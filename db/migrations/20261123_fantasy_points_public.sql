-- Repeatable. Applied to staging 2026-11-23 (production not yet).
-- The Fantasy points page for every signed-in account (T-104, owner's decision 2026-11-23: free
-- with an account, with prices and injury flags, not for subscribers only; partly supersedes the
-- owner-only rule of 2026-10-02 for this one document). Only the 'fpl_predictions' document is
-- opened: the owner's team, the lock-ins and the Fantasy EFL predictions stay behind
-- fpl_owner_data. Signed-out visitors (the public key alone) and anonymous sign-ins get nothing.
--
--   fantasy_points_stamp()   {ok, updated_at} for a signed-in caller, else {ok: false, error}.
--                            About 100 bytes: the site asks it on every view, as the visitor,
--                            and keeps the document in memory until the stamp changes.
--   fantasy_points_doc()     {ok, updated_at, doc} for a signed-in caller, else {ok: false, error}.
--                            About 1 MB: fetched once a night after the export, and after a restart.
--
-- No table changes, nothing stored. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.fantasy_points_stamp() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "private, no-store"}]', true);
    IF auth.uid() IS NULL OR coalesce((auth.jwt()->>'is_anonymous')::boolean, false) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'Sign in to see this');
    END IF;
    RETURN pg_catalog.jsonb_build_object('ok', true,
        'updated_at', (SELECT d.updated_at FROM public.fpl_owner_docs d WHERE d.name = 'fpl_predictions'));
END; $$;

CREATE OR REPLACE FUNCTION public.fantasy_points_doc() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "private, no-store"}]', true);
    IF auth.uid() IS NULL OR coalesce((auth.jwt()->>'is_anonymous')::boolean, false) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'Sign in to see this');
    END IF;
    RETURN coalesce((SELECT pg_catalog.jsonb_build_object('ok', true, 'updated_at', d.updated_at, 'doc', d.doc)
                     FROM public.fpl_owner_docs d WHERE d.name = 'fpl_predictions'),
                    pg_catalog.jsonb_build_object('ok', true, 'updated_at', null, 'doc', null));
END; $$;

REVOKE ALL ON FUNCTION public.fantasy_points_stamp() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.fantasy_points_doc() FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON FUNCTION public.fantasy_points_stamp() FROM anon;
        REVOKE ALL ON FUNCTION public.fantasy_points_doc() FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        GRANT EXECUTE ON FUNCTION public.fantasy_points_stamp() TO authenticated;
        GRANT EXECUTE ON FUNCTION public.fantasy_points_doc() TO authenticated;
    END IF;
END; $$;

COMMIT;
