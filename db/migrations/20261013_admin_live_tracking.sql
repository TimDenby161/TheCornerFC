-- Repeatable. Not yet applied.
-- The Admin area's third document (owner's decision 2026-10-13): how every change in the model
-- change record that can be run is doing on live matches, written by the Live tracking workflow
-- (experiments/prospective/live_p15.py --store, protocol P15) as 'live_tracking'. admin_docs
-- allowed only the two names it began with (20261013_admin_area.sql), so this lets the third in.
-- admin_doc() already answers any row to an administrator and no one else, so nothing else
-- changes. Until this is applied the workflow's write is refused and the page shows no live
-- figures.
-- Also in db/schema.sql.
BEGIN;
ALTER TABLE public.admin_docs DROP CONSTRAINT IF EXISTS admin_docs_name_check;
ALTER TABLE public.admin_docs ADD CONSTRAINT admin_docs_name_check
    CHECK (name IN ('bets', 'model_changes', 'live_tracking'));
COMMIT;

-- Check afterwards:
--   select pg_get_constraintdef(oid) from pg_constraint where conname = 'admin_docs_name_check';   -- lists the three names
--   select name, updated_at from admin_docs order by name;                                          -- live_tracking after the workflow's next run
--   select has_table_privilege('anon', 'public.admin_docs', 'select');                              -- f, as before
