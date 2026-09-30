-- Additive and repeatable. FPL's penalties_order for each player (1 = first choice), an input to
-- fantasy v1.5's penalty takers (owner approved this use of FPL data on 2026-09-30). Apply BEFORE
-- deploying the fpl.py change: store_capture writes this column.
ALTER TABLE fpl_player_states ADD COLUMN IF NOT EXISTS penalties_order smallint;
