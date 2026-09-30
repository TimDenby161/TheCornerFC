-- Additive and repeatable. Penalties won, scored and missed in each player's match line
-- (API-Football /fixtures penalty.*), for fantasy v1.5's penalty takers. Apply BEFORE deploying the
-- ingest change: _player_lines writes these columns to both tables.
ALTER TABLE fixture_players ADD COLUMN IF NOT EXISTS penalties_won smallint;
ALTER TABLE fixture_players ADD COLUMN IF NOT EXISTS penalties_scored smallint;
ALTER TABLE fixture_players ADD COLUMN IF NOT EXISTS penalties_missed smallint;
ALTER TABLE national_fixture_players ADD COLUMN IF NOT EXISTS penalties_won smallint;
ALTER TABLE national_fixture_players ADD COLUMN IF NOT EXISTS penalties_scored smallint;
ALTER TABLE national_fixture_players ADD COLUMN IF NOT EXISTS penalties_missed smallint;
-- Backfill: Premier League matches since 2024-25 fetched before these columns existed are fetched
-- once more by the nightly sync_fixture_players (20 per call, ~45 calls). A rerun only refetches
-- matches that still have no penalty data at all.
UPDATE fixtures f SET players_fetched_at = NULL
WHERE f.league_id = 39 AND f.kickoff >= '2024-07-01' AND f.players_fetched_at IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM fixture_players p
                  WHERE p.fixture_id = f.fixture_id AND p.penalties_scored IS NOT NULL);
