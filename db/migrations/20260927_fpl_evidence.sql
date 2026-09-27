-- Fantasy Premier League evidence for future fantasy-model validation. Requires model_versions.
-- Additive and repeatable; nothing existing is modified. No fantasy model reads these tables yet.
-- Source licensing: README "Fantasy Premier League evidence". Capture is off unless FPL_CAPTURE_ENABLED.
-- Seasons are keyed by start year, as API-Football (2026 = 2026/27). FPL ids are per season.

-- Gameweek deadlines as observed. A moved deadline appends a row; the old one stays.
CREATE TABLE IF NOT EXISTS fpl_gameweeks (
    season integer NOT NULL,
    event_id integer NOT NULL,                  -- FPL gameweek number
    name text,
    deadline timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    first_captured_at timestamptz NOT NULL,
    PRIMARY KEY (season, event_id, deadline)
);
-- Pre-deadline source state: one header per distinct state of the next gameweek's inputs.
CREATE TABLE IF NOT EXISTS fpl_captures (
    capture_id bigserial PRIMARY KEY,
    season integer NOT NULL,
    event_id integer NOT NULL,                  -- next gameweek whose deadline had not passed
    source text NOT NULL CHECK(source IN ('prospective','late_observation')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,          -- that gameweek's deadline as observed
    seconds_to_deadline double precision NOT NULL,
    fixtures jsonb NOT NULL CHECK(jsonb_typeof(fixtures)='array'),  -- schedule known at capture
    player_count integer NOT NULL,
    content_hash text NOT NULL,
    CHECK(source <> 'prospective' OR (captured_at < effective_at AND created_at < effective_at))
);
CREATE INDEX IF NOT EXISTS fpl_captures_event_idx ON fpl_captures(season,event_id,captured_at DESC);
CREATE TABLE IF NOT EXISTS fpl_player_states (
    capture_id bigint NOT NULL REFERENCES fpl_captures(capture_id) ON DELETE RESTRICT,
    fpl_player_id integer NOT NULL,             -- FPL element id (this season only)
    fpl_code integer,                           -- FPL player code (stable across seasons)
    web_name text,
    fpl_team_id integer,
    element_type smallint,
    position text,                              -- FPL's own short label for element_type
    price_tenths integer,                       -- now_cost: 55 = 5.5m
    status text,                                -- FPL code as given (a, d, i, s, u, n)
    chance_this_round smallint,
    chance_next_round smallint,
    news text,
    news_added timestamptz,
    PRIMARY KEY (capture_id, fpl_player_id)
);
-- FPL team/player -> API-Football id. A changed mapping appends a row; unmatched stays NULL.
CREATE TABLE IF NOT EXISTS fpl_id_map (
    map_id bigserial PRIMARY KEY,
    kind text NOT NULL CHECK(kind IN ('team','player')),
    season integer NOT NULL,
    fpl_id integer NOT NULL,
    fpl_code integer,
    api_id integer,
    method text NOT NULL,
    detail jsonb NOT NULL CHECK(jsonb_typeof(detail)='object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    content_hash text NOT NULL,
    CHECK((api_id IS NULL) = (method IN ('unmatched','ambiguous')))
);
CREATE INDEX IF NOT EXISTS fpl_id_map_idx ON fpl_id_map(kind,season,fpl_id,captured_at DESC);
-- Actual points as observed after a gameweek. Bonus/correction changes append a new state.
CREATE TABLE IF NOT EXISTS fpl_result_captures (
    result_capture_id bigserial PRIMARY KEY,
    season integer NOT NULL,
    event_id integer NOT NULL,
    finished boolean NOT NULL,
    data_checked boolean NOT NULL,              -- FPL marks the gameweek's points final
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    player_count integer NOT NULL,
    content_hash text NOT NULL
);
CREATE INDEX IF NOT EXISTS fpl_result_captures_event_idx ON fpl_result_captures(season,event_id,captured_at DESC);
CREATE TABLE IF NOT EXISTS fpl_player_results (
    result_capture_id bigint NOT NULL REFERENCES fpl_result_captures(result_capture_id) ON DELETE RESTRICT,
    fpl_player_id integer NOT NULL,
    total_points integer NOT NULL,
    minutes integer,
    stats jsonb NOT NULL CHECK(jsonb_typeof(stats)='object'),
    explain jsonb NOT NULL CHECK(jsonb_typeof(explain)='array'),  -- per fixture (double gameweeks)
    PRIMARY KEY (result_capture_id, fpl_player_id)
);
-- Fantasy model outputs. No model writes here yet; see thecornerfc.fpl.make_prediction_snapshot.
CREATE TABLE IF NOT EXISTS fantasy_prediction_snapshots (
    snapshot_id bigserial PRIMARY KEY,
    season integer NOT NULL,
    event_id integer NOT NULL,
    model_version_id text NOT NULL REFERENCES model_versions(model_version_id) ON DELETE RESTRICT,
    input_capture_id bigint REFERENCES fpl_captures(capture_id) ON DELETE RESTRICT,
    source text NOT NULL CHECK(source IN ('prospective','reconstruction','late_observation')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    captured_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,          -- deadline
    seconds_to_deadline double precision NOT NULL,
    predictions jsonb NOT NULL CHECK(jsonb_typeof(predictions)='array'),
    inputs jsonb NOT NULL CHECK(jsonb_typeof(inputs)='object'),
    content_hash text NOT NULL,
    CHECK(source <> 'prospective' OR (input_capture_id IS NOT NULL
          AND captured_at < effective_at AND created_at < effective_at)),
    UNIQUE(season,event_id,model_version_id,source,content_hash)
);
CREATE INDEX IF NOT EXISTS fantasy_snapshots_event_idx ON fantasy_prediction_snapshots(season,event_id,captured_at);
CREATE OR REPLACE FUNCTION guard_fpl_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE input record;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Fantasy evidence is append only';
    END IF;
    IF TG_TABLE_NAME IN ('fpl_player_states','fpl_player_results') THEN
        RETURN NEW;
    END IF;
    NEW.created_at := clock_timestamp();
    IF TG_TABLE_NAME = 'fpl_captures' AND NEW.source = 'prospective'
       AND (NEW.captured_at >= NEW.effective_at OR NEW.created_at >= NEW.effective_at) THEN
        NEW.source := 'late_observation';
    END IF;
    IF TG_TABLE_NAME = 'fantasy_prediction_snapshots' THEN
        IF NOT EXISTS (SELECT 1 FROM model_versions WHERE model_version_id=NEW.model_version_id AND model_type='fantasy') THEN
            RAISE EXCEPTION 'Fantasy predictions require a fantasy model version';
        END IF;
        IF NEW.input_capture_id IS NOT NULL THEN
            SELECT season, event_id, captured_at INTO input FROM fpl_captures WHERE capture_id=NEW.input_capture_id;
            IF input.season <> NEW.season OR input.event_id <> NEW.event_id THEN
                RAISE EXCEPTION 'Input capture is for a different gameweek';
            END IF;
            IF input.captured_at > NEW.captured_at THEN
                RAISE EXCEPTION 'Input capture was observed after the prediction';
            END IF;
        END IF;
        IF NEW.source = 'prospective' AND (NEW.captured_at >= NEW.effective_at OR NEW.created_at >= NEW.effective_at) THEN
            NEW.source := 'late_observation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['fpl_gameweeks','fpl_captures','fpl_player_states','fpl_id_map',
                             'fpl_result_captures','fpl_player_results','fantasy_prediction_snapshots'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS fpl_evidence_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER fpl_evidence_guard BEFORE INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION guard_fpl_evidence()',t);
        EXECUTE format('DROP TRIGGER IF EXISTS fpl_evidence_truncate_guard ON %I',t);
        EXECUTE format('CREATE TRIGGER fpl_evidence_truncate_guard BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION guard_fpl_evidence()',t);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    END LOOP;
END; $$;
-- Latest observed deadline per gameweek, and latest mapping per FPL id.
CREATE OR REPLACE VIEW fpl_gameweek_deadlines AS
SELECT DISTINCT ON (season,event_id) season, event_id, name, deadline, first_captured_at
FROM fpl_gameweeks ORDER BY season, event_id, first_captured_at DESC, deadline DESC;
CREATE OR REPLACE VIEW fpl_id_map_current AS
SELECT DISTINCT ON (kind,season,fpl_id) kind, season, fpl_id, fpl_code, api_id, method, detail, captured_at
FROM fpl_id_map ORDER BY kind, season, fpl_id, captured_at DESC, map_id DESC;
REVOKE ALL ON fpl_gameweek_deadlines,fpl_id_map_current FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON fpl_gameweek_deadlines,fpl_id_map_current FROM %I',r);
        END IF;
    END LOOP;
END; $$;
