-- Repeatable. Not applied yet: the owner runs it in the Supabase SQL editor.
-- Step 3 of the move away from docs/data (audit/db-api-plan.md): the site reads its data through
-- site_doc(). A file on GitHub Pages is kept by the browser for as long as its content hash stands
-- (data/manifest.json); a database row needs the same, or every visit downloads everything again.
--   p_v          the 16-character content hash the site has for the row (from the 'manifest' row).
--                When it is the row's hash the answer may be kept for a year: the address changes
--                when the content does. Without it, or with a stale one, the answer is not kept.
--   site_doc()   still the only way in, still one row by primary key, still never a paid row.
-- The one-argument function is replaced, not kept: two functions that both answer
-- site_doc(p_key) would make the call ambiguous.
-- Also in db/schema.sql.
BEGIN;

DROP FUNCTION IF EXISTS public.site_doc(text);

CREATE OR REPLACE FUNCTION public.site_doc(p_key text, p_v text DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' SET statement_timeout = '3s' AS $$
DECLARE
    doc record;
BEGIN
    SELECT body, sha256 INTO doc FROM site.docs WHERE key = p_key AND NOT paid;
    PERFORM pg_catalog.set_config('response.headers',
        CASE WHEN doc.sha256 IS NOT NULL AND p_v = pg_catalog.left(doc.sha256, 16)
             THEN '[{"Cache-Control": "public, max-age=31536000, immutable"}]'
             ELSE '[{"Cache-Control": "no-cache"}]' END, true);
    RETURN doc.body;
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

-- Check afterwards:
--   select jsonb_typeof(public.site_doc('rankings'));                                        -- object
--   select jsonb_typeof(public.site_doc('rankings', left(sha256, 16))) from site.docs where key = 'rankings';   -- object
--   select has_table_privilege('anon', 'site.docs', 'select');                               -- f
