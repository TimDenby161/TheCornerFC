-- Repeatable. Applied 2026-10-04.
-- Supabase's Security Advisor warns that the eight trigger functions behind the append-only
-- tables have no fixed search_path ("Function Search Path Mutable"). They read only tables in
-- public, so pinning the path changes nothing they do; it stops a same-named object in another
-- schema being picked up instead. Also in db/schema.sql.
ALTER FUNCTION prevent_model_version_mutation() SET search_path = public, pg_temp;
ALTER FUNCTION guard_match_snapshot()           SET search_path = public, pg_temp;
ALTER FUNCTION guard_lineup_snapshot()          SET search_path = public, pg_temp;
ALTER FUNCTION guard_paper_evidence()           SET search_path = public, pg_temp;
ALTER FUNCTION guard_player_history()           SET search_path = public, pg_temp;
ALTER FUNCTION guard_squad_transfer_evidence()  SET search_path = public, pg_temp;
ALTER FUNCTION guard_fpl_evidence()             SET search_path = public, pg_temp;
ALTER FUNCTION guard_fantasy_fixture_snapshot() SET search_path = public, pg_temp;

-- Check afterwards (expect no rows):
--   select p.proname from pg_proc p where p.pronamespace='public'::regnamespace
--     and (p.proname like 'guard\_%' or p.proname = 'prevent_model_version_mutation')
--     and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) c where c like 'search_path=%');
