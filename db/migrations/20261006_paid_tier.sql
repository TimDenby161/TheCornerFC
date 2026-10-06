-- Repeatable. Applied 2026-10-06.
-- The paid tier's foundation, switched off (owner, 2026-10-06: build everything but the
-- checkout; nothing changes for visitors until the switch is turned on).
--   subscriptions          who has paid: one row per account, written only by the payment
--                          provider's webhook when there is one (and by hand until then). No key
--                          can read or write it.
--   site.settings          the site's switches. 'paywall' is false: while it is, everyone gets
--                          everything, exactly as before this migration.
--   site.subscriber()      whether the caller is signed in with a live subscription, or is the
--                          site's owner (fpl_team_owners, as the FPL pages check).
--   site.entitled()        whether the caller gets the paid content: the paywall is off, or
--                          site.subscriber().
--   my_subscription()      what the page needs to know about the caller: {"paywall", "signed_in",
--                          "subscriber", "status", "plan", "renews_at", "ends"}.
--   site.matches.data_free, data_locked   a match's row with the paid fields blanked, written by
--                          the export beside the full row (export.store_matches):
--                            data_free    no projected goals, likely score, over 2.5, both to
--                                         score, absences or line-up ratings; the win, draw and
--                                         loss chances stay
--                            data_locked  the chances gone as well
--   site_matches(...)      as before for anyone entitled. Otherwise a match that hasn't kicked
--                          off comes back as data_free when it is within 7 days and data_locked
--                          beyond that, without its key reasons, and the answer carries
--                          "paywall": true so the page can say what is behind the lock. Matches
--                          that have kicked off are always whole: the record is free.
--   site_match_detail(fixture)   the model detail of a match that hasn't kicked off is for the
--                          entitled only ("locked": true otherwise).
-- The free and paid line is the owner's of 2026-10-04 (audit/commercial-plan.md): free is the
-- chances for the next 7 days; depth and matches further ahead are paid.
-- To switch the paywall on later (not now: the league pages, line-ups and player ranks aren't
-- gated yet):  update site.settings set value = 'true' where key = 'paywall';
-- Needs 20261005_site_matches_queries.sql and 20261004_fpl_owner_login.sql. Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS public.subscriptions (
    user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('active', 'trialing', 'past_due', 'canceled')),
    plan text,                                -- 'monthly' or 'yearly'
    current_period_end timestamptz,           -- paid up to here
    cancel_at_period_end boolean NOT NULL DEFAULT false,
    provider text,                            -- who takes the payment, and its ids for this customer
    provider_customer text,
    provider_subscription text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.subscriptions FROM PUBLIC;

CREATE TABLE IF NOT EXISTS site.settings (
    key text PRIMARY KEY,
    value jsonb NOT NULL
);
ALTER TABLE site.settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON site.settings FROM PUBLIC;
INSERT INTO site.settings (key, value) VALUES ('paywall', 'false') ON CONFLICT (key) DO NOTHING;

-- A subscription counts while it is paid up; a failed renewal keeps it for 3 days of retries
CREATE OR REPLACE FUNCTION site.subscriber() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT EXISTS (SELECT 1 FROM public.subscriptions b
                   WHERE b.user_id = auth.uid() AND b.status IN ('active', 'trialing', 'past_due')
                     AND (b.current_period_end IS NULL OR b.current_period_end + interval '3 days' > pg_catalog.now()))
        OR EXISTS (SELECT 1 FROM auth.users u JOIN public.fpl_team_owners o ON pg_catalog.lower(o.email) = pg_catalog.lower(u.email)
                   WHERE u.id = auth.uid() AND u.email_confirmed_at IS NOT NULL);
$$;
CREATE OR REPLACE FUNCTION site.entitled() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT NOT coalesce((SELECT s.value = 'true'::jsonb FROM site.settings s WHERE s.key = 'paywall'), false)
        OR site.subscriber();
$$;
REVOKE ALL ON FUNCTION site.subscriber() FROM PUBLIC;
REVOKE ALL ON FUNCTION site.entitled() FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.my_subscription() RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    b public.subscriptions;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-store"}]', true);
    SELECT * INTO b FROM public.subscriptions s WHERE s.user_id = auth.uid();
    RETURN pg_catalog.json_build_object(
        'paywall', coalesce((SELECT s.value = 'true'::jsonb FROM site.settings s WHERE s.key = 'paywall'), false),
        'signed_in', auth.uid() IS NOT NULL,
        'subscriber', site.subscriber(),
        'status', b.status, 'plan', b.plan, 'renews_at', b.current_period_end,
        'ends', coalesce(b.cancel_at_period_end, false));
END; $$;

ALTER TABLE site.matches ADD COLUMN IF NOT EXISTS data_free json;
ALTER TABLE site.matches ADD COLUMN IF NOT EXISTS data_locked json;
-- The rows already stored, until the next export rewrites them. The positions are those of
-- export.SITE_MATCH_FIELDS (export.MATCH_PAID_DEPTH, MATCH_PAID_CHANCES; a test keeps them in step)
UPDATE site.matches m SET
    data_free = (SELECT pg_catalog.json_agg(CASE WHEN e.i - 1 = ANY (ARRAY[14,15,16,28,29,30,31,32,33,34,35]) THEN 'null'::json ELSE e.v END ORDER BY e.i)
                 FROM pg_catalog.json_array_elements(m.data) WITH ORDINALITY e(v, i)),
    data_locked = (SELECT pg_catalog.json_agg(CASE WHEN e.i - 1 = ANY (ARRAY[11,12,13,14,15,16,28,29,30,31,32,33,34,35]) THEN 'null'::json ELSE e.v END ORDER BY e.i)
                   FROM pg_catalog.json_array_elements(m.data) WITH ORDINALITY e(v, i))
WHERE m.data_free IS NULL OR m.data_locked IS NULL;

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

CREATE OR REPLACE FUNCTION public.site_match_detail(p_fixture integer) RETURNS public."application/json"
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    whole boolean := site.entitled();
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-cache"}]', true);
    RETURN coalesce((SELECT CASE WHEN whole OR m.kickoff <= pg_catalog.now() THEN pg_catalog.json_build_object(
                                'id', m.fixture_id, 'why', m.why,
                                'model', (SELECT pg_catalog.json_build_object('name', v.version_name, 'code', pg_catalog.left(v.code_sha, 7))
                                          FROM public.model_versions v WHERE v.model_version_id = m.why->>'model'))
                            ELSE pg_catalog.json_build_object('id', m.fixture_id, 'why', NULL, 'locked', true) END
                     FROM site.matches m WHERE m.fixture_id = p_fixture), 'null'::json);
END; $$;

REVOKE ALL ON FUNCTION public.my_subscription() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.site_match_detail(integer) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON public.subscriptions FROM %I', r);
            EXECUTE format('REVOKE ALL ON site.settings FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION site.subscriber() FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION site.entitled() FROM %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.my_subscription() TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_matches(timestamptz, timestamptz, integer[], integer, integer[]) TO %I', r);
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.site_match_detail(integer) TO %I', r);
        END IF;
    END LOOP;
END; $$;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- Check afterwards:
--   select value from site.settings where key = 'paywall';                                  -- false
--   select has_table_privilege('anon', 'public.subscriptions', 'select');                   -- f
--   select public.my_subscription()::text;                                                  -- {"paywall" : false, "signed_in" : false, "subscriber" : false, ...}
--   select count(*), count(data_free), count(data_locked) from site.matches;                -- three equal numbers
--   select public.site_matches(p_leagues => '{39}')::json->>'paywall';                      -- false
