\set ON_ERROR_STOP on
-- Run as the schema owner after Alembic; runtime never owns tables or runs DDL.
BEGIN;
GRANT SELECT, INSERT, UPDATE ON admin_data.admin_accounts TO map_admin_runtime;
GRANT SELECT, INSERT, DELETE ON admin_data.admin_sessions TO map_admin_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON admin_data.login_attempts TO map_admin_runtime;
GRANT SELECT, INSERT, UPDATE ON admin_data.audit_logs TO map_admin_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA admin_data TO map_admin_runtime;
GRANT SELECT ON admin_data.alembic_version TO map_admin_runtime;
COMMIT;
