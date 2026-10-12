---
name: new-migration
description: Write a database migration for The Corner FC the way this repository needs it - a dated file in db/migrations, shut to the public key, copied word for word into db/schema.sql, with a test that it is there, left for the owner to apply. Use when a change needs a new or altered table, view, function, grant or policy.
---

# A new migration

The owner applies every migration by hand in the Supabase SQL editor. Never run one, and never
connect to the database to change it.

1. **Read first.** `guide/` page for the feature, the nearest earlier migration in
   `db/migrations/` (copy its shape), and the matching part of `db/schema.sql`.
2. **Write `db/migrations/YYYYMMDD_what_it_does.sql`** (today's date).
   - First line: `-- Repeatable. Not yet applied.` Then a comment saying what it is for and
     whose decision it was, with the date.
   - Make it safe to run twice: `create ... if not exists`, `create or replace`,
     `drop ... if exists` before a re-create.
   - A new table: `alter table ... enable row level security;` and no policy unless one is
     needed. A new view: `revoke all on ... from anon, authenticated;`.
   - A function the site calls: fixed SQL (no SQL built from its arguments), `set search_path`,
     and `grant execute` to exactly the roles that need it.
   - Anything derived from FPL or Fantasy EFL: owner-only, through `fpl_owner_data`. If this is
     a new use of that data, stop and ask the owner first.
3. **Copy it into `db/schema.sql`**, word for word, at the end (or replacing the earlier
   version of the same object).
4. **Add the test** that the two match, in the test file for the feature, as the others do:
   `self.assertIn(MIGRATION.read_text(), (ROOT / 'db/schema.sql').read_text())`.
5. **Test a new function before it goes live**: on a local Postgres that holds every table it
   joins at full size. There is usually none on this machine: say so, and give the owner the
   query to try in the SQL editor instead. Never loop heavy calls against the live database.
6. **Check the order.** If Python on `main` must change first (the jobs run from `main`), say
   which commit has to be there before the migration is applied.
7. **Run** `python -m unittest discover -s tests` and read its own `OK` line.
8. **Tell the owner** the file is waiting, in one line, with anything they must do after it
   (a workflow to run, a setting to switch).
9. **Once the owner says it is applied**: change the first line to
   `-- Repeatable. Applied YYYY-MM-DD.` in the migration and in its copy in `db/schema.sql`.
