-- Fix guard_fpl_evidence(): the fpl_captures source check read NEW.source on every
-- guarded table, so inserts into fpl_gameweeks, fpl_id_map and fpl_result_captures failed with
-- 'record "new" has no field "source"'. Replaces the function only; triggers are unchanged.
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
    -- Nested: PL/pgSQL does not short-circuit AND, and only some guarded tables have source.
    IF TG_TABLE_NAME = 'fpl_captures' THEN
        IF NEW.source = 'prospective'
           AND (NEW.captured_at >= NEW.effective_at OR NEW.created_at >= NEW.effective_at) THEN
            NEW.source := 'late_observation';
        END IF;
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
