-- Repeatable. Not yet applied.
-- The landing page's example line-up (owner, 2026-10-07: one predicted line-up shown to everyone
-- on Home, as an example of the paid feature). site_sample_xi() takes no argument, so it can't
-- be asked for a club of the caller's choosing: it answers with the predicted XI of the
-- strongest club (team_rankings.current_rank, among the top 20) that has one for a match still
-- to kick off, the earliest such match. Every other predicted line-up stays for the entitled
-- (site_lineups, site_next_xi: 20261006_paid_lineups.sql), which this leaves as they are.
--   {"team", "fixture", "home", "away", "kickoff", "players": [[player, name, role, rank], ...]}
--   or null when none of those clubs has a predicted XI for a match to come.
-- The same answer for everyone, so it may be kept for five minutes.
-- Needs 20261005_site_next_xi_fast.sql (the index on predicted_lineups.team_id).
BEGIN;

CREATE OR REPLACE FUNCTION public.site_sample_xi() RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    the_team integer;
    the_fixture integer;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "public, max-age=300"}]', true);
    -- the twenty strongest clubs, each one's earliest match to come that has a predicted XI (by
    -- the index on predicted_lineups.team_id; OFFSET 0 keeps the two steps apart), then the strongest
    SELECT t.team_id, nx.fixture_id INTO the_team, the_fixture
    FROM (SELECT r.team_id, r.current_rank FROM public.team_rankings r
          WHERE r.current_rank IS NOT NULL ORDER BY r.current_rank DESC, r.team_id LIMIT 20) t
    CROSS JOIN LATERAL (
        SELECT f.fixture_id
        FROM (SELECT DISTINCT pl.fixture_id FROM public.predicted_lineups pl WHERE pl.team_id = t.team_id OFFSET 0) mine
        JOIN public.fixtures f ON f.fixture_id = mine.fixture_id
        WHERE f.kickoff > pg_catalog.now()
        ORDER BY f.kickoff, f.fixture_id LIMIT 1) nx
    ORDER BY t.current_rank DESC, t.team_id LIMIT 1;
    IF the_fixture IS NULL THEN
        RETURN 'null'::json;
    END IF;
    RETURN coalesce((
        SELECT pg_catalog.json_build_object(
            'team', the_team, 'fixture', the_fixture,
            'home', (SELECT f.home_team_id FROM public.fixtures f WHERE f.fixture_id = the_fixture),
            'away', (SELECT f.away_team_id FROM public.fixtures f WHERE f.fixture_id = the_fixture),
            'kickoff', (SELECT f.kickoff FROM public.fixtures f WHERE f.fixture_id = the_fixture),
            -- team-sheet order: keeper, defence right to left, midfield, attack
            'players', pg_catalog.json_agg(
                pg_catalog.json_build_array(pl.player_id, p.name, pl.position, pl.player_rank::float8)
                ORDER BY coalesce(pg_catalog.array_position(
                             ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'], pl.position), 99),
                         coalesce(pl.player_rank, 0) DESC, pl.player_id))
        FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
        WHERE pl.fixture_id = the_fixture AND pl.team_id = the_team
        HAVING count(*) > 0), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_sample_xi() FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_sample_xi() TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select left(public.site_sample_xi()::text, 120);                    -- {"team" : ..., "fixture" : ..., ... "players" : [[...
--   select json_array_length(public.site_sample_xi()::json->'players'); -- 11
--   select public.site_next_xi((public.site_sample_xi()::json->>'team')::int)::json->>'locked';   -- still true for anyone not entitled
