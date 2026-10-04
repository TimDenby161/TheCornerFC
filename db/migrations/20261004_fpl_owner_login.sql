-- Repeatable. NOT APPLIED YET. Apply together with publishing the site change that goes with it:
-- the site before it calls the passphrase functions this drops.
-- The owner-only FPL pages check who is signed in instead of a passphrase (owner's decision
-- 2026-10-04; README: Accounts, My FPL team). fpl_team_owners holds the email address allowed for
-- an entry; it is set in the SQL editor (README: My FPL team), not here. fpl_owner_data and
-- lock/unlock_fpl_transfers lose their passphrase argument and can be called by signed-in
-- visitors only (authenticated), not with the public key alone, and answer {ok: false} to anyone
-- but the owner. An address only counts once Supabase Auth has confirmed it (Google sign-in, or
-- the emailed link), so signing up with the owner's address doesn't pass without that mailbox.
-- The passphrase functions and tables are dropped. Don't re-run 20260930_fpl_team_locks.sql or
-- 20261003_fpl_owner_docs.sql on their own after this: they would bring the passphrase back.
-- When applied, append this file to db/schema.sql as the other migrations are.
CREATE TABLE IF NOT EXISTS fpl_team_owners (
    entry_id integer PRIMARY KEY,
    email text NOT NULL
);
ALTER TABLE fpl_team_owners ENABLE ROW LEVEL SECURITY;

DROP FUNCTION IF EXISTS fpl_owner_data(integer, text);
DROP FUNCTION IF EXISTS lock_fpl_transfers(integer, integer, integer, jsonb, text);
DROP FUNCTION IF EXISTS unlock_fpl_transfers(integer, integer, integer, text);
DROP FUNCTION IF EXISTS fpl_team_key_check(integer, text);
DROP TABLE IF EXISTS fpl_team_key_failures, fpl_team_keys;

-- NULL when the caller is signed in as the entry's owner, else why not
CREATE OR REPLACE FUNCTION fpl_team_owner_check(p_entry integer) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT CASE
        WHEN auth.uid() IS NULL THEN 'Sign in to see this'
        WHEN EXISTS (SELECT 1 FROM auth.users u JOIN fpl_team_owners o ON lower(o.email) = lower(u.email)
                     WHERE u.id = auth.uid() AND o.entry_id = p_entry AND u.email_confirmed_at IS NOT NULL) THEN NULL
        ELSE 'This account isn''t the site owner''s'
    END;
$$;

-- {ok, docs: {fpl_predictions, fpl_team}, locks: [{season, event_id, transfers, locked_at}]} for
-- the owner, else {ok: false, error}
CREATE OR REPLACE FUNCTION fpl_owner_data(p_entry integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    why text := fpl_team_owner_check(p_entry);
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    RETURN jsonb_build_object('ok', true,
        'docs', coalesce((SELECT jsonb_object_agg(name, doc) FROM fpl_owner_docs), '{}'::jsonb),
        'locks', coalesce((SELECT jsonb_agg(jsonb_build_object('season', season, 'event_id', event_id,
                                                               'transfers', transfers, 'locked_at', locked_at))
                           FROM fpl_team_locks WHERE entry_id = p_entry), '[]'::jsonb));
END;
$$;

CREATE OR REPLACE FUNCTION lock_fpl_transfers(p_entry integer, p_season integer, p_event integer,
                                              p_transfers jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    why text := fpl_team_owner_check(p_entry);
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

CREATE OR REPLACE FUNCTION unlock_fpl_transfers(p_entry integer, p_season integer, p_event integer)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    why text := fpl_team_owner_check(p_entry);
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    DELETE FROM fpl_team_locks WHERE entry_id = p_entry AND season = p_season AND event_id = p_event;
    RETURN jsonb_build_object('ok', true);
END;
$$;

REVOKE ALL ON fpl_team_owners FROM PUBLIC;
REVOKE ALL ON FUNCTION fpl_team_owner_check(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION fpl_owner_data(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION unlock_fpl_transfers(integer, integer, integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON fpl_team_owners FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION fpl_team_owner_check(integer) FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION fpl_owner_data(integer) FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb) FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION unlock_fpl_transfers(integer, integer, integer) FROM %I', r);
        END IF;
    END LOOP;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        GRANT EXECUTE ON FUNCTION fpl_owner_data(integer) TO authenticated;
        GRANT EXECUTE ON FUNCTION lock_fpl_transfers(integer, integer, integer, jsonb) TO authenticated;
        GRANT EXECUTE ON FUNCTION unlock_fpl_transfers(integer, integer, integer) TO authenticated;
    END IF;
END; $$;

-- Check afterwards (expect no rows: the public key alone can call nothing):
--   select p.oid::regprocedure from pg_proc p where p.pronamespace='public'::regnamespace
--     and has_function_privilege('anon', p.oid, 'execute');
