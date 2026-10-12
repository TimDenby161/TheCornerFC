-- Repeatable. Not yet applied.
-- Which database this is (owner, 2026-10-12: a staging copy beside production). Each database
-- says of itself whether it is production or staging, in the row 'environment' of site.settings,
-- and a run that may write checks the answer before it does (config.verify_database; one of
-- three checks, with the address and the credentials themselves; guide/environments.md).
--
-- This file carries no value, so the schema is the same in both. After applying it, set the row
-- ONCE, by hand, in the database it describes:
--     insert into site.settings (key, value) values ('environment', '"production"');   -- in production
--     insert into site.settings (key, value) values ('environment', '"staging"');      -- in staging
-- From then on the row can't be changed or deleted, and the table can't be emptied: only someone
-- who can drop the trigger can alter it, which no job or page does.
--
-- Production: apply this and set the row BEFORE the code that asks for it is on main. That code
-- stops a job whose database doesn't answer; the site then goes on showing the last export.
CREATE OR REPLACE FUNCTION site.keep_environment() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'site.settings is never emptied: it says which database this is';
    END IF;
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        IF OLD.key = 'environment' THEN
            RAISE EXCEPTION 'site.settings: environment is set once and never changed';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF NEW.key = 'environment' AND NEW.value NOT IN ('"production"'::jsonb, '"staging"'::jsonb) THEN
        RAISE EXCEPTION 'site.settings: environment is "production" or "staging"';
    END IF;
    RETURN NEW;
END; $$;

DROP TRIGGER IF EXISTS keep_environment ON site.settings;
CREATE TRIGGER keep_environment BEFORE INSERT OR UPDATE OR DELETE ON site.settings
    FOR EACH ROW EXECUTE FUNCTION site.keep_environment();
DROP TRIGGER IF EXISTS keep_environment_whole ON site.settings;
CREATE TRIGGER keep_environment_whole BEFORE TRUNCATE ON site.settings
    FOR EACH STATEMENT EXECUTE FUNCTION site.keep_environment();

-- The one way to read it. Fixed SQL; in the schema the Data API doesn't expose, so no key reaches it.
CREATE OR REPLACE FUNCTION site.environment() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT s.value #>> '{}' FROM site.settings s WHERE s.key = 'environment';
$$;
REVOKE ALL ON FUNCTION site.keep_environment() FROM PUBLIC;
REVOKE ALL ON FUNCTION site.environment() FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON FUNCTION site.environment() FROM %I', r);
        END IF;
    END LOOP;
    -- the read-only role this machine uses may ask (scripts/environment.py status), and nothing more
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='local_readonly') THEN
        GRANT USAGE ON SCHEMA site TO local_readonly;
        GRANT EXECUTE ON FUNCTION site.environment() TO local_readonly;
    END IF;
END; $$;

-- Check afterwards:
--   select site.environment();                                                   -- null until the row is set, then production (or staging)
--   update site.settings set value = '"staging"' where key = 'environment';      -- refused
--   delete from site.settings where key = 'environment';                         -- refused
--   update site.settings set value = value where key = 'paywall';                -- still allowed
--   select has_function_privilege('anon', 'site.environment()', 'execute');      -- f
