-- Repeatable. Applied 2026-10-05.
-- site_next_xi(team) was slow on the real database: about 0.2 s of work a call, 4 to 7 s each
-- with twenty at once, and some stopped at the public key's 3 second limit. To find a club's
-- next match with a predicted XI, the database walked every fixture in kick-off order from the
-- oldest (124,000 of them) looking for one of that club's, where the club has about thirty.
-- Now it takes the club's own fixtures first (by the index on predicted_lineups.team_id) and
-- picks the earliest of those: 0.4 ms. The answer is the same. (It was fast on the test copy,
-- which only held the fixtures with a predicted line-up.)
-- Replaces the function from 20261005_site_players.sql. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_next_xi(p_team integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    next_fixture integer;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    -- the club's fixtures with a predicted XI, then the earliest (OFFSET 0 keeps the two steps apart)
    SELECT f.fixture_id INTO next_fixture
    FROM (SELECT DISTINCT pl.fixture_id FROM public.predicted_lineups pl WHERE pl.team_id = p_team OFFSET 0) mine
    JOIN public.fixtures f ON f.fixture_id = mine.fixture_id
    ORDER BY f.kickoff, f.fixture_id LIMIT 1;
    RETURN coalesce((
        SELECT pg_catalog.json_build_object(
            'fixture', next_fixture,
            -- team-sheet order: keeper, defence right to left, midfield, attack
            'players', pg_catalog.json_agg(
                pg_catalog.json_build_array(pl.player_id, p.name, pl.position, pl.player_rank::float8)
                ORDER BY coalesce(pg_catalog.array_position(
                             ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'], pl.position), 99),
                         coalesce(pl.player_rank, 0) DESC, pl.player_id))
        FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
        WHERE pl.fixture_id = next_fixture AND pl.team_id = p_team
        HAVING count(*) > 0), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_next_xi(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_next_xi(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select left(public.site_next_xi((select team_id from predicted_lineups limit 1))::text, 80);   -- {"fixture" : ..., "players" : [[...
--   select public.site_next_xi(-1)::text;                                                          -- null
