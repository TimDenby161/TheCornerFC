-- Repeatable. Applied 2026-10-05.
-- The matches as rows in the database, not as files (owner, 2026-10-05: convert Matches and the
-- match model detail to tables and queries, with Players to follow). First use: a match's model
-- detail, which was one stored file per match (4,088 of them).
--   site.matches             one row per match on the site: when, who, its competition, the match
--                            as the site draws it (data: an array in the order of the export's
--                            SITE_MATCH_FIELDS), the key reasons its card shows and the full model
--                            detail. Rewritten whole by each export (export.store_matches). In the
--                            site schema, which the Data API doesn't expose.
--   site_match_detail(fixture)   {"id", "why"} for one match on the site (why is null where the
--                            prediction has no breakdown), or null for a match that isn't there.
-- The queries for a day's, a club's and a competition's matches come in a later migration; the
-- indexes they need are here so the table doesn't have to be rebuilt.
-- Needs public."application/json" (20261005_site_doc_raw.sql). Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS site.matches (
    fixture_id integer PRIMARY KEY,
    kickoff timestamptz NOT NULL,
    league_id integer,
    home_id integer,
    away_id integer,
    status text,
    data json NOT NULL,
    reasons json,
    why json
);
CREATE INDEX IF NOT EXISTS matches_kickoff_idx ON site.matches (kickoff);
CREATE INDEX IF NOT EXISTS matches_league_idx ON site.matches (league_id, kickoff);
CREATE INDEX IF NOT EXISTS matches_home_idx ON site.matches (home_id, kickoff);
CREATE INDEX IF NOT EXISTS matches_away_idx ON site.matches (away_id, kickoff);
ALTER TABLE site.matches ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.matches FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.site_match_detail(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN coalesce((SELECT pg_catalog.json_build_object('id', m.fixture_id, 'why', m.why)
                     FROM site.matches m WHERE m.fixture_id = p_fixture), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.site_match_detail(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON site.matches FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_match_detail(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select has_table_privilege('anon', 'site.matches', 'select');        -- f
--   select public.site_match_detail(1)::text;                            -- null (no such match)
--   select count(*), count(why) from site.matches;                       -- after the next export: about 5,200 and 4,100
