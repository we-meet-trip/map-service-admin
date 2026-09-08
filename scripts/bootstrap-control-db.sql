\set ON_ERROR_STOP on
-- New dedicated control database only. Passwords are read from private environment.
-- Existing installations must use a reviewed ownership/grant transition; this script
-- intentionally fails if these roles or the schema already exist.
\getenv migration_password ADMIN_CONTROL_MIGRATION_PASSWORD
\getenv runtime_password ADMIN_CONTROL_RUNTIME_PASSWORD
BEGIN;
CREATE ROLE map_admin_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'migration_password';
CREATE ROLE map_admin_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'runtime_password';
CREATE SCHEMA admin_data AUTHORIZATION map_admin_migrator;
REVOKE ALL ON SCHEMA admin_data FROM PUBLIC;
GRANT USAGE ON SCHEMA admin_data TO map_admin_runtime;
COMMIT;
