-- Repeatable. Applied 2026-10-14, to staging and to production.
-- The two match models compared, for the Admin area's switch card (owner's decision 2026-10-14:
-- "the proper data in front of me to compare the two" before switching). Reads only.
--
--   admin_match_model_compare()  {"ok": false} for anyone but an administrator; for one:
--     finished   each model's log loss, Brier and share of right results on the same finished
--                matches since P18's start (2026-10-15), both predictions captured and written
--                before kickoff, scored on the 90-minute score: P18's population, so the gap here
--                is the one P18 judges (experiments/prospective/live_p18.py)
--     upcoming   fixtures not yet kicked off with both models' rows: how many, how often the two
--                pick a different favourite, the mean gap in each of home, draw and away
--     apart      the twenty upcoming fixtures where the two are furthest apart, both models'
--                chances and expected goals side by side
-- Cost: reads challenger_predictions (two rows a fixture) and fixtures by primary key, only when
-- the administrator opens the tracker; nothing is stored. Also in db/schema.sql.
BEGIN;

CREATE OR REPLACE FUNCTION public.admin_match_model_compare() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE finished jsonb; upcoming jsonb; apart jsonb;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-store"}]', true);
    IF NOT site.is_admin() THEN
        RETURN pg_catalog.jsonb_build_object('ok', false);
    END IF;

    WITH done AS (
        SELECT f.fixture_id,
               CASE WHEN f.ft_home > f.ft_away THEN 0 WHEN f.ft_home = f.ft_away THEN 1 ELSE 2 END AS y,
               c.model, c.p_home, c.p_draw, c.p_away
        FROM public.fixtures f
        JOIN public.challenger_predictions c ON c.fixture_id = f.fixture_id
        WHERE f.kickoff >= '2026-10-15'::timestamptz AND f.status_short IN ('FT', 'AET', 'PEN')
          AND f.ft_home IS NOT NULL AND f.ft_away IS NOT NULL
          AND c.captured_at < f.kickoff AND c.written_at < f.kickoff
    ), paired AS (
        SELECT * FROM (SELECT d.*, pg_catalog.count(*) OVER (PARTITION BY d.fixture_id) AS models FROM done d) x
        WHERE x.models = 2
    ), scored AS (
        SELECT p.model,
               -pg_catalog.ln(GREATEST(CASE p.y WHEN 0 THEN p.p_home WHEN 1 THEN p.p_draw ELSE p.p_away END, 1e-12)) AS loss,
               pg_catalog.power(p.p_home - (p.y = 0)::int, 2) + pg_catalog.power(p.p_draw - (p.y = 1)::int, 2)
                 + pg_catalog.power(p.p_away - (p.y = 2)::int, 2) AS brier,
               (CASE p.y WHEN 0 THEN p.p_home WHEN 1 THEN p.p_draw ELSE p.p_away END
                  >= GREATEST(p.p_home, p.p_draw, p.p_away))::int AS right_result
        FROM paired p
    )
    SELECT COALESCE(pg_catalog.jsonb_object_agg(s.model, pg_catalog.jsonb_build_object(
               'n', s.n, 'log_loss', s.log_loss, 'brier', s.brier, 'accuracy', s.accuracy)), '{}'::jsonb)
    INTO finished
    FROM (SELECT model, pg_catalog.count(*) AS n, pg_catalog.avg(loss) AS log_loss,
                 pg_catalog.avg(brier) AS brier, pg_catalog.avg(right_result) AS accuracy
          FROM scored GROUP BY model) s;

    WITH next AS (
        SELECT f.fixture_id, f.kickoff, l.name AS league, th.name AS home, ta.name AS away,
               b.p_home AS b_home, b.p_draw AS b_draw, b.p_away AS b_away, b.home_xg AS b_hxg, b.away_xg AS b_axg,
               a.p_home AS a_home, a.p_draw AS a_draw, a.p_away AS a_away, a.home_xg AS a_hxg, a.away_xg AS a_axg
        FROM public.challenger_predictions b
        JOIN public.challenger_predictions a ON a.fixture_id = b.fixture_id AND a.model = 'a18'
        JOIN public.fixtures f ON f.fixture_id = b.fixture_id
        JOIN public.leagues l ON l.league_id = f.league_id
        JOIN public.teams th ON th.team_id = f.home_team_id
        JOIN public.teams ta ON ta.team_id = f.away_team_id
        WHERE b.model = 'base' AND f.kickoff > pg_catalog.now()
    ), gaps AS (
        SELECT n.*,
               GREATEST(pg_catalog.abs(n.a_home - n.b_home), pg_catalog.abs(n.a_draw - n.b_draw),
                        pg_catalog.abs(n.a_away - n.b_away)) AS gap,
               (CASE WHEN n.b_home >= GREATEST(n.b_draw, n.b_away) THEN 0 WHEN n.b_draw >= n.b_away THEN 1 ELSE 2 END)
                 <> (CASE WHEN n.a_home >= GREATEST(n.a_draw, n.a_away) THEN 0 WHEN n.a_draw >= n.a_away THEN 1 ELSE 2 END) AS differ
        FROM next n
    )
    SELECT pg_catalog.jsonb_build_object(
               'n', pg_catalog.count(*),
               'different_favourite', pg_catalog.count(*) FILTER (WHERE g.differ),
               'mean_gap', pg_catalog.jsonb_build_object(
                   'home', pg_catalog.avg(pg_catalog.abs(g.a_home - g.b_home)),
                   'draw', pg_catalog.avg(pg_catalog.abs(g.a_draw - g.b_draw)),
                   'away', pg_catalog.avg(pg_catalog.abs(g.a_away - g.b_away))),
               'a18_home_higher', pg_catalog.count(*) FILTER (WHERE g.a_home > g.b_home)),
           (SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                       'fixture', t.fixture_id, 'kickoff', t.kickoff, 'league', t.league, 'home', t.home, 'away', t.away,
                       'differ', t.differ, 'gap', t.gap,
                       'base', pg_catalog.jsonb_build_array(t.b_home, t.b_draw, t.b_away, t.b_hxg, t.b_axg),
                       'a18', pg_catalog.jsonb_build_array(t.a_home, t.a_draw, t.a_away, t.a_hxg, t.a_axg))
                   ORDER BY t.gap DESC, t.kickoff), '[]'::jsonb)
            FROM (SELECT * FROM gaps ORDER BY gap DESC, kickoff LIMIT 20) t)
    INTO upcoming, apart
    FROM gaps g;

    RETURN pg_catalog.jsonb_build_object('ok', true, 'start', '2026-10-15',
        'finished', finished, 'upcoming', upcoming, 'apart', apart);
END;
$$;

REVOKE ALL ON FUNCTION public.admin_match_model_compare() FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON FUNCTION public.admin_match_model_compare() FROM %I', r);
        END IF;
    END LOOP;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        GRANT EXECUTE ON FUNCTION public.admin_match_model_compare() TO authenticated;
    END IF;
END; $$;

COMMIT;

-- Check afterwards, signed in as the owner for a moment and undone:
--   begin;
--   select set_config('request.jwt.claims', json_build_object('role', 'authenticated',
--     'sub', (select id from auth.users where lower(email) = 'timdenby161@gmail.com'))::text, true);
--   set local role authenticated;
--   select public.admin_match_model_compare();   -- {"ok": true, "finished": {...}, "upcoming": {"n": ...}, "apart": [...]}
--   rollback;
--   select has_function_privilege('anon', 'public.admin_match_model_compare()', 'execute');   -- f
