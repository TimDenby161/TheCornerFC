-- Additive and repeatable. Applied 2026-10-03.
-- FPL data for the owner only (audit/findings.md L3, decision P2 (a), owner's decision 2026-10-02).
-- FPL's terms (cl. 28(d), 29) don't allow its data to be republished, so the FPL predictions
-- (FPL prices, positions, status, gameweeks) and the owner's team are no longer in docs/data. The
-- export and `fpl team` write them here instead, and the site reads them through fpl_owner_data,
-- which checks the same passphrase as the lock-in (fpl_team_key_check: 10 wrong in an hour locks
-- the entry out for the rest of that hour). The lock-ins are read the same way, so anon loses its
-- direct read of fpl_team_locks.
CREATE TABLE IF NOT EXISTS fpl_owner_docs (
    name text PRIMARY KEY CHECK (name IN ('fpl_predictions', 'fpl_team')),
    doc jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE fpl_owner_docs ENABLE ROW LEVEL SECURITY;

-- {ok, docs: {fpl_predictions, fpl_team}, locks: [{season, event_id, transfers, locked_at}]} when
-- the passphrase is right, else {ok: false, error}
CREATE OR REPLACE FUNCTION fpl_owner_data(p_entry integer, p_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions, pg_temp AS $$
DECLARE
    why text := fpl_team_key_check(p_entry, p_key);
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

REVOKE ALL ON fpl_owner_docs FROM PUBLIC;
REVOKE ALL ON FUNCTION fpl_owner_data(integer, text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON fpl_owner_docs FROM %I', r);
            EXECUTE format('REVOKE ALL ON fpl_team_locks FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION fpl_owner_data(integer, text) TO %I', r);
        END IF;
    END LOOP;
END; $$;
DROP POLICY IF EXISTS fpl_team_locks_read ON fpl_team_locks;
