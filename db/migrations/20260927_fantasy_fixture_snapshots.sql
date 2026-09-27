-- Fantasy model output per team-fixture, keyed by API-Football ids (no FPL data needed). Requires
-- model_versions. Additive: nothing existing is modified. Written by thecornerfc.fantasy_snapshots.
-- fantasy_prediction_snapshots (FPL ids, per gameweek) stays for when FPL capture is licensed.
CREATE TABLE IF NOT EXISTS fantasy_fixture_snapshots (
    snapshot_id bigserial PRIMARY KEY,
    fixture_id integer NOT NULL,
    team_id integer NOT NULL,
    model_version_id text NOT NULL REFERENCES model_versions(model_version_id) ON DELETE RESTRICT,
    source text NOT NULL CHECK(source IN ('prospective','late_observation')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,          -- kickoff
    seconds_to_kickoff double precision NOT NULL,
    predictions jsonb NOT NULL CHECK(jsonb_typeof(predictions)='array'),  -- per player: every component
    inputs jsonb NOT NULL CHECK(jsonb_typeof(inputs)='object'),            -- team goals, availability, benchmarks
    content_hash text NOT NULL,
    CHECK(source <> 'prospective' OR (captured_at < effective_at AND created_at < effective_at)),
    UNIQUE(fixture_id,team_id,model_version_id,source,content_hash)
);
CREATE INDEX IF NOT EXISTS fantasy_fixture_snapshots_idx ON fantasy_fixture_snapshots(fixture_id,team_id,captured_at);
CREATE OR REPLACE FUNCTION guard_fantasy_fixture_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Fantasy snapshots are append only';
    END IF;
    NEW.created_at := clock_timestamp();
    IF NOT EXISTS (SELECT 1 FROM model_versions WHERE model_version_id=NEW.model_version_id AND model_type='fantasy') THEN
        RAISE EXCEPTION 'Fantasy snapshots require a fantasy model version';
    END IF;
    IF NEW.captured_at>=NEW.effective_at OR NEW.created_at>=NEW.effective_at THEN
        NEW.source := 'late_observation';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS fantasy_fixture_snapshot_guard ON fantasy_fixture_snapshots;
CREATE TRIGGER fantasy_fixture_snapshot_guard BEFORE INSERT OR UPDATE OR DELETE ON fantasy_fixture_snapshots
FOR EACH ROW EXECUTE FUNCTION guard_fantasy_fixture_snapshot();
DROP TRIGGER IF EXISTS fantasy_fixture_snapshot_truncate_guard ON fantasy_fixture_snapshots;
CREATE TRIGGER fantasy_fixture_snapshot_truncate_guard BEFORE TRUNCATE ON fantasy_fixture_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION guard_fantasy_fixture_snapshot();
ALTER TABLE fantasy_fixture_snapshots ENABLE ROW LEVEL SECURITY;
