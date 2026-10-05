-- Repeatable. Applied 2026-10-05.
-- site_doc() was slow on the big rows: 2 to 4 seconds for 'players' (5 MB) and over the anon
-- role's 3 second limit for 'lineups_history' (8 MB), more so with several readers at once
-- (measured 2026-10-05, the day the site started reading the table). The time went on rebuilding
-- the JSON on every read: the row was stored as jsonb, turned back into text, wrapped by the
-- Data API and unwrapped again. Now nothing is rebuilt:
--   body         is json, not jsonb: the published file's own text, stored and returned as it is.
--                Nothing queries inside it, which is all jsonb was for.
--   site_doc()   returns the "application/json" domain, which tells the Data API (PostgREST 12+)
--                that the value is already the response body. A key with no row answers null,
--                as before.
-- Also in db/schema.sql.
BEGIN;

ALTER TABLE site.docs ALTER COLUMN body TYPE json USING body::json;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'public' AND t.typname = 'application/json') THEN
        CREATE DOMAIN public."application/json" AS json;
    END IF;
END; $$;

DROP FUNCTION IF EXISTS public.site_doc(text, text);     -- the return type changes, so it can't be replaced in place

CREATE FUNCTION public.site_doc(p_key text, p_v text DEFAULT NULL) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc record;
BEGIN
    SELECT body, sha256 INTO doc FROM site.docs WHERE key = p_key AND NOT paid;
    PERFORM pg_catalog.set_config('response.headers',
        CASE WHEN doc.sha256 IS NOT NULL AND p_v = pg_catalog.left(doc.sha256, 16)
             THEN '[{"Cache-Control": "public, max-age=31536000, immutable"}]'
             ELSE '[{"Cache-Control": "no-cache"}]' END, true);
    RETURN coalesce(doc.body, 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_doc(text, text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_doc(text, text) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';      -- the Data API picks up the new return type straight away

-- Check afterwards:
--   select pg_typeof(body) from site.docs limit 1;                                           -- json
--   select left(public.site_doc('manifest')::text, 20), public.site_doc('nothing_here')::text;   -- {"files": ...   null
--   select has_table_privilege('anon', 'site.docs', 'select');                               -- f
-- To go back: run db/migrations/20261005_site_doc_cache.sql again after
--   DROP FUNCTION public.site_doc(text, text);   (the column can stay json)
