-- Repeatable. Applied 2026-10-05.
-- The Matches tab and every other view that shows matches ask the database for the ones they
-- show (owner, 2026-10-05), where each downloaded all 5,200 matches across 80 days (1.2 MB) and
-- the key reasons for 4,100 of them.
--   site_matches(from, to, leagues, team, ids)   the matches that fit every argument given: a
--                          day (kick-off from..to, which the page works out from the visitor's
--                          own clock), a competition's (its rounds), a club's (its page), or a
--                          list of ids (the ones Model vs Market lists). {"matches": the rows in
--                          the export's SITE_MATCH_FIELDS order, oldest first, "reasons": {id:
--                          the key reasons its card shows}}. With no argument it returns nothing,
--                          and never more than 2,000 rows.
--   site_match_days(tz)    what the date controls and the competition menu need without any
--                          match: how many matches (postponed ones left out) each competition has
--                          on each day of the visitor's calendar, the competitions with matches,
--                          and the international ones, most matches first. tz is an IANA zone
--                          name ("Europe/London"); one the database doesn't know counts as UTC.
--   site_match_detail(fixture)   as before, now with the name and code of the model version that
--                          made the prediction, which came from the file of every match's reasons.
--   site.matches.intl      whether it is a national team match (the last of SITE_MATCH_FIELDS),
--                          as a column the menu query can count.
-- Needs 20261005_site_matches.sql. Also in db/schema.sql.
BEGIN;

ALTER TABLE site.matches ADD COLUMN IF NOT EXISTS intl boolean NOT NULL DEFAULT false;

CREATE OR REPLACE FUNCTION public.site_matches(p_from timestamptz DEFAULT NULL, p_to timestamptz DEFAULT NULL,
                                               p_leagues integer[] DEFAULT NULL, p_team integer DEFAULT NULL,
                                               p_ids integer[] DEFAULT NULL) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN (
        SELECT pg_catalog.json_build_object(
            'matches', coalesce(pg_catalog.json_agg(x.data ORDER BY x.kickoff, x.fixture_id), '[]'::json),
            'reasons', coalesce(pg_catalog.json_object_agg(x.fixture_id, x.reasons) FILTER (WHERE x.reasons IS NOT NULL), '{}'::json))
        FROM (SELECT m.fixture_id, m.kickoff, m.data, m.reasons FROM site.matches m
              WHERE (p_from IS NOT NULL OR p_to IS NOT NULL OR p_leagues IS NOT NULL OR p_team IS NOT NULL OR p_ids IS NOT NULL)
                AND (p_from IS NULL OR m.kickoff >= p_from) AND (p_to IS NULL OR m.kickoff < p_to)
                AND (p_leagues IS NULL OR m.league_id = ANY (p_leagues))
                AND (p_team IS NULL OR m.home_id = p_team OR m.away_id = p_team)
                AND (p_ids IS NULL OR m.fixture_id = ANY (p_ids))
              ORDER BY m.kickoff, m.fixture_id LIMIT 2000) x
    );
END; $$;

CREATE OR REPLACE FUNCTION public.site_match_days(p_tz text DEFAULT 'UTC') RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    tz text := coalesce(pg_catalog.left(p_tz, 64), 'UTC');
BEGIN
    BEGIN
        PERFORM pg_catalog.now() AT TIME ZONE tz;
    EXCEPTION WHEN OTHERS THEN
        tz := 'UTC';
    END;
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN pg_catalog.json_build_object(
        'days', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.day, x.league_id, x.n) ORDER BY x.day, x.league_id), '[]'::json)
                 FROM (SELECT (m.kickoff AT TIME ZONE tz)::date AS day, m.league_id, count(*) AS n
                       FROM site.matches m WHERE m.status IS DISTINCT FROM 'PST' GROUP BY 1, 2) x),
        'leagues', (SELECT coalesce(pg_catalog.json_agg(x.league_id ORDER BY x.league_id), '[]'::json)
                    FROM (SELECT m.league_id FROM site.matches m WHERE m.league_id IS NOT NULL GROUP BY 1) x),
        'intl', (SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(x.league_id, x.n) ORDER BY x.n DESC, x.league_id), '[]'::json)
                 FROM (SELECT m.league_id, count(*) AS n FROM site.matches m WHERE m.intl GROUP BY 1) x));
END; $$;

CREATE OR REPLACE FUNCTION public.site_match_detail(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN coalesce((SELECT pg_catalog.json_build_object(
                                'id', m.fixture_id, 'why', m.why,
                                'model', (SELECT pg_catalog.json_build_object('name', v.version_name, 'code', pg_catalog.left(v.code_sha, 7))
                                          FROM public.model_versions v WHERE v.model_version_id = m.why->>'model'))
                     FROM site.matches m WHERE m.fixture_id = p_fixture), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_match_days(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_match_detail(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_match_days(text) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_match_detail(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select public.site_matches()::text;                                                     -- {"matches" : [], "reasons" : {}}
--   select json_array_length(public.site_matches(p_leagues => '{39}')::json->'matches');    -- after the next export: the Premier League's matches on the site
--   select json_array_length(public.site_match_days('Europe/London')::json->'days');        -- after it: a row per day and competition
