-- Repeatable. Not applied yet: the owner runs it in the Supabase SQL editor.
-- site_lineup_history() was too slow for the whole history. Measured on 2026-10-05, the evening
-- it went live: about 2 seconds for all 63,369 line-ups against the public key's 3 second limit
-- (filtered views 0.3 to 0.5 seconds), and several at once failed. It read every row for each
-- total, and unpacked 340,000 missed and wrong picks, on every request, for figures that only
-- change when the export runs. Now:
--   site.lineup_history_teams, _days, _often   the whole history counted once per export: per
--                          competition and club, per competition and match date, and per player
--                          the model got wrong and competition. A few hundred to a few thousand
--                          short rows each.
--   site.lineup_history_refresh()   fills them from site.lineup_history. The export calls it after
--                          rewriting that table (export.export_lineup_history); this migration
--                          calls it once, so no export is needed first.
--   site_lineup_history()  same arguments, same answer. The whole history is summed from the
--                          counted tables; a range (a year is under 10,000 line-ups) is counted
--                          from the rows, found by an index on the match date. The rows listed
--                          come by an index, newest first.
-- On a copy of the data the answers were identical to the first version's in fourteen
-- combinations of range, competitions and rows listed, and the whole history took 38 ms where it
-- had taken 592.
-- Needs 20261005_site_lineup_history.sql. Also in db/schema.sql.
BEGIN;

-- counted once per export, so the whole history is read from a few hundred rows, not 63,000
CREATE TABLE IF NOT EXISTS site.lineup_history_teams (      -- per competition and club
    league_id integer, team_id integer NOT NULL,
    n integer NOT NULL, correct integer NOT NULL, perfect integer NOT NULL, roles_right integer NOT NULL, roles_known integer NOT NULL,
    counts integer[] NOT NULL,               -- line-ups by starters named, 0 to 11
    lines integer[] NOT NULL,                -- [starters, of them named] for GK, DEF, MID, FWD, added up
    pos bigint[] NOT NULL                    -- its first line-up: [kick-off in seconds, fixture, team]
);
CREATE TABLE IF NOT EXISTS site.lineup_history_days (       -- per competition and match date
    league_id integer, day date NOT NULL,
    n integer NOT NULL, correct integer NOT NULL, perfect integer NOT NULL, matches integer NOT NULL
);
CREATE TABLE IF NOT EXISTS site.lineup_history_often (      -- per player it got wrong, and competition
    kind text NOT NULL,                      -- 'missed': started but not picked; 'wrong': picked but didn't start
    player integer NOT NULL, league_id integer,
    n integer NOT NULL,
    pos bigint[] NOT NULL                    -- the first line-up it happened in
);
CREATE INDEX IF NOT EXISTS lineup_history_day_idx ON site.lineup_history (day);
CREATE INDEX IF NOT EXISTS lineup_history_newest_idx ON site.lineup_history (kickoff DESC, fixture_id DESC, team_id DESC);

DO $$ DECLARE t text; r text; BEGIN
    FOREACH t IN ARRAY ARRAY['site.lineup_history_teams', 'site.lineup_history_days', 'site.lineup_history_often'] LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('REVOKE ALL ON %s FROM PUBLIC', t);
        FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
                EXECUTE format('REVOKE ALL ON %s FROM %I', t, r);
            END IF;
        END LOOP;
    END LOOP;
END; $$;

CREATE OR REPLACE FUNCTION site.lineup_history_refresh() RETURNS void
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    DELETE FROM site.lineup_history_teams;
    INSERT INTO site.lineup_history_teams (league_id, team_id, n, correct, perfect, roles_right, roles_known, counts, lines, pos)
    SELECT h.league_id, h.team_id, count(*), sum(h.correct), count(*) FILTER (WHERE h.correct = 11), sum(h.roles_right), sum(h.roles_known),
           ARRAY[count(*) FILTER (WHERE h.correct = 0), count(*) FILTER (WHERE h.correct = 1), count(*) FILTER (WHERE h.correct = 2),
                 count(*) FILTER (WHERE h.correct = 3), count(*) FILTER (WHERE h.correct = 4), count(*) FILTER (WHERE h.correct = 5),
                 count(*) FILTER (WHERE h.correct = 6), count(*) FILTER (WHERE h.correct = 7), count(*) FILTER (WHERE h.correct = 8),
                 count(*) FILTER (WHERE h.correct = 9), count(*) FILTER (WHERE h.correct = 10), count(*) FILTER (WHERE h.correct = 11)],
           ARRAY[sum(h.lines[1]), sum(h.lines[2]), sum(h.lines[3]), sum(h.lines[4]), sum(h.lines[5]), sum(h.lines[6]), sum(h.lines[7]), sum(h.lines[8])],
           min(ARRAY[pg_catalog.date_part('epoch', h.kickoff)::bigint, h.fixture_id, h.team_id])
    FROM site.lineup_history h GROUP BY h.league_id, h.team_id;
    DELETE FROM site.lineup_history_days;
    INSERT INTO site.lineup_history_days (league_id, day, n, correct, perfect, matches)
    SELECT h.league_id, h.day, count(*), sum(h.correct), count(*) FILTER (WHERE h.correct = 11), count(DISTINCT h.fixture_id)
    FROM site.lineup_history h GROUP BY h.league_id, h.day;
    DELETE FROM site.lineup_history_often;
    INSERT INTO site.lineup_history_often (kind, player, league_id, n, pos)
    SELECT u.kind, u.player, h.league_id, count(*), min(ARRAY[pg_catalog.date_part('epoch', h.kickoff)::bigint, h.fixture_id, h.team_id])
    FROM site.lineup_history h,
         LATERAL (SELECT 'missed' AS kind, pg_catalog.unnest(h.missed) AS player
                  UNION ALL SELECT 'wrong', pg_catalog.unnest(h.wrong)) u
    GROUP BY u.kind, u.player, h.league_id;
    ANALYZE site.lineup_history;
    ANALYZE site.lineup_history_teams;
    ANALYZE site.lineup_history_days;
    ANALYZE site.lineup_history_often;
END; $$;
REVOKE ALL ON FUNCTION site.lineup_history_refresh() FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.site_lineup_history(p_days integer DEFAULT NULL, p_leagues integer[] DEFAULT NULL,
                                                      p_limit integer DEFAULT 50) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH since AS (-- the first match date in the range: a match counts from noon on its day
                       SELECT ((pg_catalog.now() AT TIME ZONE 'UTC') - pg_catalog.make_interval(days => p_days) + interval '12 hours'
                               - interval '1 microsecond')::date AS day),
        -- The range's line-ups added up per competition and club, and per competition and match
        -- date: read ready-counted for the whole history, counted from the rows for a range (a
        -- year is under 10,000 of them). Everything below is summed from these, so the whole
        -- history costs no more than a week. pos: a group's first line-up, as an array that sorts
        -- oldest first.
        teams AS (SELECT a.league_id, a.team_id, a.n, a.correct, a.perfect, a.roles_right, a.roles_known, a.counts, a.lines, a.pos
                  FROM site.lineup_history_teams a WHERE p_days IS NULL
                  UNION ALL
                  SELECT h.league_id, h.team_id, count(*)::int, sum(h.correct)::int, (count(*) FILTER (WHERE h.correct = 11))::int,
                         sum(h.roles_right)::int, sum(h.roles_known)::int,
                         ARRAY[count(*) FILTER (WHERE h.correct = 0), count(*) FILTER (WHERE h.correct = 1), count(*) FILTER (WHERE h.correct = 2),
                               count(*) FILTER (WHERE h.correct = 3), count(*) FILTER (WHERE h.correct = 4), count(*) FILTER (WHERE h.correct = 5),
                               count(*) FILTER (WHERE h.correct = 6), count(*) FILTER (WHERE h.correct = 7), count(*) FILTER (WHERE h.correct = 8),
                               count(*) FILTER (WHERE h.correct = 9), count(*) FILTER (WHERE h.correct = 10), count(*) FILTER (WHERE h.correct = 11)]::int[],
                         ARRAY[sum(h.lines[1]), sum(h.lines[2]), sum(h.lines[3]), sum(h.lines[4]), sum(h.lines[5]), sum(h.lines[6]), sum(h.lines[7]), sum(h.lines[8])]::int[],
                         min(ARRAY[pg_catalog.date_part('epoch', h.kickoff)::bigint, h.fixture_id, h.team_id])
                  FROM site.lineup_history h, since WHERE p_days IS NOT NULL AND h.day >= since.day GROUP BY h.league_id, h.team_id),
        days AS (SELECT a.league_id, a.day, a.n, a.correct, a.perfect, a.matches FROM site.lineup_history_days a WHERE p_days IS NULL
                 UNION ALL
                 SELECT h.league_id, h.day, count(*)::int, sum(h.correct)::int, (count(*) FILTER (WHERE h.correct = 11))::int, (count(DISTINCT h.fixture_id))::int
                 FROM site.lineup_history h, since WHERE p_days IS NOT NULL AND h.day >= since.day GROUP BY h.league_id, h.day),
        -- ... and for the chosen competitions (teams itself is the range before the menu, for the menu's counts)
        lt AS (SELECT * FROM teams WHERE p_leagues IS NULL OR teams.league_id = ANY (p_leagues)),
        ld AS (SELECT * FROM days WHERE p_leagues IS NULL OR days.league_id = ANY (p_leagues)),
        t AS (SELECT a.n, a.correct, a.perfect, a.roles_right, a.roles_known, b.matches, b.first, b.last
              FROM (SELECT coalesce(sum(n), 0) AS n, coalesce(sum(correct), 0) AS correct, coalesce(sum(perfect), 0) AS perfect,
                           coalesce(sum(roles_right), 0) AS roles_right, coalesce(sum(roles_known), 0) AS roles_known FROM lt) a,
                   (SELECT coalesce(sum(matches), 0) AS matches, min(day) AS first, max(day) AS last FROM ld) b),
        -- average per day; per week past four weeks, per month past six months
        step AS (SELECT CASE WHEN t.last - t.first > 183 THEN 'month' WHEN t.last - t.first > 28 THEN 'week' ELSE 'day' END AS unit FROM t),
        -- the line-ups listed, newest first
        shown AS (SELECT h.* FROM site.lineup_history h, since
                  WHERE (p_days IS NULL OR h.day >= since.day) AND (p_leagues IS NULL OR h.league_id = ANY (p_leagues))
                  ORDER BY h.kickoff DESC, h.fixture_id DESC, h.team_id DESC
                  LIMIT least(greatest(coalesce(p_limit, 50), 1), 1000)),
        -- the players it got wrong, by competition: ready-counted for the whole history, from the rows for a range
        tally AS (SELECT o.kind, o.player, o.n, o.pos FROM site.lineup_history_often o
                  WHERE p_days IS NULL AND (p_leagues IS NULL OR o.league_id = ANY (p_leagues))
                  UNION ALL
                  SELECT u.kind, u.player, 1, ARRAY[pg_catalog.date_part('epoch', h.kickoff)::bigint, h.fixture_id, h.team_id]
                  FROM site.lineup_history h, since,
                       LATERAL (SELECT 'missed' AS kind, pg_catalog.unnest(h.missed) AS player
                                UNION ALL SELECT 'wrong', pg_catalog.unnest(h.wrong)) u
                  WHERE p_days IS NOT NULL AND h.day >= since.day AND (p_leagues IS NULL OR h.league_id = ANY (p_leagues))),
        -- the ones it got wrong most often (twice or more), each with the club of his first row: the top
        -- 15 by times, with everyone level with the 15th (the page puts those in name order and cuts)
        often AS (SELECT x.kind, x.player, x.n, x.team_id FROM (
                      SELECT g.kind, g.player, g.n, g.team_id, pg_catalog.rank() OVER (PARTITION BY g.kind ORDER BY g.n DESC) AS place
                      FROM (SELECT kind, player, sum(n) AS n, (min(pos))[3]::int AS team_id
                            FROM tally GROUP BY kind, player HAVING sum(n) >= 2) g) x
                  WHERE x.place <= 15),
        club AS (SELECT team_id, sum(n) AS n, sum(correct) AS correct, sum(perfect) AS perfect, min(pos) AS pos FROM lt GROUP BY team_id)
        SELECT pg_catalog.json_build_object(
            'available', true,
            'any', EXISTS (SELECT 1 FROM site.lineup_history),
            'leagues', (SELECT coalesce(pg_catalog.json_agg(x.league_id ORDER BY x.league_id), '[]'::json) FROM (SELECT league_id FROM site.lineup_history_teams GROUP BY league_id) x),
            'scope', (SELECT coalesce(pg_catalog.json_object_agg(x.league_id, x.n), '{}'::json)
                      FROM (SELECT league_id, sum(n) AS n FROM teams GROUP BY league_id) x),
            'total', t.n, 'correct', t.correct, 'perfect', t.perfect, 'roles_right', t.roles_right, 'roles_known', t.roles_known,
            'matches', t.matches, 'first', t.first, 'last', t.last,
            'counts', (SELECT coalesce(pg_catalog.json_object_agg(x.k, x.n), '{}'::json)
                       FROM (SELECT u.i - 1 AS k, sum(u.v) AS n FROM lt, pg_catalog.unnest(lt.counts) WITH ORDINALITY u(v, i)
                             GROUP BY u.i HAVING sum(u.v) > 0) x),
            'step', step.unit,
            'trend', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.k, x.n, x.correct, x.perfect) ORDER BY x.k DESC), '[]'::json)
                      FROM (SELECT pg_catalog.date_trunc(step.unit, l.day::timestamp)::date AS k, sum(l.n) AS n, sum(l.correct) AS correct,
                                   sum(l.perfect) AS perfect
                            FROM ld l GROUP BY 1) x),
            'lines', (SELECT coalesce(pg_catalog.json_agg(x.s ORDER BY x.i), '[null,null,null,null,null,null,null,null]'::json)
                      FROM (SELECT u.i, sum(u.v) AS s FROM lt, pg_catalog.unnest(lt.lines) WITH ORDINALITY u(v, i) GROUP BY u.i) x),
            'comps', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.league_id, x.n, x.correct, x.perfect, x.roles_right, x.roles_known) ORDER BY x.pos), '[]'::json)
                      FROM (SELECT league_id, sum(n) AS n, sum(correct) AS correct, sum(perfect) AS perfect,
                                   sum(roles_right) AS roles_right, sum(roles_known) AS roles_known, min(pos) AS pos FROM lt GROUP BY league_id) x),
            'clubs', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(c.team_id, c.n, c.correct, c.perfect) ORDER BY c.pos), '[]'::json) FROM club c),
            'missed', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(o.player, o.team_id, o.n) ORDER BY o.n DESC, o.player), '[]'::json)
                       FROM often o WHERE o.kind = 'missed'),
            'wrong', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(o.player, o.team_id, o.n) ORDER BY o.n DESC, o.player), '[]'::json)
                      FROM often o WHERE o.kind = 'wrong'),
            'missed_total', (SELECT coalesce(sum(n), 0) FROM tally WHERE kind = 'missed'),
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
            EXECUTE format('REVOKE ALL ON FUNCTION site.lineup_history_refresh() FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_lineup_history(integer, integer[], integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

SELECT site.lineup_history_refresh();       -- count what the last export stored

COMMIT;

-- Check afterwards:
--   select (select count(*) from site.lineup_history_teams), (select count(*) from site.lineup_history_days), (select count(*) from site.lineup_history_often);   -- a few hundred, about 15,000, about 37,000
--   select public.site_lineup_history()::json->>'total';                                   -- 63,369 on 2026-10-05
--   select has_table_privilege('anon', 'site.lineup_history_teams', 'select');             -- f
