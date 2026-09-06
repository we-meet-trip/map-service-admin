"""Individual operator permissions and durable login throttling."""
from alembic import op

revision = "0003_operator_permissions"
down_revision = "0002_admin_accounts_sessions"
branch_labels = None
depends_on = None


def upgrade():
    # 기존 계정은 모두 관리 권한을 가졌으므로 그 권한을 유지한다.
    op.execute("ALTER TABLE admin_data.admin_accounts ADD COLUMN role TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner','operator','viewer'))")
    op.execute("ALTER TABLE admin_data.admin_accounts ADD COLUMN allowed_environments JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(allowed_environments)='array')")
    op.execute("CREATE TABLE admin_data.login_attempts (bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires_at TIMESTAMPTZ NOT NULL)")
    op.execute("CREATE INDEX ix_login_attempts_expiry ON admin_data.login_attempts(expires_at)")


def downgrade():
    raise RuntimeError("operator permissions migration requires a reviewed forward change")
