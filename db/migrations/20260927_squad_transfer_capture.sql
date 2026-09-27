-- Prospective capture for protocols P1/P2 (experiments/prospective/PROTOCOLS.md). Additive only:
-- new append-only tables and nullable columns; no existing rows are rewritten.
-- Dated registered squads: one row whenever a club's /players/squads list changes.
CREATE TABLE IF NOT EXISTS squad_snapshots (
    snapshot_id bigserial PRIMARY KEY,
    team_id integer NOT NULL,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    players jsonb NOT NULL CHECK(jsonb_typeof(players)='array'), -- API ids plus the mapped match-data id
    content_hash text NOT NULL
);
CREATE INDEX IF NOT EXISTS squad_snapshots_team_idx ON squad_snapshots(team_id,captured_at DESC);
-- Verified transfer events as reported by /transfers; identical reports are stored once.
CREATE TABLE IF NOT EXISTS transfer_observations (
    observation_id bigserial PRIMARY KEY,
    player_id integer NOT NULL, -- API-Football player id
    player_name text,
    transfer_date date,
    transfer_type text,
    team_in integer,
    team_out integer,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    content_hash text NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS transfer_observations_player_idx ON transfer_observations(player_id,transfer_date);
-- One row per /transfers?team= request, so unchanged squads are not re-fetched.
CREATE TABLE IF NOT EXISTS transfer_fetches (
    team_id integer NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    records integer NOT NULL
);
CREATE INDEX IF NOT EXISTS transfer_fetches_team_idx ON transfer_fetches(team_id,fetched_at DESC);
CREATE OR REPLACE FUNCTION guard_squad_transfer_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Squad and transfer evidence is append only';
    END IF;
    IF TG_TABLE_NAME IN ('squad_snapshots','transfer_observations') THEN
        NEW.created_at := clock_timestamp();
    END IF;
    RETURN NEW;
END;
$$;
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['squad_snapshots','transfer_observations','transfer_fetches'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS squad_transfer_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER squad_transfer_guard BEFORE INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION guard_squad_transfer_evidence()',t);
        EXECUTE format('DROP TRIGGER IF EXISTS squad_transfer_truncate_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER squad_transfer_truncate_guard BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION guard_squad_transfer_evidence()',t);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    END LOOP;
END; $$;
-- Rating components for each daily player capture (NULL for captures before 2026-09-27):
-- rolling stat percentile, the window's minutes-weighted club rank, the rolling club-scaled
-- rating, and the same formula with club strength fixed at 1000 (club-neutral).
ALTER TABLE player_rating_history ADD COLUMN IF NOT EXISTS stat_percentile double precision;
ALTER TABLE player_rating_history ADD COLUMN IF NOT EXISTS window_club_rank double precision;
ALTER TABLE player_rating_history ADD COLUMN IF NOT EXISTS window_rating numeric(4,1);
ALTER TABLE player_rating_history ADD COLUMN IF NOT EXISTS neutral_rating numeric(4,1);
