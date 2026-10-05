-- Repeatable. Not applied yet: the owner runs it in the Supabase SQL editor, then an export.
-- The players as rows in the database, not as one file (owner, 2026-10-05: convert Players to a
-- table and query functions). Until now every view that showed a player downloaded all 7,500 of
-- them (players.json, 1.4 MB) and filtered, sorted and searched them in the browser.
--   site.players             one row per listed player: the columns the queries filter and sort
--                            on, and the player as the site draws him (data: an array in the
--                            order of the export's SITE_PLAYER_FIELDS). Rewritten whole by each
--                            export (export.store_players). In the site schema, which the Data
--                            API doesn't expose.
--   site_players(...)        the players that fit every argument given, in the order asked for,
--                            p_limit of them from p_offset: {"total": how many fit, "rows": [...]}.
--                            The Players table asks for the 100 rows on screen; a club's page
--                            asks for that club's players (p_teams), a nation's page for that
--                            nationality (p_nats), other views for players by id (p_ids).
--                            With p_count it returns, for the same arguments, how many fit per
--                            league and club ({"counts": [[league, club, n], ...]}): the numbers
--                            in the Players view's competition menu.
--   site_player_facets()     what the Players view's filters need without any player: the age,
--                            Ability and minutes ranges, how many play each position, the clubs
--                            (with the league each is listed under) and the nationalities.
--   site_next_xi(team)       a club's predicted XI for its next match, {"fixture", "players":
--                            [[player, name, position, rank], ...]} in team-sheet order, or null.
--                            Read from predicted_lineups, as the export did for every club at once.
-- Arguments of site_players (all optional; a range is '{from,to}', either end NULL for open):
--   p_ids, p_leagues, p_teams, p_nats   he is one of these players, in one of these leagues, at
--                            one of these clubs, of one of these nationalities
--   p_not_leagues            he isn't in one of these leagues (the view's Exclude chips)
--   p_positions              he plays one of these (his main position, or one he has started in
--                            for a quarter of his minutes over 12 months)
--   p_age, p_ab, p_crank, p_mins   his age, Ability as shown, club's world rank, and minutes
--                            over his last 20 appearances are inside the range
--   p_q, p_words             the search: his name contains p_q (lower case, as typed), or every
--                            word starts a word of his name or of his club's search text. The
--                            page knows the clubs' search text (short forms, leagues, countries),
--                            so each element of p_words is "word|1 if it fits a player with no
--                            club|the ids of the clubs it fits, comma-separated".
--   p_sort, p_groups         "age" (youngest first), "ga" (goals and assists), "pos" (his best
--                            rank in the role groups p_groups), "s0", "s1", ... (a season's rank,
--                            newest first) or "f0", "f1", ... (a projected season); highest
--                            first, blanks last, ties in the export's order. Default "s0".
--   p_limit, p_offset        at most 2,000 rows a call
-- Fixed SQL, definer's rights with an empty search path; the tables stay closed to the public
-- key. Needs public."application/json" (20261005_site_doc_raw.sql). Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS site.players (
    player_id integer PRIMARY KEY,
    ord integer NOT NULL,                     -- his place in the export's order (current rank, highest first)
    name_lc text NOT NULL,                    -- his name in lower case
    name_fold text NOT NULL,                  -- and without accents or punctuation, as the site's search folds text
    team_id integer,
    league_id integer,
    age integer,
    nationality text,
    plays text[] NOT NULL,
    ability integer,                          -- this season's rank, rounded as the site shows it
    club_world integer,                       -- his club's place among every ranked club
    minutes integer,
    seasons double precision[] NOT NULL,      -- his rank each season, newest first
    future double precision[] NOT NULL,       -- and each projected season, oldest first
    pos_ranks jsonb NOT NULL,                 -- {role group: his rank as that position}
    ga double precision,                      -- goals + assists this season, goals breaking ties
    data json NOT NULL
);
CREATE INDEX IF NOT EXISTS players_team_idx ON site.players (team_id);
CREATE INDEX IF NOT EXISTS players_league_idx ON site.players (league_id);
CREATE INDEX IF NOT EXISTS players_nationality_idx ON site.players (nationality);
ALTER TABLE site.players ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.players FROM PUBLIC;

-- a club's next predicted XI is looked up by club (the table's key is the fixture and the player)
CREATE INDEX IF NOT EXISTS predicted_lineups_team_idx ON public.predicted_lineups (team_id);

CREATE OR REPLACE FUNCTION public.site_players(
    p_ids integer[] DEFAULT NULL, p_leagues integer[] DEFAULT NULL, p_teams integer[] DEFAULT NULL,
    p_nats text[] DEFAULT NULL, p_not_leagues integer[] DEFAULT NULL, p_positions text[] DEFAULT NULL,
    p_age integer[] DEFAULT NULL, p_ab integer[] DEFAULT NULL, p_crank integer[] DEFAULT NULL,
    p_mins integer[] DEFAULT NULL, p_q text DEFAULT NULL, p_words text[] DEFAULT NULL,
    p_sort text DEFAULT 's0', p_groups text[] DEFAULT NULL, p_limit integer DEFAULT 100,
    p_offset integer DEFAULT 0, p_count boolean DEFAULT false) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    sort_key text := CASE WHEN p_sort IN ('age', 'ga', 'pos') OR p_sort ~ '^[sf][0-9]{1,2}$' THEN p_sort ELSE 's0' END;
    sort_at integer := CASE WHEN sort_key ~ '^[sf][0-9]' THEN pg_catalog.substr(sort_key, 2)::integer + 1 END;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH fit AS MATERIALIZED (
            SELECT p.league_id, p.team_id, p.ord, p.data,
                   CASE WHEN sort_key = 'age' THEN -p.age::double precision
                        WHEN sort_key = 'ga' THEN p.ga
                        WHEN sort_key = 'pos' THEN (SELECT max((p.pos_ranks->>g.g)::double precision) FROM pg_catalog.unnest(p_groups) g(g))
                        WHEN pg_catalog.left(sort_key, 1) = 's' THEN p.seasons[sort_at]
                        ELSE p.future[sort_at] END AS v
            FROM site.players p
            WHERE (p_ids IS NULL OR p.player_id = ANY (p_ids))
              AND (p_leagues IS NULL OR p.league_id = ANY (p_leagues))
              AND (p_teams IS NULL OR p.team_id = ANY (p_teams))
              AND (p_nats IS NULL OR p.nationality = ANY (p_nats))
              AND (p_not_leagues IS NULL OR p.league_id IS NULL OR p.league_id <> ALL (p_not_leagues))
              AND (p_positions IS NULL OR p.plays && p_positions)
              AND (p_age IS NULL OR (p_age[1] IS NULL AND p_age[2] IS NULL)
                   OR (p.age IS NOT NULL AND (p_age[1] IS NULL OR p.age >= p_age[1]) AND (p_age[2] IS NULL OR p.age <= p_age[2])))
              AND (p_ab IS NULL OR (p_ab[1] IS NULL AND p_ab[2] IS NULL)
                   OR (p.ability IS NOT NULL AND (p_ab[1] IS NULL OR p.ability >= p_ab[1]) AND (p_ab[2] IS NULL OR p.ability <= p_ab[2])))
              AND (p_crank IS NULL OR (p_crank[1] IS NULL AND p_crank[2] IS NULL)
                   OR (p.club_world IS NOT NULL AND (p_crank[1] IS NULL OR p.club_world >= p_crank[1]) AND (p_crank[2] IS NULL OR p.club_world <= p_crank[2])))
              AND (p_mins IS NULL OR (p_mins[1] IS NULL AND p_mins[2] IS NULL)
                   OR (p.minutes IS NOT NULL AND (p_mins[1] IS NULL OR p.minutes >= p_mins[1]) AND (p_mins[2] IS NULL OR p.minutes <= p_mins[2])))
              AND (p_q IS NULL OR pg_catalog.strpos(p.name_lc, p_q) > 0
                   OR (coalesce(pg_catalog.cardinality(p_words), 0) > 0 AND NOT EXISTS (
                           SELECT 1 FROM pg_catalog.unnest(p_words) w(w)
                           WHERE NOT (pg_catalog.strpos(' ' || p.name_fold, ' ' || pg_catalog.split_part(w.w, '|', 1)) > 0
                                      OR CASE WHEN p.team_id IS NULL THEN pg_catalog.split_part(w.w, '|', 2) = '1'
                                              ELSE p.team_id::text = ANY (pg_catalog.string_to_array(pg_catalog.split_part(w.w, '|', 3), ',')) END))))
        )
        SELECT CASE WHEN p_count THEN pg_catalog.json_build_object(
                   'counts', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(c.league_id, c.team_id, c.n)), '[]'::json)
                              FROM (SELECT f.league_id, f.team_id, count(*) AS n FROM fit f GROUP BY 1, 2) c))
               ELSE pg_catalog.json_build_object(
                   'total', (SELECT count(*) FROM fit),
                   'rows', (SELECT coalesce(pg_catalog.json_agg(r.data ORDER BY r.v DESC NULLS LAST, r.ord), '[]'::json)
                            FROM (SELECT f.data, f.v, f.ord FROM fit f ORDER BY f.v DESC NULLS LAST, f.ord
                                  LIMIT least(greatest(coalesce(p_limit, 100), 0), 2000) OFFSET greatest(coalesce(p_offset, 0), 0)) r))
               END
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_player_facets() RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'players', count(*),
            'age', CASE WHEN min(p.age) IS NOT NULL THEN pg_catalog.json_build_array(min(p.age), max(p.age)) END,
            'ability', CASE WHEN min(p.ability) IS NOT NULL THEN pg_catalog.json_build_array(min(p.ability), max(p.ability)) END,
            'minutes', coalesce(max(p.minutes), 0),
            'positions', (SELECT coalesce(pg_catalog.json_object_agg(x.pos, x.n), '{}'::json)
                          FROM (SELECT r.pos, count(*) AS n FROM site.players q, pg_catalog.unnest(q.plays) r(pos) GROUP BY 1) x),
            -- each club once, with the league of its highest-ranked player
            'clubs', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.team_id, x.league_id) ORDER BY x.ord), '[]'::json)
                      FROM (SELECT DISTINCT ON (q.team_id) q.team_id, q.league_id, q.ord FROM site.players q
                            WHERE q.team_id IS NOT NULL ORDER BY q.team_id, q.ord) x),
            'nats', (SELECT coalesce(pg_catalog.json_agg(x.nationality ORDER BY x.nationality), '[]'::json)
                     FROM (SELECT DISTINCT q.nationality FROM site.players q WHERE q.nationality <> '') x))
        FROM site.players p
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_next_xi(p_team integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN coalesce((
        SELECT pg_catalog.json_build_object(
            'fixture', x.fixture_id,
            -- team-sheet order: keeper, defence right to left, midfield, attack
            'players', pg_catalog.json_agg(
                pg_catalog.json_build_array(x.player_id, x.name, x.position, x.player_rank::float8)
                ORDER BY coalesce(pg_catalog.array_position(
                             ARRAY['GK','RB','RWB','CB','LB','LWB','DM','CM','RM','LM','AM','RW','LW','ST'], x.position), 99),
                         coalesce(x.player_rank, 0) DESC, x.player_id))
        FROM (SELECT pl.fixture_id, pl.player_id, p.name, pl.position, pl.player_rank
              FROM public.predicted_lineups pl JOIN public.players p USING (player_id)
              WHERE pl.team_id = p_team
                AND pl.fixture_id = (SELECT pl2.fixture_id FROM public.predicted_lineups pl2
                                     JOIN public.fixtures f2 ON f2.fixture_id = pl2.fixture_id
                                     WHERE pl2.team_id = p_team ORDER BY f2.kickoff, pl2.fixture_id LIMIT 1)) x
        GROUP BY x.fixture_id), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_players(integer[], integer[], integer[], text[], integer[], text[], integer[], integer[], integer[], integer[], text, text[], text, text[], integer, integer, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_player_facets() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_next_xi(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON site.players FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_players(integer[], integer[], integer[], text[], integer[], text[], integer[], integer[], integer[], integer[], text, text[], text, text[], integer, integer, boolean) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_player_facets() TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_next_xi(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select has_table_privilege('anon', 'site.players', 'select');                         -- f
--   select public.site_players()::text;                                                   -- {"total" : 0, "rows" : []} until the next export
--   select (public.site_players(p_limit => 1)::json->>'total')::int;                      -- after it: about 7,500
--   select public.site_player_facets()::json->'age';                                      -- after it: [15, 45] or so
--   select left(public.site_next_xi((select team_id from predicted_lineups limit 1))::text, 80);   -- {"fixture" : ..., "players" : [[...
