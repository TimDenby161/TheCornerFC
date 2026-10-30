-- Repeatable. Not yet applied.
-- Match events: goals, cards, substitutions and VAR decisions with their minute (owner's decision
-- 2026-10-30, T-074). The /fixtures?ids= responses the jobs already fetch for player-data
-- fixtures (sync_fixture_players) carry them and they were thrown away; keeping them costs no API
-- calls. They are what plus-minus player ratings need: who was on the pitch when each goal went in.
--
--   fixture_events   one row per event, in the order the feed lists them (seq from 0). A
--                    fixture's rows are replaced whole whenever it is fetched again.
--                    player_id is the event's player (the scorer, the player booked, the player
--                    going off); assist_id the other (the assist, the player coming on). A
--                    suppressed player is stored as null in either.
--
-- About 20 rows a match, ~110,000 a season in the 13 player-data leagues: 10 to 15 MB a season.
-- Nothing here is reachable by the public key. Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS public.fixture_events (
    fixture_id integer NOT NULL REFERENCES public.fixtures(fixture_id) ON DELETE CASCADE,
    seq smallint NOT NULL,
    team_id integer,
    player_id integer,
    assist_id integer,
    elapsed smallint,
    extra smallint,
    type text,
    detail text,
    PRIMARY KEY (fixture_id, seq)
);
ALTER TABLE public.fixture_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.fixture_events FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON public.fixture_events FROM %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;
