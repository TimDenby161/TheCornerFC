-- Additive and repeatable. The predicted XI the nightly player-ratings replay works out for every
-- finished match, from what it knew before kick-off; rebuilt each run. Not captured evidence:
-- the live record stays in lineup_prediction_snapshots.
CREATE TABLE IF NOT EXISTS reconstructed_lineups (
    fixture_id integer NOT NULL,
    team_id integer NOT NULL,
    players integer[] NOT NULL,   -- the predicted XI, in slot order
    roles text[] NOT NULL,        -- each one's predicted role, same order
    PRIMARY KEY (fixture_id, team_id)
);
ALTER TABLE reconstructed_lineups ENABLE ROW LEVEL SECURITY;
