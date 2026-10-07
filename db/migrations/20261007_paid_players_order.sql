-- Repeatable. Not yet applied.
-- The player ranks behind the paywall (owner, 2026-10-07): every list is in the order a
-- subscriber sees, with the ranks outside the free slice hidden; and the free slice is the top 50
-- overall, the top 10 of every league again, and the top 10 of each position.
--   site.players.free      also the top 10 of each league (it was the five big leagues' since
--                          20261006_paid_players_slice.sql) and of each position on the Players
--                          tab's pitch: of the players listed under it (plays), the ten best by
--                          their rank as it (pos_ranks, by role group as positions.GROUPS), the
--                          order the tab puts them in when it is picked. A tie shares the higher
--                          place, as in the export. Only rows that join the slice are written.
--   site.players.data_free keeps his place in the export's order (ord, position 20 of
--                          export.SITE_PLAYER_FIELDS), which the page sorts its own lists by.
--   site_players(...)      the live function with one change: a player outside the free slice,
--                          for anyone not entitled, still comes back as data_free but in the
--                          place the sort gives him (he used to follow the ranked players, by
--                          name). A filter on Ability still leaves him out.
-- The export does the first two from its next run (export.FREE_POSITION, PLAYER_PAID_FIELDS). A
-- player who joins the slice keeps his cut-down page file ("players/<id>") until that export
-- writes his whole one, so run a nightly sync after this.
-- Needs 20261006_paid_players.sql. Also in db/schema.sql.
BEGIN;

UPDATE site.players p SET free = true
WHERE NOT p.free AND (coalesce((p.data->>16)::integer <= 10, false) OR p.player_id IN (
    SELECT t.player_id
    FROM (SELECT s.player_id,
                 rank() OVER (PARTITION BY r.role ORDER BY (s.pos_ranks->>r.grp)::double precision DESC) AS place
          FROM site.players s
          JOIN (VALUES ('GK', 'GK'), ('CB', 'CB'), ('LB', 'FB'), ('RB', 'FB'), ('LWB', 'WB'), ('RWB', 'WB'),
                       ('DM', 'DM'), ('CM', 'CM'), ('AM', 'AM'), ('LW', 'W'), ('RW', 'W'), ('LM', 'W'), ('RM', 'W'),
                       ('ST', 'ST')) AS r(role, grp) ON r.role = ANY (s.plays)
          WHERE s.pos_ranks->>r.grp IS NOT NULL) t
    WHERE t.place <= 10));

UPDATE site.players p SET
    data_free = (SELECT pg_catalog.json_agg(CASE WHEN e.i - 1 = 20 THEN pg_catalog.to_json(p.ord) ELSE e.v END ORDER BY e.i)
                 FROM pg_catalog.json_array_elements(p.data_free) WITH ORDINALITY e(v, i))
WHERE p.data_free IS NOT NULL AND p.data_free->>20 IS NULL;

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
                   -- a player outside the free slice, for anyone not entitled: his blanked row, in
                   -- the place the sort gives him (the order is a subscriber's, the ranks are hidden)
                   p.ord,
                   CASE WHEN whole OR p.free THEN p.data ELSE p.data_free END AS data,
                   CASE WHEN sort_key = 'age' THEN -p.age::double precision
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

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select count(*) filter (where free), count(*), count(*) filter (where data_free->>20 is null) from site.players;   -- several hundred, about 7,500, 0
--   select public.site_players(p_limit => 1)::json->>'paywall';                                                         -- false
