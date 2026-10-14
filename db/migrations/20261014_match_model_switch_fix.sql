-- Repeatable. Applied 2026-10-14, to staging and to production.
-- Mends admin_match_model() (20261014_challenger_model.sql), so the Admin area's switch card shows
-- (found 2026-10-14, when the owner could not see it): it called pg_catalog.coalesce, which does not
-- exist, since COALESCE is part of SQL's grammar and not a function. Every call failed, the
-- site took no answer as no administrator, and admin_set_match_model(), which returns this, failed
-- too. Same answer, same grants (CREATE OR REPLACE keeps them). Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.admin_match_model() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-store"}]', true);
    IF NOT site.is_admin() THEN
        RETURN pg_catalog.jsonb_build_object('ok', false);
    END IF;
    RETURN pg_catalog.jsonb_build_object('ok', true,
        'live', (SELECT s.live FROM public.match_model_switch s),
        'switches', (SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                         'at', x.switched_at, 'live', x.live) ORDER BY x.switched_at DESC), '[]'::jsonb)
                     FROM (SELECT w.switched_at, w.live FROM public.match_model_switches w
                           ORDER BY w.switched_at DESC LIMIT 50) x));
END;
$$;

COMMIT;

-- Check afterwards, signed in as the owner for a moment and undone:
--   begin;
--   select set_config('request.jwt.claims', json_build_object('role', 'authenticated',
--     'sub', (select id from auth.users where lower(email) = 'timdenby161@gmail.com'))::text, true);
--   set local role authenticated;
--   select public.admin_match_model();                 -- {"ok": true, "live": "base", "switches": []}
--   rollback;
--   select public.admin_match_model();                 -- {"ok": false} here: the editor is no signed-in visitor
