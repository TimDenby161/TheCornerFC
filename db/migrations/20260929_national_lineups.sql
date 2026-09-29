-- Additive and repeatable. Starting XIs, formations and coaches for national_fixtures
-- (ingest.sync_national_lineups), as fixture_lineups and fixture_formations hold them for clubs.
-- Own tables: the club models read every row of those two.
ALTER TABLE national_fixtures ADD COLUMN IF NOT EXISTS players_fetched_at timestamptz;
CREATE TABLE IF NOT EXISTS national_fixture_formations (
    fixture_id  integer NOT NULL,
    team_id     integer NOT NULL,
    formation   text,
    coach_id    integer,              -- the manager on the line-up
    PRIMARY KEY (fixture_id, team_id)
);
CREATE TABLE IF NOT EXISTS national_fixture_lineups (
    fixture_id  integer NOT NULL,
    team_id     integer NOT NULL,
    player_id   integer NOT NULL,
    grid        text,
    role        text,
    PRIMARY KEY (fixture_id, player_id)
);
CREATE INDEX IF NOT EXISTS national_fixture_lineups_player ON national_fixture_lineups (player_id);
ALTER TABLE national_fixture_formations ENABLE ROW LEVEL SECURITY;
ALTER TABLE national_fixture_lineups ENABLE ROW LEVEL SECURITY;
