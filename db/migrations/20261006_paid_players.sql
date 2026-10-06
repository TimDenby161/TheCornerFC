-- Repeatable. Applied 2026-10-06.
-- Player ranks for the paid tier (owner's line of 2026-10-04: the top 50 overall and the top 10
-- of each league are free, the full list is paid). While the paywall is off (site.entitled()
-- true for everyone) every answer is as before, plus "paywall": false.
--   site.players.free, data_free   whether he is in the free slice, and his row with the paid
--                          fields null (rank, season ranks, projected seasons, position ranks,
--                          his places): written by the export (export.site_player_rows). Who he
--                          is, his club, age, minutes, goals and assists stay.
--   site_players(...)      the live function with this added: for anyone not entitled, a player
--                          outside the free slice comes back as data_free; he has no place in
--                          an order by rank (he follows the ranked ones, by name), and a filter
--                          on Ability leaves him out. The answer carries "paywall": true.
--   site_player_page(id)   a player's page file. Once this function exists the export writes a
--                          player outside the free slice two rows: "players/<id>" without his
--                          rank going into each match or his rating movement ("cut": true), and
--                          "paid_players/<id>", whole and marked paid, which site_doc() never
--                          returns. This returns the whole one to anyone entitled and the
--                          cut-down one otherwise. A player in the free slice has one, whole.
-- Needs 20261006_paid_tier.sql and 20261005_site_players.sql. Also in db/schema.sql.
BEGIN;

ALTER TABLE site.players ADD COLUMN IF NOT EXISTS free boolean NOT NULL DEFAULT false;
ALTER TABLE site.players ADD COLUMN IF NOT EXISTS data_free json;
-- The rows already stored, until the next export rewrites them. The positions are those of
-- export.SITE_PLAYER_FIELDS (export.PLAYER_PAID_FIELDS; world is 15 and lg 16; a test keeps them in step)
UPDATE site.players p SET
    free = coalesce((p.data->>15)::integer <= 50, false) OR coalesce((p.data->>16)::integer <= 10, false),
    data_free = (SELECT pg_catalog.json_agg(CASE WHEN e.i - 1 = ANY (ARRAY[3,7,9,12,13,15,16,18,20]) THEN 'null'::json ELSE e.v END ORDER BY e.i)
                 FROM pg_catalog.json_array_elements(p.data) WITH ORDINALITY e(v, i))
WHERE p.data_free IS NULL;

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
    whole boolean := site.entitled();
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        WITH fit AS MATERIALIZED (
            SELECT p.league_id, p.team_id, p.name_lc,
                   -- a player outside the free slice, for anyone not entitled: his blanked row, no
                   -- place in an order by rank, and the same place as the others like him otherwise
                   CASE WHEN whole OR p.free THEN p.ord ELSE 1000000 END AS ord,
                   CASE WHEN whole OR p.free THEN p.data ELSE p.data_free END AS data,
                   CASE WHEN NOT (whole OR p.free) AND sort_key NOT IN ('age', 'ga') THEN NULL
                        WHEN sort_key = 'age' THEN -p.age::double precision
                        WHEN sort_key = 'ga' THEN p.ga
                        WHEN sort_key = 'pos' THEN (SELECT max((p.pos_ranks->>g.g)::double precision) FROM pg_catalog.unnest(p_groups) g(g))
                        WHEN pg_catalog.left(sort_key, 1) = 's' THEN p.seasons[sort_at]
                        ELSE p.future[sort_at] END AS v
            FROM site.players p
            WHERE (whole OR p.free OR p.data_free IS NOT NULL)      -- never the whole row for want of a blanked one
              AND (p_ids IS NULL OR p.player_id = ANY (p_ids))
              AND (p_leagues IS NULL OR p.league_id = ANY (p_leagues))
              AND (p_teams IS NULL OR p.team_id = ANY (p_teams))
              AND (p_nats IS NULL OR p.nationality = ANY (p_nats))
              AND (p_not_leagues IS NULL OR p.league_id IS NULL OR p.league_id <> ALL (p_not_leagues))
              AND (p_positions IS NULL OR p.plays && p_positions)
              AND (p_age IS NULL OR (p_age[1] IS NULL AND p_age[2] IS NULL)
                   OR (p.age IS NOT NULL AND (p_age[1] IS NULL OR p.age >= p_age[1]) AND (p_age[2] IS NULL OR p.age <= p_age[2])))
              AND (p_ab IS NULL OR (p_ab[1] IS NULL AND p_ab[2] IS NULL)
                   OR ((whole OR p.free) AND p.ability IS NOT NULL AND (p_ab[1] IS NULL OR p.ability >= p_ab[1]) AND (p_ab[2] IS NULL OR p.ability <= p_ab[2])))
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
                   'paywall', NOT whole,
                   'rows', (SELECT coalesce(pg_catalog.json_agg(r.data ORDER BY r.v DESC NULLS LAST, r.ord, r.name_lc), '[]'::json)
                            FROM (SELECT f.data, f.v, f.ord, f.name_lc FROM fit f ORDER BY f.v DESC NULLS LAST, f.ord, f.name_lc
                                  LIMIT least(greatest(coalesce(p_limit, 100), 0), 2000) OFFSET greatest(coalesce(p_offset, 0), 0)) r))
               END
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_player_page(p_id integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    doc json;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    IF site.entitled() THEN
        SELECT d.body INTO doc FROM site.docs d WHERE d.key = 'paid_players/' || p_id AND d.paid;
    END IF;
    IF doc IS NULL THEN
        SELECT d.body INTO doc FROM site.docs d WHERE d.key = 'players/' || p_id AND NOT d.paid;
    END IF;
    RETURN coalesce(doc, 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_players(integer[], integer[], integer[], text[], integer[], text[], integer[], integer[], integer[], integer[], text, text[], text, text[], integer, integer, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_player_page(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_players(integer[], integer[], integer[], text[], integer[], text[], integer[], integer[], integer[], integer[], text, text[], text, text[], integer, integer, boolean) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_player_page(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select count(*), count(*) filter (where free), count(data_free) from site.players;      -- about 7,500, several hundred, 7,500
--   select public.site_players(p_limit => 1)::json->>'paywall';                             -- false
--   select left(public.site_player_page((select player_id from site.players limit 1))::text, 40);   -- {"id":...
