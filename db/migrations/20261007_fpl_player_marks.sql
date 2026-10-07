-- Repeatable. For the owner to apply in the SQL editor, with the site change that goes with it
-- (the FPL tab's "Mine" and "Target" boxes; until it is applied the boxes say they couldn't save).
-- The owner's own marks against players on the FPL tab: in his team, or one he wants. One row a
-- marked player (ours: players.id, as the predictions key them); a player with neither mark has no
-- row. Owner only, like the lock-ins: the table can't be read or written through the API, and
-- mark_fpl_player answers {ok: false} to anyone but the sign-in named in fpl_team_owners.
-- fpl_owner_data returns them with the documents and the locks, as marks: [[player, mine, target]].
-- Also in db/schema.sql.
CREATE TABLE IF NOT EXISTS fpl_player_marks (
    entry_id integer NOT NULL,
    player_id integer NOT NULL,
    mine boolean NOT NULL DEFAULT false,
    target boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (entry_id, player_id),
    CHECK (mine OR target)
);
ALTER TABLE fpl_player_marks ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION mark_fpl_player(p_entry integer, p_player integer, p_mine boolean, p_target boolean)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    why text := fpl_team_owner_check(p_entry);
BEGIN
    IF why IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', why);
    END IF;
    IF p_player IS NULL OR p_player <= 0 OR p_mine IS NULL OR p_target IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Not a valid mark');
    END IF;
    IF NOT (p_mine OR p_target) THEN
        DELETE FROM fpl_player_marks WHERE entry_id = p_entry AND player_id = p_player;
    ELSIF (SELECT count(*) FROM fpl_player_marks WHERE entry_id = p_entry AND player_id <> p_player) >= 500 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'Too many marked players');
    ELSE
        INSERT INTO fpl_player_marks (entry_id, player_id, mine, target) VALUES (p_entry, p_player, p_mine, p_target)
        ON CONFLICT (entry_id, player_id) DO UPDATE SET mine = EXCLUDED.mine, target = EXCLUDED.target, updated_at = now();
    END IF;
    RETURN jsonb_build_object('ok', true);
END;
$$;

-- {ok, docs, locks, marks: [[player, mine, target]]} for the owner, else {ok: false, error}
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
                           FROM fpl_team_locks WHERE entry_id = p_entry), '[]'::jsonb),
        'marks', coalesce((SELECT jsonb_agg(jsonb_build_array(player_id, mine, target))
                           FROM fpl_player_marks WHERE entry_id = p_entry), '[]'::jsonb));
END;
$$;

REVOKE ALL ON fpl_player_marks FROM PUBLIC;
REVOKE ALL ON FUNCTION mark_fpl_player(integer, integer, boolean, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION fpl_owner_data(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON fpl_player_marks FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION mark_fpl_player(integer, integer, boolean, boolean) FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION fpl_owner_data(integer) FROM %I', r);
        END IF;
    END LOOP;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        GRANT EXECUTE ON FUNCTION mark_fpl_player(integer, integer, boolean, boolean) TO authenticated;
        GRANT EXECUTE ON FUNCTION fpl_owner_data(integer) TO authenticated;
    END IF;
END; $$;

-- Check afterwards:
--   select has_table_privilege('anon', 'fpl_player_marks', 'select'), has_table_privilege('authenticated', 'fpl_player_marks', 'select');   -- f, f
--   select has_function_privilege('anon', 'mark_fpl_player(integer, integer, boolean, boolean)', 'execute');                                -- f
--   select * from fpl_player_marks;                                                                                                          -- a row for each box ticked on the FPL tab
