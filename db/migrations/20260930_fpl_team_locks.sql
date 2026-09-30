-- Additive and repeatable. My FPL team page (README: My FPL team; owner's decision 2026-09-30):
-- the owner's "I've made these transfers" locks, written from the public site. The page carries
-- Supabase's public anon key, so anon gets exactly this: read the locks (the plan they record is
-- on the page anyway) and call lock_fpl_transfers / unlock_fpl_transfers, which check a
-- passphrase whose hash only the owner sets (in the SQL editor, see README). After 10 wrong
-- passphrases in an hour an entry is locked out for the rest of that hour.
-- Also closes anon's read of the upcoming_predictions view: views skip RLS, and nothing reads it
-- through the API.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
CREATE TABLE IF NOT EXISTS fpl_team_locks (
    entry_id integer NOT NULL,
    season integer NOT NULL,
    event_id integer NOT NULL,
    -- [{out, in, out_name, in_name, sell, buy}]: API-Football ids (negative FPL id if unmatched), tenths
    transfers jsonb NOT NULL CHECK (jsonb_typeof(transfers) = 'array' AND jsonb_array_length(transfers) <= 15),
    locked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (entry_id, season, event_id)
);
CREATE TABLE IF NOT EXISTS fpl_team_keys (
    entry_id integer PRIMARY KEY,
    key_hash text NOT NULL            -- extensions.crypt(passphrase, extensions.gen_salt('bf'))
);
CREATE TABLE IF NOT EXISTS fpl_team_key_failures (
    entry_id integer NOT NULL,
    failed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS fpl_team_key_failures_idx ON fpl_team_key_failures (entry_id, failed_at);
ALTER TABLE fpl_team_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE fpl_team_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE fpl_team_key_failures ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fpl_team_locks_read ON fpl_team_locks;
CREATE POLICY fpl_team_locks_read ON fpl_team_locks FOR SELECT USING (true);

-- NULL when the passphrase is right, else why not. Wrong ones are counted (the caller returns
-- rather than raising, so the count is kept).
CREATE OR REPLACE FUNCTION fpl_team_key_check(p_entry integer, p_key text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions, pg_temp AS $$
DECLARE
    h text;
BEGIN
    DELETE FROM fpl_team_key_failures WHERE failed_at < now() - interval '1 day';
    IF (SELECT count(*) FROM fpl_team_key_failures
        WHERE entry_id = p_entry AND failed_at > now() - interval '1 hour') >= 10 THEN
        RETURN 'Too many wrong passphrases: try again in an hour';
    END IF;
    SELECT key_hash INTO h FROM fpl_team_keys WHERE entry_id = p_entry;
    IF h IS NULL THEN
        RETURN 'No passphrase set for this team yet';
    END IF;
    IF p_key IS NOT NULL AND crypt(p_key, h) = h THEN
        RETURN NULL;
    END IF;
    INSERT INTO fpl_team_key_failures (entry_id) VALUES (p_entry);
    RETURN 'Wrong passphrase';
END;
$$;

CREATE OR REPLACE FUNCTION lock_fpl_transfers(p_entry integer, p_season integer, p_event integer,
                                              p_transfers jsonb, p_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions, pg_temp AS $$
DECLARE
    why text := fpl_team_key_check(p_entry, p_key);
    stamp timestamptz;
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    IF p_season IS NULL OR p_event IS NULL OR p_season NOT BETWEEN 2020 AND 2100 OR p_event NOT BETWEEN 1 AND 38
       OR jsonb_typeof(p_transfers) IS DISTINCT FROM 'array' OR jsonb_array_length(p_transfers) > 15
       OR octet_length(p_transfers::text) > 8000 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Not a valid lock');
    END IF;
    INSERT INTO fpl_team_locks (entry_id, season, event_id, transfers) VALUES (p_entry, p_season, p_event, p_transfers)
    ON CONFLICT (entry_id, season, event_id) DO UPDATE SET transfers = EXCLUDED.transfers, locked_at = now()
    RETURNING locked_at INTO stamp;
    RETURN jsonb_build_object('ok', true, 'locked_at', stamp);
END;
$$;

CREATE OR REPLACE FUNCTION unlock_fpl_transfers(p_entry integer, p_season integer, p_event integer, p_key text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions, pg_temp AS $$
DECLARE
    why text := fpl_team_key_check(p_entry, p_key);
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    DELETE FROM fpl_team_locks WHERE entry_id = p_entry AND season = p_season AND event_id = p_event;
    RETURN jsonb_build_object('ok', true);
END;
$$;

-- New tables and functions get Supabase's default grants to anon; replace them with the above
REVOKE ALL ON fpl_team_locks, fpl_team_keys, fpl_team_key_failures FROM PUBLIC;
REVOKE ALL ON FUNCTION fpl_team_key_check(integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION unlock_fpl_transfers(integer, integer, integer, text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON fpl_team_locks, fpl_team_keys, fpl_team_key_failures FROM %I', r);
            EXECUTE format('GRANT SELECT ON fpl_team_locks TO %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION fpl_team_key_check(integer, text) FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb, text) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION unlock_fpl_transfers(integer, integer, integer, text) TO %I', r);
            IF to_regclass('upcoming_predictions') IS NOT NULL THEN
                EXECUTE format('REVOKE ALL ON upcoming_predictions FROM %I', r);
            END IF;
        END IF;
    END LOOP;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='local_readonly') THEN
        GRANT SELECT ON fpl_team_locks TO local_readonly;
    END IF;
END; $$;
