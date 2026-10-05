-- Repeatable. Applied 2026-10-05.
-- A match's line-ups, asked for when its card is opened (owner, 2026-10-05: a page gets the data
-- it shows, when it shows it). Until now the export worked out every match's line-ups ahead of
-- time (2.7 MB inside players.json, then 7,000 one-match files for a few hours). They are already
-- in the database, so the site asks for one match's:
--   site_lineups(fixture)   {"id", "xi", "actual", "prematch"}, each {team: [[player, name, role, rank], ...]}
--                           or null. xi: the predicted XI. actual: the XI that started, for a
--                           finished match from the last 21 days (export.PAST_DAYS), each player
--                           with his rank going into it. prematch: the XI the model predicted
--                           before the team sheet was first seen. The same rows, rules and order
--                           the export used (export_players before this), nothing more.
-- Fixed SQL, one match by its id, definer's rights with an empty search path; the tables
-- themselves stay closed to the public key. The answer is not kept by the browser: a line-up
-- can change before kick-off.
-- fixture_player_ranks had no index (it is truncated and copied every night); one is added so
-- a match's ranks are a lookup, not a scan of 945,000 rows.
-- Needs public."application/json" (20261005_site_doc_raw.sql). Also in db/schema.sql.
BEGIN;

CREATE INDEX IF NOT EXISTS fixture_player_ranks_fixture_idx ON public.fixture_player_ranks (fixture_id, player_id);

CREATE OR REPLACE FUNCTION public.site_lineups(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'id', p_fixture,
            -- the predicted XI, in team-sheet order: keeper, defence right to left, midfield, attack
            'xi', (SELECT pg_catalog.json_object_agg(t.team_id, t.players) FROM (
                       SELECT pl.team_id, pg_catalog.json_agg(
                                  pg_catalog.json_build_array(pl.player_id, p.name, pl.position, pl.player_rank::float8)
                                  ORDER BY coalesce(pg_catalog.array_position(roles.sheet, pl.position), 99),
                                           coalesce(pl.player_rank, 0) DESC, pl.player_id) AS players
                       FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
                       WHERE pl.fixture_id = p_fixture GROUP BY pl.team_id) t),
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

-- Check afterwards:
--   select left(public.site_lineups((select fixture_id from predicted_lineups limit 1))::text, 120);   -- {"id" : ..., "xi" : {...
--   select public.site_lineups(1)::text;                                                                -- every part null
--   select has_table_privilege('anon', 'public.predicted_lineups', 'select');                           -- f
