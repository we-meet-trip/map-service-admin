"""Synthetic isolated PostgreSQL integration. Never connects to an existing DB."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

root = Path(__file__).resolve().parents[1]
name = "map-control-isolation-20260906-" + uuid.uuid4().hex[:8]
password = secrets.token_urlsafe(32)
env = {**os.environ, "POSTGRES_PASSWORD": password}
checks = {}

def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, check=True, **kwargs)

def sql(query):
    return run(["docker", "exec", "-i", name, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1"], input=query).stdout

try:
    run(["docker", "run", "--pull", "never", "-d", "--name", name, "--memory", "384m", "--tmpfs", "/var/lib/postgresql/data", "-p", "127.0.0.1::5432", "-e", "POSTGRES_PASSWORD", "postgis/postgis:17-3.5"], env=env)
    for attempt in range(60):
        if subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"], capture_output=True).returncode == 0:
            break
        time.sleep(0.5)
    port = run(["docker", "port", name, "5432/tcp"]).stdout.strip().split(":")[-1]
    # Tokens contain only URL-safe characters; SQL literal escaping still explicit.
    quoted = password.replace("'", "''")
    sql(f"CREATE ROLE map_admin_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{quoted}'; CREATE ROLE map_admin_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{quoted}'; CREATE SCHEMA admin_data AUTHORIZATION map_admin_migrator; REVOKE ALL ON SCHEMA admin_data FROM PUBLIC; GRANT USAGE ON SCHEMA admin_data TO map_admin_runtime;")
    base = f"postgresql+psycopg://{{role}}:{password}@127.0.0.1:{port}/postgres"
    runtime = base.format(role="map_admin_runtime")
    migration = base.format(role="map_admin_migrator")
    private_env = {**os.environ, "ADMIN_CONTROL_DATABASE_URL": runtime,
                   "ADMIN_CONTROL_MIGRATION_DATABASE_URL": migration,
                   "ADMIN_BOOTSTRAP_USER": "synthetic-owner", "ADMIN_BOOTSTRAP_PASSWORD": password,
                   "ADMIN_DATABASE_URL": "", "ADMIN_TARGETS": "{}"}
    run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=private_env)
    sql((root / "scripts/grant-control-runtime.sql").read_text())
    private_env.pop("ADMIN_CONTROL_MIGRATION_DATABASE_URL")
    os.environ.pop("ADMIN_CONTROL_MIGRATION_DATABASE_URL", None)
    os.environ.update(private_env)
    sys.path.insert(0, str(root))
    import psycopg
    with psycopg.connect(runtime.replace("postgresql+psycopg", "postgresql")) as conn:
        checks["control_has_no_hub_schema"] = conn.execute("SELECT count(*) FROM information_schema.schemata WHERE schema_name='hub_data'").fetchone()[0] == 0
        checks["runtime_no_admin_ddl"] = not conn.execute("SELECT has_schema_privilege(current_user,'admin_data','CREATE')").fetchone()[0]
        checks["runtime_not_superuser"] = not conn.execute("SELECT rolsuper OR rolcreaterole OR rolcreatedb FROM pg_roles WHERE rolname=current_user").fetchone()[0]
        checks["runtime_audit_delete_denied"] = not conn.execute("SELECT has_table_privilege(current_user,'admin_data.audit_logs','DELETE')").fetchone()[0]
        checks["runtime_migration_write_denied"] = not conn.execute("SELECT has_table_privilege(current_user,'admin_data.alembic_version','UPDATE')").fetchone()[0]
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import control_settings
    with TestClient(app, raise_server_exceptions=False) as client:
        checks["control_bootstrap_ready"] = client.get("/health/ready").status_code == 200
        checks["login_without_target"] = client.post("/api/v1/auth/login", json={"username":"synthetic-owner", "password":password}).status_code == 200
        checks["me_without_target"] = client.get("/api/v1/auth/me").status_code == 200
        checks["environments_without_target"] = client.get("/api/v1/environments").status_code == 200
        control_settings.ADMIN_TARGETS = {"test": {"ADMIN_DATABASE_URL": "postgresql+psycopg://unavailable:unused@127.0.0.1:1/no_db", "ADMIN_REDIS_URL":"redis://127.0.0.1:1", "USER_BASE_URL":"http://127.0.0.1:1", "AGENT_BASE_URL":"http://127.0.0.1:1", "HUB_BASE_URL":"http://127.0.0.1:1", "INTERNAL_SERVICE_TOKEN":"synthetic"}}
        checks["target_failure_is_503"] = client.get("/api/v1/db/tables").status_code == 503
        checks["control_survives_target_failure"] = client.get("/health/ready").status_code == 200 and client.get("/api/v1/auth/me").status_code == 200
        checks["logout_after_target_failure"] = client.post("/api/v1/auth/logout").status_code == 204
    result = {"scope":"local synthetic dedicated PostgreSQL; no GCP changes", "container":name, "checks":checks, "overall":all(checks.values())}
    print(json.dumps(result, indent=2))
    if not result["overall"]: sys.exit(1)
except Exception as exc:
    print(json.dumps({"scope":"local synthetic", "container":name, "overall":False, "error_type":type(exc).__name__, "safe_detail": (getattr(exc, "stderr", "") or "").replace(password, "[REDACTED]")[-1500:]}))
    sys.exit(1)
finally:
    # Only the newly created tmpfs test container is stopped. No existing DB/volume touched.
    subprocess.run(["docker", "stop", name], capture_output=True)
