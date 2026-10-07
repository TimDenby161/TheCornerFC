-- Additive and repeatable. Applied 2026-10-07. Projected scores and win/draw/loss chances for national team matches
-- (thecornerfc/national_predictions.py), so the Matches tab shows internationals as it shows club
-- matches (owner, 2026-10-07). Own table, as national_fixtures is: the stats, the paper bets and
-- the prediction ratings read every row of fixture_predictions. Written by the nightly run for
-- matches that haven't kicked off; a match's row is left alone after that, apart from its rating.
-- Until this is applied the nightly run logs that it skipped the projections and the site shows
-- internationals as before. Also in db/schema.sql.
CREATE TABLE IF NOT EXISTS national_fixture_predictions (
    fixture_id          integer PRIMARY KEY,
    kickoff             timestamptz,
    league_id           integer,
    home_team_id        integer,
    away_team_id        integer,
    home_rank           double precision,   -- national team Elo (nations.py) when projected
    away_rank           double precision,
    neutral             boolean,            -- no home advantage counted
    exp_diff            double precision,   -- expected goal difference (home - away)
    home_xg             double precision,   -- projected home goals
    away_xg             double precision,
    p_home              double precision,
    p_draw              double precision,
    p_away              double precision,
    likely_score        text,
    p_over25            double precision,
    p_btts              double precision,
    -- 1-5 grade of the projection once the match is finished, and its factor scores (rating.py)
    rating              smallint,
    rating_winner       smallint,
    rating_margin       smallint,
    rating_clean_sheets smallint,
    rating_shape        smallint,
    rating_goals        smallint,
    updated_at          timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE national_fixture_predictions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON national_fixture_predictions FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON national_fixture_predictions FROM %I', r);
        END IF;
    END LOOP;
END; $$;

-- Check afterwards:
--   select has_table_privilege('anon', 'national_fixture_predictions', 'select');   -- f
--   select count(*) from national_fixture_predictions;                              -- 0 until the next nightly run
