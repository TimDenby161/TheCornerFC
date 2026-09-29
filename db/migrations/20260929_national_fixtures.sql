-- Additive and repeatable. National team matches from API-Football (config.NATIONAL_TEAM_LEAGUES),
-- for the Nations ranking (nations.py), which adds them to the public results dataset where it
-- doesn't have them yet. Kept apart from fixtures: every club model reads all of fixtures.
-- Team names are stored as sent, since national teams aren't in teams.
CREATE TABLE IF NOT EXISTS national_fixtures (
    fixture_id    integer PRIMARY KEY,
    league_id     integer NOT NULL,
    season        integer NOT NULL,
    tournament    text,               -- API-Football's competition name
    round         text,
    kickoff       timestamptz,
    venue_name    text,
    venue_city    text,
    status_short  text,
    home_team_id  integer NOT NULL,
    away_team_id  integer NOT NULL,
    home_name     text NOT NULL,
    away_name     text NOT NULL,
    home_goals    integer,            -- after extra time, before penalties
    away_goals    integer,
    neutral       boolean,            -- null: not known (nations.py assumes finals are neutral)
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS national_fixtures_kickoff ON national_fixtures (kickoff);
ALTER TABLE national_fixtures ENABLE ROW LEVEL SECURITY;
