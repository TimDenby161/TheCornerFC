-- Repeatable. Not applied yet: the owner runs it in the Supabase SQL editor.
-- The Line-up record's reconstructed history, asked for as it is shown (owner, 2026-10-05: a page
-- gets the data it shows). Until now the site downloaded every scored line-up (63,000 rows,
-- 6.5 MB) and added them up in the browser to show four totals, a few tables and 50 rows.
--   site.lineup_history    one row per team line-up, scored by the export in Python
--                          (export.export_lineup_history; rewritten whole on each run). In the
--                          site schema, which the Data API doesn't expose.
--   site_lineup_history()  the totals, tables and the newest p_limit rows for a range (p_days:
--                          the last so many days, null for all) and competitions (p_leagues, null
--                          for all), with the names of the clubs and players in them and no
--                          others. The same sums the browser did, so the tab reads the same.
-- Fixed SQL, definer's rights with an empty search path, at most 1,000 rows listed.
-- Needs public."application/json" (20261005_site_doc_raw.sql). Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS site.lineup_history (
    fixture_id integer NOT NULL,
    team_id integer NOT NULL,
    kickoff timestamptz NOT NULL,
    day date NOT NULL,                       -- the match date, as the tab shows it
    league_id integer,
    opponent_id integer,
    home boolean NOT NULL,
    correct smallint NOT NULL,               -- starters the predicted XI named
    roles_right smallint NOT NULL,           -- of them, put where they played
    roles_known smallint NOT NULL,           -- of them, with both positions known
    lines smallint[] NOT NULL,               -- [starters, of them named] for GK, DEF, MID, FWD
    missed integer[] NOT NULL,               -- starters it left out
    wrong integer[] NOT NULL,                -- players it picked instead
    PRIMARY KEY (fixture_id, team_id)
);
ALTER TABLE site.lineup_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.lineup_history FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.site_lineup_history(p_days integer DEFAULT NULL, p_leagues integer[] DEFAULT NULL,
                                                      p_limit integer DEFAULT 50) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH h AS (SELECT * FROM site.lineup_history),
        -- the chosen range, before the competition menu (the menu's counts come from this)
        scope AS (SELECT * FROM h WHERE p_days IS NULL
                     OR h.day::timestamp + interval '12 hours' >= (pg_catalog.now() AT TIME ZONE 'UTC') - pg_catalog.make_interval(days => p_days)),
        -- pos: a line-up's place oldest first, so clubs and competitions that tie stay in the order they first appear
        list AS (SELECT scope.*, pg_catalog.row_number() OVER (ORDER BY scope.kickoff, scope.fixture_id, scope.team_id) AS pos
                 FROM scope WHERE p_leagues IS NULL OR scope.league_id = ANY (p_leagues)),
        t AS (SELECT count(*) AS n, coalesce(sum(correct), 0) AS correct, count(*) FILTER (WHERE correct = 11) AS perfect,
                     coalesce(sum(roles_right), 0) AS roles_right, coalesce(sum(roles_known), 0) AS roles_known,
                     count(DISTINCT fixture_id) AS matches, min(day) AS first, max(day) AS last FROM list),
        -- average per day; per week past four weeks, per month past six months
        step AS (SELECT CASE WHEN t.last - t.first > 183 THEN 'month' WHEN t.last - t.first > 28 THEN 'week' ELSE 'day' END AS unit FROM t),
        shown AS (SELECT * FROM list ORDER BY kickoff DESC, fixture_id DESC, team_id DESC
                  LIMIT least(greatest(coalesce(p_limit, 50), 1), 1000)),
        tally AS (SELECT 'missed' AS kind, u.player, l.team_id, l.kickoff, l.fixture_id FROM list l, pg_catalog.unnest(l.missed) u(player)
                  UNION ALL
                  SELECT 'wrong', u.player, l.team_id, l.kickoff, l.fixture_id FROM list l, pg_catalog.unnest(l.wrong) u(player)),
        -- the players it got wrong most often (twice or more), each with the club of his first row: the top
        -- 15 by times, with everyone level with the 15th (the page puts those in name order and cuts)
        often AS (SELECT x.kind, x.player, x.n, x.team_id FROM (
                      SELECT g.kind, g.player, g.n, g.team_id, pg_catalog.rank() OVER (PARTITION BY g.kind ORDER BY g.n DESC) AS place
                      FROM (SELECT kind, player, count(*) AS n,
                                   (pg_catalog.array_agg(team_id ORDER BY kickoff, fixture_id, team_id))[1] AS team_id
                            FROM tally GROUP BY kind, player HAVING count(*) >= 2) g) x
                  WHERE x.place <= 15),
        club AS (SELECT team_id, count(*) AS n, sum(correct) AS correct, count(*) FILTER (WHERE correct = 11) AS perfect, min(pos) AS pos
                 FROM list GROUP BY team_id)
        SELECT pg_catalog.json_build_object(
            'available', true,
            'any', EXISTS (SELECT 1 FROM h),
            'leagues', (SELECT coalesce(pg_catalog.json_agg(x.league_id), '[]'::json) FROM (SELECT DISTINCT league_id FROM h) x),
            'scope', (SELECT coalesce(pg_catalog.json_object_agg(x.league_id, x.n), '{}'::json)
                      FROM (SELECT league_id, count(*) AS n FROM scope GROUP BY league_id) x),
            'total', t.n, 'correct', t.correct, 'perfect', t.perfect, 'roles_right', t.roles_right, 'roles_known', t.roles_known,
            'matches', t.matches, 'first', t.first, 'last', t.last,
            'counts', (SELECT coalesce(pg_catalog.json_object_agg(x.correct, x.n), '{}'::json)
                       FROM (SELECT correct, count(*) AS n FROM list GROUP BY correct) x),
            'step', step.unit,
            'trend', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.k, x.n, x.correct, x.perfect) ORDER BY x.k DESC), '[]'::json)
                      FROM (SELECT pg_catalog.date_trunc(step.unit, l.day::timestamp)::date AS k, count(*) AS n, sum(l.correct) AS correct,
                                   count(*) FILTER (WHERE l.correct = 11) AS perfect
                            FROM list l GROUP BY 1) x),
            'lines', (SELECT pg_catalog.json_build_array(sum(lines[1]), sum(lines[2]), sum(lines[3]), sum(lines[4]),
                                                         sum(lines[5]), sum(lines[6]), sum(lines[7]), sum(lines[8])) FROM list),
            'comps', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.league_id, x.n, x.correct, x.perfect, x.roles_right, x.roles_known) ORDER BY x.pos), '[]'::json)
                      FROM (SELECT league_id, count(*) AS n, sum(correct) AS correct, count(*) FILTER (WHERE correct = 11) AS perfect,
                                   sum(roles_right) AS roles_right, sum(roles_known) AS roles_known, min(pos) AS pos FROM list GROUP BY league_id) x),
            'clubs', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(c.team_id, c.n, c.correct, c.perfect) ORDER BY c.pos), '[]'::json) FROM club c),
            'missed', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(o.player, o.team_id, o.n) ORDER BY o.n DESC, o.player), '[]'::json)
                       FROM often o WHERE o.kind = 'missed'),
            'wrong', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(o.player, o.team_id, o.n) ORDER BY o.n DESC, o.player), '[]'::json)
                      FROM often o WHERE o.kind = 'wrong'),
            'missed_total', (SELECT coalesce(sum(pg_catalog.cardinality(missed)), 0) FROM list),
            -- the line-ups on screen, newest first: [date, team, opponent, home, competition, right, missed]
            'rows', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(s.day, s.team_id, s.opponent_id, s.home::int, s.league_id, s.correct,
                                                                                    pg_catalog.to_json(s.missed))
                                                         ORDER BY s.kickoff DESC, s.fixture_id DESC, s.team_id DESC), '[]'::json) FROM shown s),
            -- names for the ids above, and no others
            'teams', (SELECT coalesce(pg_catalog.json_object_agg(tm.team_id, tm.name), '{}'::json) FROM public.teams tm
                      WHERE tm.team_id IN (SELECT team_id FROM club UNION SELECT opponent_id FROM shown UNION SELECT team_id FROM often)),
            'players', (SELECT coalesce(pg_catalog.json_object_agg(pp.player_id, pp.name), '{}'::json) FROM public.players pp
                        WHERE pp.player_id IN (SELECT player FROM often UNION SELECT pg_catalog.unnest(missed) FROM shown)))
        FROM t, step
    );
END; $$;

REVOKE ALL ON FUNCTION public.site_lineup_history(integer, integer[], integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON site.lineup_history FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_lineup_history(integer, integer[], integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select has_table_privilege('anon', 'site.lineup_history', 'select');                    -- f
--   select public.site_lineup_history()::json->>'any';                                      -- false until the next export, then true
--   select public.site_lineup_history(30, '{39}', 5)::json->>'total';                       -- after it: Premier League line-ups in the last 30 days
