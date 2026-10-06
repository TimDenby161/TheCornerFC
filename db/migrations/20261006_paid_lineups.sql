-- Repeatable. Applied 2026-10-06.
-- Predicted line-ups for the paid tier (owner's line of 2026-10-04: predicted line-ups are
-- paid). Both functions are the ones already live with one thing added; while the paywall is
-- off (site.entitled() true for everyone) they answer exactly as before, plus "locked": false.
--   site_lineups(fixture)   the predicted XI ("xi") of a match that hasn't kicked off is null
--                           for anyone not entitled, with "locked": true. The XI that started
--                           and the one predicted before the team sheet ("actual", "prematch")
--                           only exist for finished matches and stay free: the record is free.
--   site_next_xi(team)      {"fixture", "players": null, "locked": true} for anyone not entitled.
-- Needs 20261006_paid_tier.sql, 20261005_site_lineups.sql and 20261005_site_next_xi_fast.sql.
-- Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_lineups(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    -- the predicted XI of a match that hasn't kicked off is for the entitled
    whole boolean := site.entitled()
        OR coalesce((SELECT f.kickoff <= pg_catalog.now() FROM public.fixtures f WHERE f.fixture_id = p_fixture), true);
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'id', p_fixture,
            -- the predicted XI, in team-sheet order: keeper, defence right to left, midfield, attack
            'locked', NOT whole,
            'xi', CASE WHEN whole THEN (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT pl.team_id, pg_catalog.json_agg(
                                  pg_catalog.json_build_array(pl.player_id, p.name, pl.position, pl.player_rank::float8)
                                  ORDER BY coalesce(pg_catalog.array_position(roles.sheet, pl.position), 99),
                                           coalesce(pl.player_rank, 0) DESC, pl.player_id) AS players
                       FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
                       WHERE pl.fixture_id = p_fixture GROUP BY pl.team_id) t) END,
            -- the XI that started a finished match on the site, each player with his rank going into it
            'actual', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT x.team_id, pg_catalog.json_agg(
                                  pg_catalog.json_build_array(x.player_id, p.name, x.role, coalesce(r.player_rank, p.current_rank)::float8)
                                  ORDER BY coalesce(pg_catalog.array_position(roles.sheet, x.role), 99),
                                           coalesce(r.player_rank, p.current_rank, 0) DESC, x.player_id) AS players
                       FROM (SELECT DISTINCT ON (s.team_id, s.player_id) s.team_id, s.player_id, s.role
                             FROM (SELECT fp.team_id, fp.player_id,
                                          coalesce(fp.role, CASE fp.position WHEN 'G' THEN 'GK' WHEN 'D' THEN 'CB'
                                                                             WHEN 'M' THEN 'CM' WHEN 'F' THEN 'ST' END) AS role, 1 AS src
                                   FROM public.fixture_players fp WHERE fp.fixture_id = p_fixture AND fp.started
                                   UNION ALL
                                   SELECT fl.team_id, fl.player_id, fl.role, 2 FROM public.fixture_lineups fl WHERE fl.fixture_id = p_fixture) s
                             ORDER BY s.team_id, s.player_id, s.src) x
                       JOIN public.fixtures f ON f.fixture_id = p_fixture
                       JOIN public.players p ON p.player_id = x.player_id
                       LEFT JOIN public.fixture_player_ranks r ON r.fixture_id = p_fixture AND r.player_id = x.player_id
                       WHERE f.status_short IN ('FT', 'AET', 'PEN') AND f.kickoff > pg_catalog.now() - interval '21 days'
                       GROUP BY x.team_id) t),
            -- the XI the model predicted for it: its last capture before the team sheet was first seen
            'prematch', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT s.team_id, (SELECT pg_catalog.json_agg(pg_catalog.json_build_array(
                                                     (e.v->>'player')::int, coalesce(n.name, ''), e.v->>'role', (e.v->>'player_rating')::float8)
                                                 ORDER BY e.i)
                                          FROM pg_catalog.jsonb_array_elements(s.players) WITH ORDINALITY e(v, i)
                                          LEFT JOIN public.players n ON n.player_id = (e.v->>'player')::int
                                          WHERE (e.v->>'predicted_starter')::boolean) AS players
                       FROM (SELECT DISTINCT ON (s.team_id) s.team_id, s.players
                             FROM public.lineup_prediction_snapshots s JOIN public.fixtures f ON f.fixture_id = s.fixture_id
                             WHERE s.fixture_id = p_fixture AND s.source = 'prospective'
                               AND f.status_short IN ('FT', 'AET', 'PEN') AND f.kickoff > pg_catalog.now() - interval '21 days'
                               AND s.captured_at < coalesce((SELECT min(o.captured_at) FROM public.official_lineup_snapshots o
                                                             WHERE o.fixture_id = s.fixture_id AND o.team_id = s.team_id
                                                               AND o.effective_at = s.effective_at), 'infinity'::timestamptz)
                             ORDER BY s.team_id, s.captured_at DESC, s.snapshot_id DESC) s) t
                       WHERE t.players IS NOT NULL))
        FROM (SELECT ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'] AS sheet) roles
    );
END; $$;

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
    IF next_fixture IS NOT NULL AND NOT site.entitled() THEN
        RETURN pg_catalog.json_build_object('fixture', next_fixture, 'players', NULL, 'locked', true);
    END IF;
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

REVOKE ALL ON FUNCTION public.site_lineups(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_next_xi(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_lineups(integer) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_next_xi(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select public.site_lineups((select fixture_id from predicted_lineups limit 1))::json->>'locked';        -- false
--   select left(public.site_next_xi((select team_id from predicted_lineups limit 1))::text, 80);            -- {"fixture" : ..., "players" : [[...
