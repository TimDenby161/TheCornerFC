-- Repeatable. Not yet applied.
-- A league's next round is free even when it is more than 7 days away (T-102, owner's decision
-- 2026-11-25): in an international break the Premier League's next round was over a week off,
-- so a free visitor saw no chances at all on its Matches tab. The 7-day line stays (the owner's
-- rule of 2026-10-06); on top of it, for a league with nothing in the next 7 days, its matches
-- kicking off within 4 days of its next kick-off (a round, Friday to Monday) are free too.
-- The export cuts each league's own file the same way (site_clubs.cut_league_fixtures,
-- NEXT_ROUND_DAYS). Only site_matches changes: the same arguments, grants and answer shape.
-- The next kick-off is one look-up on matches_league_idx (league_id, kickoff), made only for a
-- row more than 7 days away and only for a visitor who isn't entitled. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.site_matches(p_from timestamptz DEFAULT NULL, p_to timestamptz DEFAULT NULL,
                                               p_leagues integer[] DEFAULT NULL, p_team integer DEFAULT NULL,
                                               p_ids integer[] DEFAULT NULL) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    whole boolean := site.entitled();
    soon timestamptz := pg_catalog.now() + interval '7 days';
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'matches', coalesce(pg_catalog.json_agg(x.data ORDER BY x.kickoff, x.fixture_id), '[]'::json),
            'reasons', coalesce(pg_catalog.json_object_agg(x.fixture_id, x.reasons) FILTER (WHERE x.reasons IS NOT NULL), '{}'::json),
            'paywall', NOT whole)
        FROM (SELECT m.fixture_id, m.kickoff,
                     CASE WHEN whole OR m.kickoff <= pg_catalog.now() THEN m.data
                          WHEN m.kickoff <= soon THEN coalesce(m.data_free, m.data_locked)
                          -- a league with nothing in the next 7 days: its next round is free
                          WHEN (SELECT n.kickoff FROM site.matches n
                                WHERE n.league_id = m.league_id AND n.kickoff > pg_catalog.now()
                                ORDER BY n.kickoff LIMIT 1) > soon
                               AND m.kickoff <= (SELECT n.kickoff FROM site.matches n
                                                WHERE n.league_id = m.league_id AND n.kickoff > pg_catalog.now()
                                                ORDER BY n.kickoff LIMIT 1) + interval '4 days'
                               THEN coalesce(m.data_free, m.data_locked)
                          ELSE m.data_locked END AS data,
                     CASE WHEN whole OR m.kickoff <= pg_catalog.now() THEN m.reasons END AS reasons
              FROM site.matches m
              WHERE (p_from IS NOT NULL OR p_to IS NOT NULL OR p_leagues IS NOT NULL OR p_team IS NOT NULL OR p_ids IS NOT NULL)
                AND (p_from IS NULL OR m.kickoff >= p_from) AND (p_to IS NULL OR m.kickoff < p_to)
                AND (p_leagues IS NULL OR m.league_id = ANY (p_leagues))
                AND (p_team IS NULL OR m.home_id = p_team OR m.away_id = p_team)
                AND (p_ids IS NULL OR m.fixture_id = ANY (p_ids))
                -- a row the export hasn't given its blanked copies yet is left out for the
                -- unentitled, not shown whole
                AND (whole OR m.kickoff <= pg_catalog.now() OR m.data_locked IS NOT NULL)
              ORDER BY m.kickoff, m.fixture_id LIMIT 2000) x
    );
END; $$;

REVOKE ALL ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;
