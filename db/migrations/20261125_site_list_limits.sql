-- Repeatable. Not yet applied.
-- The four public site functions that take lists answer nothing when a list is far longer than
-- any page sends (T-098, owner's go-ahead 2026-11-25): anyone holding the public key can call
-- them straight at Supabase, past the site's kept answers, and a huge list makes every row's
-- check expensive until the role's statement timeout (anon 3 s, authenticated 8 s, read
-- 2026-11-25). Limits: 2,000 player or club ids (the site sends at most 1,000 players, and the
-- cup filter every club still in a cup), 500 leagues, nations, positions or groups, 40 search
-- words (the site cuts a search to 80 characters) of 100,000 bytes in all, 200 characters of
-- search text, 10 values in a range.
-- Each function is otherwise word for word the version live on 2026-11-25 (checked against
-- staging and production), the check added as the first statement of its body. CREATE OR
-- REPLACE keeps each function's owner and grants. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_players(
    p_ids integer[] DEFAULT NULL, p_leagues integer[] DEFAULT NULL, p_teams integer[] DEFAULT NULL,
    p_nats text[] DEFAULT NULL, p_not_leagues integer[] DEFAULT NULL, p_positions text[] DEFAULT NULL,
    p_age integer[] DEFAULT NULL, p_ab integer[] DEFAULT NULL, p_crank integer[] DEFAULT NULL,
    p_mins integer[] DEFAULT NULL, p_q text DEFAULT NULL, p_words text[] DEFAULT NULL,
    p_sort text DEFAULT 's0', p_groups text[] DEFAULT NULL, p_limit integer DEFAULT 100,
    p_offset integer DEFAULT 0, p_count boolean DEFAULT false) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    sort_key text := CASE WHEN p_sort IN ('age', 'ga', 'pos', 'k_finishing', 'k_creating', 'k_passing', 'k_dribbling',
                                          'k_ball_winning', 'k_duels', 'k_solidity',
                                          'k_shot_stopping', 'k_goals_prevented', 'k_distribution')
                               OR p_sort ~ '^[sf][0-9]{1,2}$' THEN p_sort ELSE 's0' END;
    sort_at integer := CASE WHEN sort_key ~ '^[sf][0-9]' THEN pg_catalog.substr(sort_key, 2)::integer + 1 END;
    whole boolean := site.entitled();
BEGIN
    -- T-098: lists past any real page's size are answered with nothing (the site sends at most 1,000 ids)
    IF coalesce(pg_catalog.cardinality(p_ids), 0) > 2000
       OR coalesce(pg_catalog.cardinality(p_leagues), 0) > 500 OR coalesce(pg_catalog.cardinality(p_teams), 0) > 2000
       OR coalesce(pg_catalog.cardinality(p_nats), 0) > 500 OR coalesce(pg_catalog.cardinality(p_not_leagues), 0) > 500
       OR coalesce(pg_catalog.cardinality(p_positions), 0) > 500 OR coalesce(pg_catalog.cardinality(p_groups), 0) > 500
       OR coalesce(pg_catalog.cardinality(p_words), 0) > 40 OR coalesce(pg_catalog.octet_length(p_words::text), 0) > 100000
       OR coalesce(pg_catalog.length(p_q), 0) > 200
       OR coalesce(pg_catalog.cardinality(p_age), 0) > 10 OR coalesce(pg_catalog.cardinality(p_ab), 0) > 10
       OR coalesce(pg_catalog.cardinality(p_crank), 0) > 10 OR coalesce(pg_catalog.cardinality(p_mins), 0) > 10 THEN
        RETURN NULL;
    END IF;
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH fit AS MATERIALIZED (
            SELECT p.league_id, p.team_id, p.name_lc,
                   -- a player outside the free slice, for anyone not entitled: his blanked row, in
                   -- the place the sort gives him (the order is a subscriber's, the ranks are hidden)
                   p.ord,
                   -- a player in the free slice, for anyone not entitled: his whole row but his skill
                   -- scores, the row's last field (export.SITE_PLAYER_FIELDS), which are for subscribers
                   CASE WHEN whole THEN p.data
                        WHEN p.free THEN ((p.data::jsonb - (pg_catalog.jsonb_array_length(p.data::jsonb) - 1)) || 'null'::jsonb)::json
                        ELSE p.data_free END AS data,
                   CASE WHEN sort_key = 'age' THEN -p.age::double precision
                        WHEN sort_key = 'ga' THEN p.ga
                        WHEN sort_key = 'pos' THEN (SELECT max((p.pos_ranks->>g.g)::double precision) FROM pg_catalog.unnest(p_groups) g(g))
                        WHEN pg_catalog.left(sort_key, 2) = 'k_' THEN (p.skills->>pg_catalog.substr(sort_key, 3))::double precision
                        WHEN pg_catalog.left(sort_key, 1) = 's' THEN p.seasons[sort_at]
                        ELSE p.future[sort_at] END AS v
            FROM site.players p
            WHERE (whole OR p.free OR p.data_free IS NOT NULL)      -- never the whole row for want of a blanked one
              AND (p_ids IS NULL OR p.player_id = ANY (p_ids))
              AND (p_leagues IS NULL OR p.league_id = ANY (p_leagues))
              AND (p_teams IS NULL OR p.team_id = ANY (p_teams))
              AND (p_nats IS NULL OR p.nationality = ANY (p_nats))
              AND (p_not_leagues IS NULL OR p.league_id IS NULL OR p.league_id <> ALL (p_not_leagues))
              AND (p_positions IS NULL OR p.plays && p_positions)
              AND (p_age IS NULL OR (p_age[1] IS NULL AND p_age[2] IS NULL)
                   OR (p.age IS NOT NULL AND (p_age[1] IS NULL OR p.age >= p_age[1]) AND (p_age[2] IS NULL OR p.age <= p_age[2])))
              AND (p_ab IS NULL OR (p_ab[1] IS NULL AND p_ab[2] IS NULL)
                   OR ((whole OR p.free) AND p.ability IS NOT NULL AND (p_ab[1] IS NULL OR p.ability >= p_ab[1]) AND (p_ab[2] IS NULL OR p.ability <= p_ab[2])))
              AND (p_crank IS NULL OR (p_crank[1] IS NULL AND p_crank[2] IS NULL)
                   OR (p.club_world IS NOT NULL AND (p_crank[1] IS NULL OR p.club_world >= p_crank[1]) AND (p_crank[2] IS NULL OR p.club_world <= p_crank[2])))
              AND (p_mins IS NULL OR (p_mins[1] IS NULL AND p_mins[2] IS NULL)
                   OR (p.minutes IS NOT NULL AND (p_mins[1] IS NULL OR p.minutes >= p_mins[1]) AND (p_mins[2] IS NULL OR p.minutes <= p_mins[2])))
              AND (p_q IS NULL OR pg_catalog.strpos(p.name_lc, p_q) > 0
                   OR (coalesce(pg_catalog.cardinality(p_words), 0) > 0 AND NOT EXISTS (
                           SELECT 1 FROM pg_catalog.unnest(p_words) w(w)
                           WHERE NOT (pg_catalog.strpos(' ' || p.name_fold, ' ' || pg_catalog.split_part(w.w, '|', 1)) > 0
                                      OR CASE WHEN p.team_id IS NULL THEN pg_catalog.split_part(w.w, '|', 2) = '1'
                                              ELSE p.team_id::text = ANY (pg_catalog.string_to_array(pg_catalog.split_part(w.w, '|', 3), ',')) END))))
        )
        SELECT CASE WHEN p_count THEN pg_catalog.json_build_object(
                   'counts', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(c.league_id, c.team_id, c.n)), '[]'::json)
                              FROM (SELECT f.league_id, f.team_id, count(*) AS n FROM fit f GROUP BY 1, 2) c))
               ELSE pg_catalog.json_build_object(
                   'total', (SELECT count(*) FROM fit),
                   'paywall', NOT whole,
                   'rows', (SELECT coalesce(pg_catalog.json_agg(r.data ORDER BY r.v DESC NULLS LAST, r.ord, r.name_lc), '[]'::json)
                            FROM (SELECT f.data, f.v, f.ord, f.name_lc FROM fit f ORDER BY f.v DESC NULLS LAST, f.ord, f.name_lc
                                  LIMIT least(greatest(coalesce(p_limit, 100), 0), 2000) OFFSET greatest(coalesce(p_offset, 0), 0)) r))
               END
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_matches(p_from timestamptz DEFAULT NULL, p_to timestamptz DEFAULT NULL,
                                               p_leagues integer[] DEFAULT NULL, p_team integer DEFAULT NULL,
                                               p_ids integer[] DEFAULT NULL) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    whole boolean := site.entitled();
    soon timestamptz := pg_catalog.now() + interval '7 days';
BEGIN
    -- T-098: lists past any real page's size are answered with nothing
    IF coalesce(pg_catalog.cardinality(p_ids), 0) > 2000 OR coalesce(pg_catalog.cardinality(p_leagues), 0) > 500 THEN
        RETURN NULL;
    END IF;
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'matches', coalesce(pg_catalog.json_agg(x.data ORDER BY x.kickoff, x.fixture_id), '[]'::json),
            'reasons', coalesce(pg_catalog.json_object_agg(x.fixture_id, x.reasons) FILTER (WHERE x.reasons IS NOT NULL), '{}'::json),
            'paywall', NOT whole)
        FROM (SELECT m.fixture_id, m.kickoff,
                     CASE WHEN whole OR m.kickoff <= pg_catalog.now() THEN m.data
                          WHEN m.kickoff <= soon THEN coalesce(m.data_free, m.data_locked)
                          -- a league with nothing in the next 7 days: its next round is free
                          WHEN (SELECT n.kickoff FROM site.matches n
                                WHERE n.league_id = m.league_id AND n.kickoff > pg_catalog.now()
                                ORDER BY n.kickoff LIMIT 1) > soon
                               AND m.kickoff <= (SELECT n.kickoff FROM site.matches n
                                                WHERE n.league_id = m.league_id AND n.kickoff > pg_catalog.now()
                                                ORDER BY n.kickoff LIMIT 1) + interval '4 days'
                               THEN coalesce(m.data_free, m.data_locked)
                          ELSE m.data_locked END AS data,
                     CASE WHEN whole OR m.kickoff <= pg_catalog.now() THEN m.reasons END AS reasons
              FROM site.matches m
              WHERE (p_from IS NOT NULL OR p_to IS NOT NULL OR p_leagues IS NOT NULL OR p_team IS NOT NULL OR p_ids IS NOT NULL)
                AND (p_from IS NULL OR m.kickoff >= p_from) AND (p_to IS NULL OR m.kickoff < p_to)
                AND (p_leagues IS NULL OR m.league_id = ANY (p_leagues))
                AND (p_team IS NULL OR m.home_id = p_team OR m.away_id = p_team)
                AND (p_ids IS NULL OR m.fixture_id = ANY (p_ids))
                -- a row the export hasn't given its blanked copies yet is left out for the
                -- unentitled, not shown whole
                AND (whole OR m.kickoff <= pg_catalog.now() OR m.data_locked IS NOT NULL)
              ORDER BY m.kickoff, m.fixture_id LIMIT 2000) x
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_prediction_record(p_from date DEFAULT NULL, p_to date DEFAULT NULL,
    p_leagues integer[] DEFAULT NULL, p_team integer DEFAULT NULL, p_limit integer DEFAULT 100,
    p_offset integer DEFAULT 0) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    -- T-098: lists past any real page's size are answered with nothing
    IF coalesce(pg_catalog.cardinality(p_leagues), 0) > 500 THEN
        RETURN NULL;
    END IF;
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH scope AS MATERIALIZED (
            SELECT * FROM site.prediction_record r
            WHERE (p_from IS NULL OR r.kickoff >= p_from::timestamp AT TIME ZONE 'UTC')
              AND (p_to IS NULL OR r.kickoff < (p_to + 1)::timestamp AT TIME ZONE 'UTC')
              AND (p_team IS NULL OR r.home_id = p_team OR r.away_id = p_team)),
        list AS MATERIALIZED (SELECT * FROM scope s WHERE p_leagues IS NULL OR s.league_id = ANY (p_leagues)),
        shown AS (SELECT * FROM list l ORDER BY l.kickoff DESC, l.fixture_id DESC
                  LIMIT least(greatest(coalesce(p_limit, 100), 0), 500) OFFSET greatest(coalesce(p_offset, 0), 0))
        SELECT pg_catalog.json_build_object(
            'any', EXISTS (SELECT 1 FROM site.prediction_record),
            'since', (SELECT min(r.kickoff) FROM site.prediction_record r),      -- where the month menu starts
            'total', (SELECT count(*) FROM list),
            'right', (SELECT count(*) FILTER (WHERE l.right_call) FROM list l),
            'log_loss', (SELECT pg_catalog.round(avg(l.log_loss)::numeric, 4) FROM list l),
            'first', (SELECT min(l.kickoff) FROM list l),
            'last', (SELECT max(l.kickoff) FROM list l),
            -- matches per competition in the range and for the club, before the competition filter
            'comps', (SELECT coalesce(pg_catalog.json_object_agg(x.league_id, x.n), '{}'::json)
                      FROM (SELECT s.league_id, count(*) AS n FROM scope s GROUP BY s.league_id) x),
            -- [fixture, kickoff, competition, home, away, p_home, p_draw, p_away, likely, home_xg,
            --  away_xg, home goals, away goals, outcome, right, log loss, stored at, version, hash]
            'rows', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(s.fixture_id, s.kickoff, s.league_id, s.home_id, s.away_id,
                                                                                    s.p_home, s.p_draw, s.p_away, s.likely, s.home_xg, s.away_xg,
                                                                                    s.hg, s.ag, s.outcome, s.right_call, s.log_loss,
                                                                                    s.captured_at, s.version, s.hash)
                                                         ORDER BY s.kickoff DESC, s.fixture_id DESC), '[]'::json) FROM shown s),
            -- names for the clubs above, and no others
            'teams', (SELECT coalesce(pg_catalog.json_object_agg(t.team_id, t.name), '{}'::json) FROM public.teams t
                      WHERE t.team_id IN (SELECT s.home_id FROM shown s UNION SELECT s.away_id FROM shown s UNION SELECT p_team)))
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_lineup_history(p_days integer DEFAULT NULL, p_leagues integer[] DEFAULT NULL,
                                                      p_limit integer DEFAULT 50) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    -- T-098: lists past any real page's size are answered with nothing
    IF coalesce(pg_catalog.cardinality(p_leagues), 0) > 500 THEN
        RETURN NULL;
    END IF;
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

COMMIT;
