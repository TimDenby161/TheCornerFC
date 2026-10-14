-- Repeatable. Applied 2026-10-14, to staging and to production.
-- Two match models side by side, with a switch (owner's decision 2026-10-14, step 3 of the plan
-- after P17 and the A18 refit): the jobs run the club-rank model ('base', MC-0028) and the same
-- model with A18's boosted trees on top ('a18'). The one the switch names writes
-- fixture_predictions, which the site, the paper bets and everything else read; each model's last
-- prediction before each kickoff is kept in challenger_predictions, whichever is live, so the two
-- can be compared on the same matches (protocol P18) and A18 always learns from the base model's
-- own history.
--
--   match_model_switch       one row: which model is live. Changed only through
--                            admin_set_match_model(), by an administrator (site_admins).
--   match_model_switches     every change of it, in order: when, which way, by whom. Append only.
--   challenger_predictions   every model, live or not: one row per fixture and model, rewritten
--                            by each run until kickoff and never after it, so it keeps the last
--                            prediction made before the match.
--   admin_match_model()      {"ok": true, "live": ..., "switches": [...]} for an administrator,
--                            {"ok": false} for anyone else. Signed-in callers only.
--   admin_set_match_model(p) the same, after switching to p ('base' or 'a18'); from the next run.
-- Nothing here is reachable by the public key. Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS public.match_model_switch (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    live text NOT NULL DEFAULT 'base' CHECK (live IN ('base', 'a18')),
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO public.match_model_switch (id) VALUES (true) ON CONFLICT (id) DO NOTHING;
ALTER TABLE public.match_model_switch ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.match_model_switches (
    switched_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    live text NOT NULL CHECK (live IN ('base', 'a18')),
    switched_by text NOT NULL,
    PRIMARY KEY (switched_at)
);
ALTER TABLE public.match_model_switches ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.challenger_predictions (
    fixture_id integer NOT NULL REFERENCES public.fixtures(fixture_id) ON DELETE CASCADE,
    model text NOT NULL CHECK (model IN ('base', 'a18')),
    model_version_id text NOT NULL REFERENCES public.model_versions(model_version_id) ON DELETE RESTRICT,
    kickoff timestamptz NOT NULL,
    home_match_rank double precision,
    away_match_rank double precision,
    home_xg double precision NOT NULL,
    away_xg double precision NOT NULL,
    p_home double precision NOT NULL,
    p_draw double precision NOT NULL,
    p_away double precision NOT NULL,
    p_over25 double precision,
    p_btts double precision,
    captured_at timestamptz NOT NULL,
    written_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (fixture_id, model)
);
ALTER TABLE public.challenger_predictions ENABLE ROW LEVEL SECURITY;

-- The switch log is append only, and a challenger prediction stands once its match has kicked off
CREATE OR REPLACE FUNCTION public.guard_match_models() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF TG_TABLE_NAME = 'match_model_switches' THEN
        IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'The switch log is append only';
        END IF;
        NEW.switched_at := pg_catalog.clock_timestamp();
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' OR TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'Challenger predictions are kept';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.kickoff <= pg_catalog.clock_timestamp() THEN
        RETURN NULL;                 -- the match has started: the last prediction before it stands
    END IF;
    IF NEW.kickoff <= pg_catalog.clock_timestamp() THEN
        RETURN NULL;                 -- nothing is written for a match that has started
    END IF;
    NEW.written_at := pg_catalog.clock_timestamp();
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS switch_guard ON public.match_model_switches;
CREATE TRIGGER switch_guard BEFORE INSERT OR UPDATE OR DELETE ON public.match_model_switches
    FOR EACH ROW EXECUTE FUNCTION public.guard_match_models();
DROP TRIGGER IF EXISTS switch_truncate_guard ON public.match_model_switches;
CREATE TRIGGER switch_truncate_guard BEFORE TRUNCATE ON public.match_model_switches
    FOR EACH STATEMENT EXECUTE FUNCTION public.guard_match_models();
DROP TRIGGER IF EXISTS challenger_guard ON public.challenger_predictions;
CREATE TRIGGER challenger_guard BEFORE INSERT OR UPDATE OR DELETE ON public.challenger_predictions
    FOR EACH ROW EXECUTE FUNCTION public.guard_match_models();
DROP TRIGGER IF EXISTS challenger_truncate_guard ON public.challenger_predictions;
CREATE TRIGGER challenger_truncate_guard BEFORE TRUNCATE ON public.challenger_predictions
    FOR EACH STATEMENT EXECUTE FUNCTION public.guard_match_models();

CREATE OR REPLACE FUNCTION public.admin_match_model() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-store"}]', true);
    IF NOT site.is_admin() THEN
        RETURN pg_catalog.jsonb_build_object('ok', false);
    END IF;
    RETURN pg_catalog.jsonb_build_object('ok', true,
        'live', (SELECT s.live FROM public.match_model_switch s),
        'switches', (SELECT pg_catalog.coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                         'at', x.switched_at, 'live', x.live) ORDER BY x.switched_at DESC), '[]'::jsonb)
                     FROM (SELECT w.switched_at, w.live FROM public.match_model_switches w
                           ORDER BY w.switched_at DESC LIMIT 50) x));
END;
$$;

CREATE OR REPLACE FUNCTION public.admin_set_match_model(p_live text) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = '' AS $$
DECLARE who text;
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-store"}]', true);
    IF NOT site.is_admin() OR p_live IS NULL OR p_live NOT IN ('base', 'a18') THEN
        RETURN pg_catalog.jsonb_build_object('ok', false);
    END IF;
    IF (SELECT s.live FROM public.match_model_switch s) IS DISTINCT FROM p_live THEN
        SELECT pg_catalog.lower(u.email) INTO who FROM auth.users u WHERE u.id = auth.uid();
        UPDATE public.match_model_switch SET live = p_live, updated_at = pg_catalog.now() WHERE id;
        INSERT INTO public.match_model_switches (live, switched_by) VALUES (p_live, who);
    END IF;
    RETURN public.admin_match_model();
END;
$$;

REVOKE ALL ON public.match_model_switch, public.match_model_switches, public.challenger_predictions FROM PUBLIC;
REVOKE ALL ON FUNCTION public.guard_match_models() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_match_model() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_set_match_model(text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON public.match_model_switch, public.match_model_switches, public.challenger_predictions FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION public.guard_match_models() FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION public.admin_match_model() FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION public.admin_set_match_model(text) FROM %I', r);
        END IF;
    END LOOP;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        GRANT EXECUTE ON FUNCTION public.admin_match_model() TO authenticated;
        GRANT EXECUTE ON FUNCTION public.admin_set_match_model(text) TO authenticated;
    END IF;
END; $$;

COMMIT;

-- Check afterwards:
--   select live from match_model_switch;                                                         -- base
--   select has_function_privilege('anon', 'public.admin_set_match_model(text)', 'execute');      -- f
--   select has_function_privilege('authenticated', 'public.admin_set_match_model(text)', 'execute');  -- t
--   select has_table_privilege('anon', 'public.challenger_predictions', 'select'),
--          has_table_privilege('authenticated', 'public.match_model_switch', 'select');          -- f, f
--   select public.admin_set_match_model('a18');                                                  -- {"ok": false} here: the editor is no signed-in visitor
--   delete from match_model_switches;                                                            -- refused once it has rows
