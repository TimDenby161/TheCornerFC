-- Repeatable. Applied 2026-10-15, to staging and to production.
-- The bookmakers beside the two match models on the Admin area's switch card (owner's request
-- 2026-10-15: "a bookies column so we can see all 3"). Replaces admin_match_model_compare()
-- (20261014_match_model_compare.sql) with the same answer and two additions:
--   finished.market        the bookmakers' log loss, Brier and share of right results on the
--                          finished matches that have stored prices, with base_priced and
--                          a18_priced: the two models on exactly those matches, so all three are
--                          read on the same games
--   apart[].market         the bookmakers' home, draw and away chances for an upcoming fixture,
--                          or null where no prices are stored yet (about 14 days before kickoff)
-- The bookmakers' chances are the Stats page's (site_record.market_consensus): each bookmaker's
-- complete home/draw/away set with its margin removed, averaged; odds.odd stops updating at
-- kickoff, so it is the closing price. Reads only; odds by fixture (odds_fixture_idx), for the
-- few dozen fixtures in question. Also in db/schema.sql.
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
    ), priced AS (
        SELECT b.fixture_id,
               pg_catalog.avg(b.p) FILTER (WHERE b.sel = 'Home') AS p_home,
               pg_catalog.avg(b.p) FILTER (WHERE b.sel = 'Draw') AS p_draw,
               pg_catalog.avg(b.p) FILTER (WHERE b.sel = 'Away') AS p_away
        FROM (SELECT o.fixture_id, o.selection AS sel,
                     (1 / o.odd::float8) / pg_catalog.sum(1 / o.odd::float8) OVER w AS p,
                     pg_catalog.count(*) OVER w AS k
              FROM public.odds o
              WHERE o.bet_id = 1 AND o.odd > 1 AND o.selection IN ('Home', 'Draw', 'Away')
                AND o.fixture_id IN (SELECT p.fixture_id FROM paired p)
              WINDOW w AS (PARTITION BY o.fixture_id, o.bookmaker_id)) b
        WHERE b.k = 3
        GROUP BY b.fixture_id
    ), rows_all AS (
        SELECT p.model AS who, p.y, p.p_home, p.p_draw, p.p_away FROM paired p
        UNION ALL
        SELECT p.model || '_priced', p.y, p.p_home, p.p_draw, p.p_away
        FROM paired p WHERE p.fixture_id IN (SELECT m.fixture_id FROM priced m)
        UNION ALL
        SELECT 'market', p.y, m.p_home, m.p_draw, m.p_away
        FROM priced m JOIN (SELECT DISTINCT x.fixture_id, x.y FROM paired x) p ON p.fixture_id = m.fixture_id
    ), scored AS (
        SELECT r.who,
               -pg_catalog.ln(GREATEST(CASE r.y WHEN 0 THEN r.p_home WHEN 1 THEN r.p_draw ELSE r.p_away END, 1e-12)) AS loss,
               pg_catalog.power(r.p_home - (r.y = 0)::int, 2) + pg_catalog.power(r.p_draw - (r.y = 1)::int, 2)
                 + pg_catalog.power(r.p_away - (r.y = 2)::int, 2) AS brier,
               (CASE r.y WHEN 0 THEN r.p_home WHEN 1 THEN r.p_draw ELSE r.p_away END
                  >= GREATEST(r.p_home, r.p_draw, r.p_away))::int AS right_result
        FROM rows_all r
    )
    SELECT COALESCE(pg_catalog.jsonb_object_agg(s.who, pg_catalog.jsonb_build_object(
               'n', s.n, 'log_loss', s.log_loss, 'brier', s.brier, 'accuracy', s.accuracy)), '{}'::jsonb)
    INTO finished
    FROM (SELECT who, pg_catalog.count(*) AS n, pg_catalog.avg(loss) AS log_loss,
                 pg_catalog.avg(brier) AS brier, pg_catalog.avg(right_result) AS accuracy
          FROM scored GROUP BY who) s;

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
    ), top AS (
        SELECT * FROM gaps ORDER BY gap DESC, kickoff LIMIT 20
    ), top_priced AS (
        SELECT b.fixture_id,
               pg_catalog.avg(b.p) FILTER (WHERE b.sel = 'Home') AS p_home,
               pg_catalog.avg(b.p) FILTER (WHERE b.sel = 'Draw') AS p_draw,
               pg_catalog.avg(b.p) FILTER (WHERE b.sel = 'Away') AS p_away
        FROM (SELECT o.fixture_id, o.selection AS sel,
                     (1 / o.odd::float8) / pg_catalog.sum(1 / o.odd::float8) OVER w AS p,
                     pg_catalog.count(*) OVER w AS k
              FROM public.odds o
              WHERE o.bet_id = 1 AND o.odd > 1 AND o.selection IN ('Home', 'Draw', 'Away')
                AND o.fixture_id IN (SELECT t.fixture_id FROM top t)
              WINDOW w AS (PARTITION BY o.fixture_id, o.bookmaker_id)) b
        WHERE b.k = 3
        GROUP BY b.fixture_id
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
                       'a18', pg_catalog.jsonb_build_array(t.a_home, t.a_draw, t.a_away, t.a_hxg, t.a_axg),
                       'market', CASE WHEN m.fixture_id IS NULL THEN NULL
                                      ELSE pg_catalog.jsonb_build_array(m.p_home, m.p_draw, m.p_away) END)
                   ORDER BY t.gap DESC, t.kickoff), '[]'::jsonb)
            FROM top t LEFT JOIN top_priced m ON m.fixture_id = t.fixture_id)
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
--   select public.admin_match_model_compare() -> 'finished';   -- base, a18, market, base_priced, a18_priced
--   rollback;
--   select has_function_privilege('anon', 'public.admin_match_model_compare()', 'execute');   -- f
