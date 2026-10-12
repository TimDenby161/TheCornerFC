-- Repeatable. Not yet applied.
-- The Admin area (owner's decision 2026-10-13): Model vs Market and Paper Simulation become the
-- administrator's only, and a Model Change Tracker joins them. Until now the paper bets were a
-- row of site.docs ('bets'), which the public key can read; from this migration the export
-- writes them to admin_docs, and the row in site.docs goes with the next export.
--
--   site_admins          the email address of each administrator. Set in the SQL editor, never
--                        here (the repository is public):
--                          insert into site_admins (email) values ('...') on conflict do nothing;
--                        An address only counts once Supabase Auth has confirmed it (a Google
--                        sign-in, or the emailed link), so signing up with it without that
--                        mailbox passes nothing. Being signed in is not enough, and neither is
--                        being the FPL entry's owner (fpl_team_owners): this is its own list.
--   site.is_admin()      whether the caller is one. In the schema the Data API doesn't expose.
--   am_admin()           the same, for the site's server to ask with a visitor's own token
--                        before it serves anything under /admin. Signed-in callers only.
--   admin_docs           the private documents, one row each, written by the export
--                        (export.store_admin_doc): 'bets' and 'model_changes'.
--   admin_doc(name)      {"ok": true, "doc": ...} for an administrator, {"ok": false} for anyone
--                        else. Fixed SQL, one row by primary key. Signed-in callers only: the
--                        public key alone can't call it.
--   model_changes        one row for each change to a model that was proposed: what was
--                        registered before it was tested, as written. Append only.
--   model_change_events  what happened to it afterwards, in order: results, a decision, a
--                        deployment, a correction. Append only: a correction is a new row, and
--                        nothing recorded is ever rewritten or removed.
-- Both are filled by the export from experiments/changes/*.json
-- (thecornerfc/evidence/model_changes.py). Nothing here is reachable by the public key.
-- Also in db/schema.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS public.site_admins (
    email text PRIMARY KEY CHECK (email = lower(email) AND position('@' in email) > 1)
);
ALTER TABLE public.site_admins ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.admin_docs (
    name text PRIMARY KEY CHECK (name IN ('bets', 'model_changes')),
    doc jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.admin_docs ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.model_changes (
    change_id text PRIMARY KEY CHECK (change_id ~ '^MC-[0-9]{4}$'),
    registration jsonb NOT NULL CHECK (jsonb_typeof(registration) = 'object'),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE public.model_changes ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.model_change_events (
    change_id text NOT NULL REFERENCES public.model_changes(change_id) ON DELETE RESTRICT,
    seq integer NOT NULL CHECK (seq >= 1),
    body jsonb NOT NULL CHECK (jsonb_typeof(body) = 'object'),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (change_id, seq)
);
ALTER TABLE public.model_change_events ENABLE ROW LEVEL SECURITY;

-- What was recorded stays as it was recorded
CREATE OR REPLACE FUNCTION public.guard_model_changes() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'The model change record is append only: record a correction as a new event';
    END IF;
    NEW.recorded_at := pg_catalog.clock_timestamp();
    RETURN NEW;
END;
$$;
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['model_changes', 'model_change_events'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS change_guard ON public.%I', t);
        EXECUTE format('CREATE TRIGGER change_guard BEFORE INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.guard_model_changes()', t);
        EXECUTE format('DROP TRIGGER IF EXISTS change_truncate_guard ON public.%I', t);
        EXECUTE format('CREATE TRIGGER change_truncate_guard BEFORE TRUNCATE ON public.%I FOR EACH STATEMENT EXECUTE FUNCTION public.guard_model_changes()', t);
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION site.is_admin() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT auth.uid() IS NOT NULL AND EXISTS (
        SELECT 1 FROM auth.users u JOIN public.site_admins a ON a.email = pg_catalog.lower(u.email)
        WHERE u.id = auth.uid() AND u.email_confirmed_at IS NOT NULL);
$$;

CREATE OR REPLACE FUNCTION public.am_admin() RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-store"}]', true);
    RETURN site.is_admin();
END;
$$;

CREATE OR REPLACE FUNCTION public.admin_doc(p_name text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM pg_catalog.set_config('response.headers', '[{"Cache-Control": "no-store"}]', true);
    IF NOT site.is_admin() THEN
        RETURN pg_catalog.jsonb_build_object('ok', false);
    END IF;
    RETURN pg_catalog.jsonb_build_object('ok', true,
        'doc', (SELECT d.doc FROM public.admin_docs d WHERE d.name = p_name),
        'updated_at', (SELECT d.updated_at FROM public.admin_docs d WHERE d.name = p_name));
END;
$$;

REVOKE ALL ON public.site_admins, public.admin_docs, public.model_changes, public.model_change_events FROM PUBLIC;
REVOKE ALL ON FUNCTION public.guard_model_changes() FROM PUBLIC;
REVOKE ALL ON FUNCTION site.is_admin() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.am_admin() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_doc(text) FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
    FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
            EXECUTE format('REVOKE ALL ON public.site_admins, public.admin_docs, public.model_changes, public.model_change_events FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION public.guard_model_changes() FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION site.is_admin() FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION public.am_admin() FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION public.admin_doc(text) FROM %I', r);
        END IF;
    END LOOP;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        GRANT EXECUTE ON FUNCTION public.am_admin() TO authenticated;
        GRANT EXECUTE ON FUNCTION public.admin_doc(text) TO authenticated;
    END IF;
END; $$;

COMMIT;

-- Afterwards, in the SQL editor of the same database (the address is not kept in the repository):
--   insert into site_admins (email) values ('<the administrator''s sign-in address, in lower case>') on conflict do nothing;
-- Check afterwards:
--   select has_function_privilege('anon', 'public.admin_doc(text)', 'execute');            -- f
--   select has_function_privilege('anon', 'public.am_admin()', 'execute');                 -- f
--   select has_function_privilege('authenticated', 'public.admin_doc(text)', 'execute');   -- t
--   select has_table_privilege('anon', 'public.admin_docs', 'select'),
--          has_table_privilege('authenticated', 'public.admin_docs', 'select'),
--          has_table_privilege('authenticated', 'public.site_admins', 'select');           -- f, f, f
--   select public.admin_doc('bets');                                                        -- {"ok": false} here: the editor is no signed-in visitor
--   select count(*) from site_admins;                                                       -- 1
--   select name, updated_at from admin_docs order by name;                                  -- bets, model_changes after the next export
--   select count(*) from site.docs where key = 'bets';                                      -- 0 after the next export
--   update model_changes set sha256 = sha256;                                               -- refused once it has rows
