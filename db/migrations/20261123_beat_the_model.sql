-- Repeatable. Applied to staging 2026-11-23 (production not yet).
-- Beat the Model (T-095, owner's decisions 2026-11-23): signed-in accounts predict the score of
-- every match of each Premier League round before kick-off; 3 points for the exact score, 1 for
-- the right result. The model plays too, with its most likely score. A player sees the model's
-- score for a match once they have picked it, so a pick is final once made; everyone sees it at
-- kick-off. One overall table, by round and by season, under a display name the player chooses
-- (never the email). No mini-leagues.
--
--   btm_players     a player's display name (3 to 20 letters, digits, spaces, . _ -), unique
--                   whatever the case. A player without one is scored but not in the table.
--   btm_picks       one row per player and match, final once written. points stays null until
--                   btm_score() marks the match.
--   btm_model       the model's score for a match, frozen by btm_score() at the first run after
--                   kick-off from site.matches (the 'likely' field), and its points.
--   btm_rounds      each player's points, exact scores, right results and picks in a round.
--   btm_seasons     the same for the season. Both are added to as matches finish, never rebuilt.
--
--   btm_round(p_round)    a round's matches with the caller's picks and points, the model's score
--                         where the caller has picked or the match has kicked off, and the
--                         caller's display name. p_round null: the round being played or next.
--   btm_pick(p_fixture, p_home, p_away)   saves a pick before kick-off; answers the model's score.
--   btm_set_name(p_name)  sets or changes the caller's display name.
--   btm_table(p_round)    the top 50 of the season (p_round null) or of a round, the caller's own
--                         row and the model's, by points then exact scores.
--   btm_score()           for the jobs only (every match-day run): freezes the model's score of
--                         each Premier League match that has kicked off, then marks the picks of
--                         finished matches and adds them to btm_rounds and btm_seasons. With
--                         nothing to do it is three small reads: the last 30 days of Premier
--                         League matches, btm_model (about 380 rows a season) and the unscored
--                         picks' partial index. A rerun adds nothing twice.
--
-- A season is named by the year it starts (August 2026 to May 2027 is 2026); a round is the number
-- at the end of the match's round label ('Regular Season - 13'). Premier League is league 39.
-- Size: about 150 bytes a pick, 380 picks a player a season: about 57 MB a season at 1,000
-- players. Leaving the site (deleting the account) removes a player's rows (ON DELETE CASCADE).
-- Nothing here is reachable by the public key alone, and an anonymous sign-in (no email) counts
-- as signed out. Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS public.btm_players (
    user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    display_name text NOT NULL CHECK (display_name ~ '^[A-Za-z0-9][A-Za-z0-9 ._-]{1,18}[A-Za-z0-9._-]$'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS btm_players_name_idx ON public.btm_players (lower(display_name));

CREATE TABLE IF NOT EXISTS public.btm_picks (
    user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    fixture_id integer NOT NULL,
    home smallint NOT NULL CHECK (home BETWEEN 0 AND 20),
    away smallint NOT NULL CHECK (away BETWEEN 0 AND 20),
    picked_at timestamptz NOT NULL DEFAULT now(),
    points smallint,
    PRIMARY KEY (user_id, fixture_id)
);
CREATE INDEX IF NOT EXISTS btm_picks_unscored_idx ON public.btm_picks (fixture_id) WHERE points IS NULL;

CREATE TABLE IF NOT EXISTS public.btm_model (
    fixture_id integer PRIMARY KEY,
    season smallint NOT NULL,
    round smallint NOT NULL,
    home smallint,
    away smallint,
    taken_at timestamptz NOT NULL DEFAULT now(),
    points smallint
);
CREATE INDEX IF NOT EXISTS btm_model_round_idx ON public.btm_model (season, round);

CREATE TABLE IF NOT EXISTS public.btm_rounds (
    season smallint NOT NULL,
    round smallint NOT NULL,
    user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    points integer NOT NULL DEFAULT 0,
    exact integer NOT NULL DEFAULT 0,
    results integer NOT NULL DEFAULT 0,
    played integer NOT NULL DEFAULT 0,
    PRIMARY KEY (season, round, user_id)
);

CREATE TABLE IF NOT EXISTS public.btm_seasons (
    season smallint NOT NULL,
    user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    points integer NOT NULL DEFAULT 0,
    exact integer NOT NULL DEFAULT 0,
    results integer NOT NULL DEFAULT 0,
    played integer NOT NULL DEFAULT 0,
    PRIMARY KEY (season, user_id)
);

ALTER TABLE public.btm_players ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.btm_picks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.btm_model ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.btm_rounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.btm_seasons ENABLE ROW LEVEL SECURITY;

-- The season a kick-off belongs to: August 2026 to May 2027 is 2026
CREATE OR REPLACE FUNCTION public.btm_season_of(p_at timestamptz) RETURNS smallint
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT pg_catalog.date_part('year', (p_at AT TIME ZONE 'UTC') - interval '6 months')::smallint;
$$;

-- Points for a pick against a full-time score: 3 exact, 1 the right result, else 0
CREATE OR REPLACE FUNCTION public.btm_points(p_home integer, p_away integer, p_hg integer, p_ag integer) RETURNS smallint
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
    SELECT CASE WHEN p_home IS NULL OR p_away IS NULL OR p_hg IS NULL OR p_ag IS NULL THEN NULL
                WHEN p_home = p_hg AND p_away = p_ag THEN 3
                WHEN pg_catalog.sign(p_home - p_away) = pg_catalog.sign(p_hg - p_ag) THEN 1
                ELSE 0 END::smallint;
$$;

CREATE OR REPLACE FUNCTION public.btm_round(p_round integer DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_me uuid := auth.uid();
    v_season smallint := public.btm_season_of(pg_catalog.now());
    v_round integer := p_round;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "private, no-store"}]', true);
    IF v_me IS NULL OR coalesce((auth.jwt()->>'is_anonymous')::boolean, false) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'Sign in to play');
    END IF;
    IF v_round IS NULL THEN
        -- the round being played or next: the one holding the earliest unfinished match, among
        -- rounds with at least 5 matches listed (so a single rearranged game doesn't take over)
        SELECT r.round INTO v_round FROM (
            SELECT pg_catalog.substring(m.data->>3, '(\d+)\s*$')::integer AS round,
                   pg_catalog.count(*) AS n,
                   pg_catalog.min(m.kickoff) FILTER (WHERE (m.status IS NULL OR m.status NOT IN
                       ('FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD', 'AWD', 'WO'))
                       AND m.kickoff > pg_catalog.now() - interval '1 day') AS first_open
            FROM site.matches m
            WHERE m.league_id = 39 AND public.btm_season_of(m.kickoff) = v_season
            GROUP BY 1) r
        WHERE r.round IS NOT NULL AND r.n >= 5 AND r.first_open IS NOT NULL
        ORDER BY r.first_open LIMIT 1;
    END IF;
    RETURN pg_catalog.jsonb_build_object('ok', true, 'season', v_season, 'round', v_round,
        'name', (SELECT p.display_name FROM public.btm_players p WHERE p.user_id = v_me),
        'matches', coalesce((
            SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                'id', m.fixture_id, 'kickoff', m.kickoff, 'home', m.home_id, 'away', m.away_id,
                'status', m.status, 'hg', m.data->7, 'ag', m.data->8,
                'pick', CASE WHEN k.fixture_id IS NULL THEN NULL ELSE pg_catalog.jsonb_build_array(k.home, k.away) END,
                'points', k.points,
                'model', CASE WHEN b.fixture_id IS NOT NULL THEN pg_catalog.to_jsonb(b.home::text || '-' || b.away::text)
                              WHEN k.fixture_id IS NOT NULL OR m.kickoff <= pg_catalog.now() THEN (m.data->16)::jsonb
                              ELSE NULL END,
                'model_points', b.points)
                ORDER BY m.kickoff, m.fixture_id)
            FROM site.matches m
            LEFT JOIN public.btm_picks k ON k.user_id = v_me AND k.fixture_id = m.fixture_id
            LEFT JOIN public.btm_model b ON b.fixture_id = m.fixture_id
            WHERE m.league_id = 39 AND public.btm_season_of(m.kickoff) = v_season
              AND pg_catalog.substring(m.data->>3, '(\d+)\s*$')::integer = v_round), '[]'::jsonb));
END; $$;

CREATE OR REPLACE FUNCTION public.btm_pick(p_fixture integer, p_home integer, p_away integer) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_me uuid := auth.uid();
    m site.matches;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "private, no-store"}]', true);
    IF v_me IS NULL OR coalesce((auth.jwt()->>'is_anonymous')::boolean, false) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'Sign in to play');
    END IF;
    IF p_home IS NULL OR p_away IS NULL OR p_home NOT BETWEEN 0 AND 20 OR p_away NOT BETWEEN 0 AND 20 THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'Not a valid score');
    END IF;
    SELECT * INTO m FROM site.matches x WHERE x.fixture_id = p_fixture AND x.league_id = 39;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'Not a match in the game');
    END IF;
    IF m.kickoff <= pg_catalog.now() THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'This match has kicked off');
    END IF;
    IF m.kickoff > pg_catalog.now() + interval '14 days' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'Picks open two weeks before kick-off');
    END IF;
    INSERT INTO public.btm_picks (user_id, fixture_id, home, away) VALUES (v_me, p_fixture, p_home, p_away)
    ON CONFLICT (user_id, fixture_id) DO NOTHING;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'You have already picked this match');
    END IF;
    RETURN pg_catalog.jsonb_build_object('ok', true, 'pick', pg_catalog.jsonb_build_array(p_home, p_away),
                                         'model', m.data->16);
END; $$;

CREATE OR REPLACE FUNCTION public.btm_set_name(p_name text) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_me uuid := auth.uid();
    v_name text := pg_catalog.btrim(p_name);
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "private, no-store"}]', true);
    IF v_me IS NULL OR coalesce((auth.jwt()->>'is_anonymous')::boolean, false) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'Sign in to play');
    END IF;
    IF v_name IS NULL OR v_name !~ '^[A-Za-z0-9][A-Za-z0-9 ._-]{1,18}[A-Za-z0-9._-]$' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false,
            'error', '3 to 20 letters or numbers (spaces, dots, dashes and underscores allowed)');
    END IF;
    IF EXISTS (SELECT 1 FROM public.btm_players p WHERE pg_catalog.lower(p.display_name) = pg_catalog.lower(v_name)
               AND p.user_id <> v_me) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'That name is taken');
    END IF;
    INSERT INTO public.btm_players (user_id, display_name) VALUES (v_me, v_name)
    ON CONFLICT (user_id) DO UPDATE SET display_name = EXCLUDED.display_name;
    RETURN pg_catalog.jsonb_build_object('ok', true, 'name', v_name);
EXCEPTION WHEN unique_violation THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'That name is taken');
END; $$;

CREATE OR REPLACE FUNCTION public.btm_table(p_round integer DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_me uuid := auth.uid();
    v_season smallint := public.btm_season_of(pg_catalog.now());
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "private, no-store"}]', true);
    IF v_me IS NULL OR coalesce((auth.jwt()->>'is_anonymous')::boolean, false) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'error', 'Sign in to play');
    END IF;
    RETURN (
        WITH entries AS (
            SELECT t.user_id, t.points, t.exact, t.results, t.played
            FROM public.btm_seasons t WHERE p_round IS NULL AND t.season = v_season
            UNION ALL
            SELECT t.user_id, t.points, t.exact, t.results, t.played
            FROM public.btm_rounds t WHERE p_round IS NOT NULL AND t.season = v_season AND t.round = p_round),
        named AS (
            SELECT r.*, p.display_name,
                   pg_catalog.rank() OVER (ORDER BY r.points DESC, r.exact DESC) AS pos
            FROM entries r JOIN public.btm_players p ON p.user_id = r.user_id),
        model AS (
            SELECT coalesce(pg_catalog.sum(b.points), 0) AS points,
                   pg_catalog.count(*) FILTER (WHERE b.points = 3) AS exact,
                   pg_catalog.count(*) FILTER (WHERE b.points >= 1) AS results,
                   pg_catalog.count(b.points) AS played
            FROM public.btm_model b
            WHERE b.season = v_season AND (p_round IS NULL OR b.round = p_round))
        SELECT pg_catalog.jsonb_build_object('ok', true, 'season', v_season, 'round', p_round,
            'players', (SELECT pg_catalog.count(*) FROM named),
            'top', coalesce((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(n.pos, n.display_name, n.points,
                                                                                       n.exact, n.results, n.played, n.user_id = v_me)
                                                         ORDER BY n.pos, n.display_name)
                             FROM (SELECT * FROM named ORDER BY pos, display_name LIMIT 50) n), '[]'::jsonb),
            'me', (SELECT pg_catalog.jsonb_build_array(n.pos, n.display_name, n.points, n.exact, n.results, n.played, true)
                   FROM named n WHERE n.user_id = v_me),
            'model', (SELECT pg_catalog.jsonb_build_array(m.points, m.exact, m.results, m.played) FROM model m)));
END; $$;

-- For the jobs (every match-day run). Returns how many picks it marked.
CREATE OR REPLACE FUNCTION public.btm_score() RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    marked integer := 0;
BEGIN
    -- 1. Freeze the model's score of each Premier League match that has kicked off
    INSERT INTO public.btm_model (fixture_id, season, round, home, away)
    SELECT m.fixture_id, public.btm_season_of(m.kickoff),
           pg_catalog.substring(m.data->>3, '(\d+)\s*$')::smallint,
           pg_catalog.split_part(m.data->>16, '-', 1)::smallint,
           pg_catalog.split_part(m.data->>16, '-', 2)::smallint
    FROM site.matches m
    WHERE m.league_id = 39 AND m.kickoff <= pg_catalog.now() AND m.kickoff > pg_catalog.now() - interval '30 days'
      AND pg_catalog.substring(m.data->>3, '(\d+)\s*$') IS NOT NULL
      AND (m.data->>16) ~ '^\d+-\d+$'
    ON CONFLICT (fixture_id) DO NOTHING;

    -- 2. Mark the model's points for finished matches
    UPDATE public.btm_model b
    SET points = public.btm_points(b.home, b.away, (m.data->>7)::integer, (m.data->>8)::integer)
    FROM site.matches m
    WHERE b.points IS NULL AND m.fixture_id = b.fixture_id AND m.status IN ('FT', 'AET', 'PEN')
      AND (m.data->>7) IS NOT NULL AND (m.data->>8) IS NOT NULL;

    -- 3. Mark the players' picks for finished matches and add them to the round and season
    WITH scored AS (
        UPDATE public.btm_picks k
        SET points = public.btm_points(k.home, k.away, (m.data->>7)::integer, (m.data->>8)::integer)
        FROM site.matches m
        WHERE k.points IS NULL AND m.fixture_id = k.fixture_id AND m.status IN ('FT', 'AET', 'PEN')
          AND (m.data->>7) IS NOT NULL AND (m.data->>8) IS NOT NULL
          AND pg_catalog.substring(m.data->>3, '(\d+)\s*$') IS NOT NULL
        RETURNING k.user_id, k.points, public.btm_season_of(m.kickoff) AS season,
                  pg_catalog.substring(m.data->>3, '(\d+)\s*$')::smallint AS round),
    by_round AS (
        SELECT s.season, s.round, s.user_id, pg_catalog.sum(s.points)::integer AS points,
               pg_catalog.count(*) FILTER (WHERE s.points = 3)::integer AS exact,
               pg_catalog.count(*) FILTER (WHERE s.points >= 1)::integer AS results,
               pg_catalog.count(*)::integer AS played
        FROM scored s GROUP BY 1, 2, 3),
    rounds AS (
        INSERT INTO public.btm_rounds AS t (season, round, user_id, points, exact, results, played)
        SELECT * FROM by_round
        ON CONFLICT (season, round, user_id) DO UPDATE SET points = t.points + EXCLUDED.points,
            exact = t.exact + EXCLUDED.exact, results = t.results + EXCLUDED.results, played = t.played + EXCLUDED.played
        RETURNING 1),
    seasons AS (
        INSERT INTO public.btm_seasons AS t (season, user_id, points, exact, results, played)
        SELECT r.season, r.user_id, pg_catalog.sum(r.points), pg_catalog.sum(r.exact), pg_catalog.sum(r.results),
               pg_catalog.sum(r.played)
        FROM by_round r GROUP BY 1, 2
        ON CONFLICT (season, user_id) DO UPDATE SET points = t.points + EXCLUDED.points,
            exact = t.exact + EXCLUDED.exact, results = t.results + EXCLUDED.results, played = t.played + EXCLUDED.played
        RETURNING 1)
    -- (rounds and seasons run whether read or not: data-changing WITH parts always do)
    SELECT pg_catalog.count(*)::integer INTO marked FROM scored;
    RETURN marked;
END; $$;

-- Shut to the public key, signed-in callers and the service key, apart from the four functions
-- players use (btm_score is for the jobs, which connect as the database owner)
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON public.btm_players, public.btm_picks, public.btm_model, public.btm_rounds, public.btm_seasons FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION public.btm_score() FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION public.btm_season_of(timestamptz), public.btm_points(integer, integer, integer, integer) FROM %I', r);
        END IF;
    END LOOP;
END; $$;
REVOKE ALL ON FUNCTION public.btm_score() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.btm_season_of(timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.btm_points(integer, integer, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.btm_round(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.btm_pick(integer, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.btm_set_name(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.btm_table(integer) FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON FUNCTION public.btm_round(integer), public.btm_pick(integer, integer, integer),
                               public.btm_set_name(text), public.btm_table(integer) FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        GRANT EXECUTE ON FUNCTION public.btm_round(integer), public.btm_pick(integer, integer, integer),
                                  public.btm_set_name(text), public.btm_table(integer) TO authenticated;
    END IF;
END; $$;

COMMIT;
