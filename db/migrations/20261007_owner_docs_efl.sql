-- Repeatable. Applied 2026-10-07. The EFL Fantasy predictions have been owner-only since 2026-10-04 (audit L11): the
-- export writes them to fpl_owner_docs as 'efl_predictions' (export.store_owner_doc), but the
-- table's check allowed only the two FPL names, so every write since then was refused and the tab
-- said "No upcoming EFL gameweeks yet." This lets the third name in. fpl_owner_data already
-- returns every row, so nothing else changes; the next export stores the document.
-- Also in db/schema.sql.
BEGIN;
ALTER TABLE fpl_owner_docs DROP CONSTRAINT IF EXISTS fpl_owner_docs_name_check;
ALTER TABLE fpl_owner_docs ADD CONSTRAINT fpl_owner_docs_name_check
    CHECK (name IN ('fpl_predictions', 'fpl_team', 'efl_predictions'));
COMMIT;

-- Check afterwards:
--   select pg_get_constraintdef(oid) from pg_constraint where conname = 'fpl_owner_docs_name_check';   -- lists the three names
--   select name, updated_at from fpl_owner_docs order by name;                                          -- efl_predictions after the next export
