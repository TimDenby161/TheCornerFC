-- Repeatable. Not applied yet: the owner runs it in the Supabase SQL editor.
-- A league's page from one question, so the paid tier can cut it down (owner, 2026-10-06). A
-- league's file carries every remaining fixture's projected goals and chances, which the page
-- plays out for the projected table: paid content, by the owner's line of 2026-10-04.
--   site_league(id)   the league's page data. Once this function exists the export writes two
--                     rows for each league (export.export_leagues): "leagues/<id>", cut down
--                     (chances only for fixtures in the next 7 days, no projected goals, and
--                     "cut": true so the page can say what is behind the lock), and
--                     "paid_leagues/<id>", whole and marked paid, which site_doc() never
--                     returns. This returns the whole one to anyone entitled (everyone, while
--                     the paywall is off: site.entitled()) and the cut-down one otherwise. Until
--                     the export has written the paid row, everyone gets "leagues/<id>", which
--                     is still whole.
-- Needs 20261006_paid_tier.sql. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_league(p_id integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc json;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    IF site.entitled() THEN
        SELECT d.body INTO doc FROM site.docs d WHERE d.key = 'paid_leagues/' || p_id AND d.paid;
    END IF;
    IF doc IS NULL THEN
        SELECT d.body INTO doc FROM site.docs d WHERE d.key = 'leagues/' || p_id AND NOT d.paid;
    END IF;
    RETURN coalesce(doc, 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_league(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_league(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select left(public.site_league(39)::text, 60);                                  -- {"id":39,"season":2026,...
--   select public.site_league(-1)::text;                                            -- null
--   select count(*) from site.docs where paid;                                      -- after the next export: one per league (70)
--   select public.site_doc('paid_leagues/39')::text;                                -- null, always
