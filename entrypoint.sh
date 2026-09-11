#!/bin/sh
# =========================================================================
# map-service-admin 컨테이너 엔트리포인트 (cut 2)
#
# uvicorn 기동 전에 admin_data 스키마 마이그레이션을 적용한다.
#   1) alembic upgrade head — admin_data(audit_logs/admin_accounts/
#      admin_sessions) 테이블 보장. map_admin 이 admin_data 를 소유해야 하며
#      (infra 10-admin.sh), 미소유 환경(기존 볼륨·수동적용 누락)에서는 여기서
#      실패해 컨테이너가 즉시 종료된다(fail-fast — 권한/DB 문제를 표면화).
#   2) exec uvicorn — PID 1 로 앱 기동(시그널 전달 보장).
#
# ADMIN_DATABASE_URL 은 compose 공유 .env 에서 주입된다.
# =========================================================================
set -eu

# Central runtime does not need or receive DDL credentials. Migration is a separate job.
if [ "${ADMIN_RUN_MIGRATIONS:-auto}" = "true" ] || { [ "${ADMIN_RUN_MIGRATIONS:-auto}" = "auto" ] && [ -z "${ADMIN_CONTROL_DATABASE_URL:-}" ]; }; then
    echo "entrypoint: applying admin_data migrations"
    alembic upgrade head
fi
unset ADMIN_CONTROL_MIGRATION_DATABASE_URL

echo "entrypoint: starting uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
