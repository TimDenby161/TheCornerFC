-- Additive and repeatable. Not applied yet: run it in the Supabase SQL editor.
-- The site's data in the database (audit/db-api-plan.md; owner's go-ahead 2026-10-04). Step 1 of
-- the move away from docs/data: every file the export publishes is also kept here, one row per
-- file, keyed by its path without ".json" ('matches', 'clubs/42'). The export writes the rows
-- (export.mirror_site_docs); nothing on the site reads them yet.
--   site.docs    in its own schema, which the Data API doesn't expose: no key can reach the table.
--   site_doc()   the only way in. Fixed SQL, one row by primary key, 3 second limit.
--   paid         rows marked paid are never returned by site_doc. A later migration adds the
--                subscriber check; until then nothing is marked paid.
-- Also in db/schema.sql.
CREATE SCHEMA IF NOT EXISTS site;
REVOKE ALL ON SCHEMA site FROM PUBLIC;

CREATE TABLE IF NOT EXISTS site.docs (
    key text PRIMARY KEY CHECK (key ~ '^[a-z_]+(/[0-9]+)?$'),
    body jsonb NOT NULL,
    sha256 text NOT NULL,                       -- of the published file: unchanged rows aren't rewritten
    paid boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE site.docs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.docs FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.site_doc(p_key text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' SET statement_timeout = '3s' AS $$
    SELECT body FROM site.docs WHERE key = p_key AND NOT paid;
$$;

REVOKE ALL ON FUNCTION public.site_doc(text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA site FROM %I', r);
            EXECUTE format('REVOKE ALL ON site.docs FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_doc(text) TO %I', r);
        END IF;
    END LOOP;
END; $$;

-- Check afterwards:
--   select has_schema_privilege('anon', 'site', 'usage'), has_table_privilege('anon', 'site.docs', 'select');   -- f, f
--   select count(*), pg_size_pretty(pg_total_relation_size('site.docs')) from site.docs;    -- after the next export: about 9,700 rows
--   select jsonb_typeof(public.site_doc('rankings'));                                       -- object
