-- Repeatable. Not applied yet: the owner runs it in the Supabase SQL editor.
-- Ranks in the line-ups of finished matches are for subscribers too (owner, 2026-10-06: "hide
-- those ranks"): they would give away the paid player ranks one match at a time. site_lineups()
-- is the function of 20261006_paid_lineups.sql with this added: for anyone not entitled, each
-- player in "actual" and "prematch" comes without his rank ([player, name, role, null]). Who
-- started and who the model predicted stay free. While the paywall is off nothing changes.
-- Needs 20261006_paid_lineups.sql. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_lineups(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    -- the predicted XI of a match that hasn't kicked off is for the entitled (whole), and so is
    -- each player's rank in the line-ups of one that has (paid)
    paid boolean := site.entitled();
    whole boolean := paid
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
                                  pg_catalog.json_build_array(x.player_id, p.name, x.role, CASE WHEN paid THEN coalesce(r.player_rank, p.current_rank)::float8 END)
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
                                                     (e.v->>'player')::int, coalesce(n.name, ''), e.v->>'role', CASE WHEN paid THEN (e.v->>'player_rating')::float8 END)
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

REVOKE ALL ON FUNCTION public.site_lineups(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_lineups(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards (a finished match from the last 21 days):
--   select public.site_lineups((select fixture_id from fixtures where status_short = 'FT' order by kickoff desc limit 1))::json->'actual' is not null;   -- t, with ranks while the paywall is off
