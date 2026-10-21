-- Repeatable. Applied 2026-10-21.
-- Every prediction on record (owner, 2026-10-21, T-058: transparency before marketing): every
-- finished club match's prediction as it was locked before kick-off, beside what happened, for
-- anyone to check, filtered by competition, club and dates.
--   site.prediction_record   one row per finished match with a prospective snapshot: the last
--                            one stored before kick-off (match_prediction_snapshots, which the
--                            database keeps append-only), its chances, likely score, when it was
--                            stored and its fingerprint (content_hash), and the score after 90
--                            minutes. Written by the export from the rows the methodology record
--                            already scores (site_record.store_prediction_record), only the rows
--                            that changed. In the site schema, which the Data API doesn't expose.
--   site_prediction_record(...)   for a date range (UTC days, either end open), competitions and
--                            a club: how many, how many right, the average log loss, the first
--                            match on record, the matches per competition in the range (for the
--                            menu), and a page of
--                            rows newest first (at most 500), with the names of the clubs in them.
-- Fixed SQL, definer's rights with an empty search path. About 300 bytes a match with its
-- indexes (30,000 made-up rows on staging, in a transaction rolled back: 9 MB; a page in 27 to
-- 77 ms, about 24 KB): about 7 MB a season at today's rate. The nightly writes only the day's new
-- matches. Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS site.prediction_record (
    fixture_id integer PRIMARY KEY,
    kickoff timestamptz NOT NULL,
    league_id integer NOT NULL,
    home_id integer NOT NULL,
    away_id integer NOT NULL,
    p_home real NOT NULL,
    p_draw real NOT NULL,
    p_away real NOT NULL,
    likely text,                             -- the single most likely score
    home_xg real NOT NULL,
    away_xg real NOT NULL,
    hg smallint NOT NULL,                    -- the score after 90 minutes
    ag smallint NOT NULL,
    outcome smallint NOT NULL,               -- 0 home win, 1 draw, 2 away win
    right_call boolean NOT NULL,             -- the outcome given the highest chance happened
    log_loss real NOT NULL,                  -- minus the log of the chance given to what happened
    captured_at timestamptz NOT NULL,        -- when the prediction was stored
    version text NOT NULL,                   -- the model version that made it
    hash text NOT NULL                       -- the snapshot's content_hash
);
CREATE INDEX IF NOT EXISTS prediction_record_kickoff_idx ON site.prediction_record (kickoff);
CREATE INDEX IF NOT EXISTS prediction_record_home_idx ON site.prediction_record (home_id, kickoff);
CREATE INDEX IF NOT EXISTS prediction_record_away_idx ON site.prediction_record (away_id, kickoff);
ALTER TABLE site.prediction_record ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.prediction_record FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.site_prediction_record(p_from date DEFAULT NULL, p_to date DEFAULT NULL,
    p_leagues integer[] DEFAULT NULL, p_team integer DEFAULT NULL, p_limit integer DEFAULT 100,
    p_offset integer DEFAULT 0) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
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

REVOKE ALL ON FUNCTION public.site_prediction_record(date, date, integer[], integer, integer, integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON site.prediction_record FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_prediction_record(date, date, integer[], integer, integer, integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards (after the next nightly run):
--   select count(*), min(kickoff), max(kickoff) from site.prediction_record;    -- every scored match since 26 September
--   select public.site_prediction_record(p_limit => 3)::json->'rows';           -- the three latest
