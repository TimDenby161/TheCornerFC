-- Repeatable. Applied 2026-10-04 (audit/findings.md S1; public-API audit of 2026-10-01).
-- The site's public key (anon) should hold nothing, and signed-in visitors (authenticated)
-- exactly what docs/assets/app.js calls for them: fpl_owner_data and lock_fpl_transfers /
-- unlock_fpl_transfers, which answer only the owner (20261004_fpl_owner_login.sql), and
-- delete_my_account. Until 2026-10-04 this file gave the passphrase versions of the first three
-- to anon as well; that is how it was first run.
-- Before it, anon and authenticated held every privilege on almost every table, so row level security with no policies is the only
-- barrier, and a new table gets the same grants the moment it is created.
-- 1. Row level security on the eight tables that db/schema.sql never gave it (live already has it).
-- 2. Take every table, view, sequence and function grant in public away from anon, authenticated
--    and PUBLIC, then give signed-in visitors back the functions the site uses.
-- 3. New tables, sequences and functions made by the role running this (postgres) start closed.
-- The pipeline (DATABASE_URL, postgres) and local_readonly are not touched. After this, anon
-- reads of the other tables answer 401 instead of 200 with no rows.
-- When applied, append this file to db/schema.sql as the other migrations are.
ALTER TABLE fixture_player_ranks   ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_career_checks   ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_career_teams    ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_overrides       ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_position_ranks  ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_projected_ranks ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_season_ranks    ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_squads            ENABLE ROW LEVEL SECURITY;

DO $$ DECLARE r text; f regprocedure; BEGIN
    -- Functions one by one, so an extension's functions that happen to live in public are left alone
    FOR f IN SELECT p.oid::regprocedure FROM pg_proc p
             WHERE p.pronamespace = 'public'::regnamespace
               AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e') LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f);
        FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
                EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I', f, r);
            END IF;
        END LOOP;
    END LOOP;
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);      -- views too
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', r);
        END IF;
    END LOOP;
    -- Signed-in visitors only: deleting their own account (20261004_delete_my_account.sql) and the
    -- owner-only FPL functions (20261004_fpl_owner_login.sql). Each is skipped until it exists.
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        FOREACH r IN ARRAY ARRAY['delete_my_account()', 'fpl_owner_data(integer)',
                                 'lock_fpl_transfers(integer, integer, integer, jsonb)',
                                 'unlock_fpl_transfers(integer, integer, integer)'] LOOP
            IF to_regprocedure(r) IS NOT NULL THEN
                EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO authenticated', r);
            END IF;
        END LOOP;
    END IF;
END; $$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
-- PUBLIC's EXECUTE on new functions is a database-wide default, which a per-schema revoke can't
-- remove: this covers functions this role creates in any schema.
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- Check afterwards (each should return no rows). Tables made in the dashboard's Table editor may
-- be created by another role (supabase_admin), whose defaults this can't change: re-run the checks
-- after adding one there.
--   select relname from pg_class where relnamespace='public'::regnamespace and relkind in ('r','p')
--     and not relrowsecurity;
--   select grantee, table_name, privilege_type from information_schema.role_table_grants
--     where table_schema='public' and grantee in ('anon','authenticated','PUBLIC');
--   select p.oid::regprocedure from pg_proc p where p.pronamespace='public'::regnamespace
--     and has_function_privilege('anon', p.oid, 'execute');
