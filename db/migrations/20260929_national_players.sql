-- Additive and repeatable. Each player's stat line in national_fixtures matches, and the coach's
-- and players' names (ingest.sync_national_lineups), for the nation page's Players and Formations
-- tabs. Own table, as fixture_players is for clubs: the player ratings read every row of that one.
ALTER TABLE national_fixture_formations ADD COLUMN IF NOT EXISTS coach_name text;
ALTER TABLE national_fixture_lineups ADD COLUMN IF NOT EXISTS player_name text;
CREATE TABLE IF NOT EXISTS national_fixture_players (LIKE fixture_players INCLUDING DEFAULTS);
ALTER TABLE national_fixture_players ADD COLUMN IF NOT EXISTS player_name text;  -- as sent: not every international is in players
CREATE UNIQUE INDEX IF NOT EXISTS national_fixture_players_key ON national_fixture_players (fixture_id, player_id);
CREATE INDEX IF NOT EXISTS national_fixture_players_team ON national_fixture_players (team_id, fixture_id);
ALTER TABLE national_fixture_players ENABLE ROW LEVEL SECURITY;
-- Matches whose line-ups were fetched before this table existed: fetch them once more (20 per
-- call) for their stat lines and names. A rerun only refetches matches that never had any.
UPDATE national_fixtures nf SET players_fetched_at = NULL
WHERE players_fetched_at IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM national_fixture_players p WHERE p.fixture_id = nf.fixture_id);
