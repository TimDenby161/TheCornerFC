---
paths:
  - "db/**"
---

# The database (`db/`)

- **The owner applies migrations**, in the Supabase SQL editor. Never run one. Write the file in
  `db/migrations/` as `YYYYMMDD_what_it_does.sql`, say it is waiting, and once the owner says it
  has been applied mark its first line and the copy in `db/schema.sql`.
- Every migration is also in `db/schema.sql`, word for word: the tests assert it
  (`assertIn(MIGRATION.read_text(), schema)`). Write migrations so they can be run twice.
- **New tables and views are reachable by the public key** unless shut: `alter table ... enable
  row level security`, and for a view revoke `anon` and `authenticated` (views skip row level
  security). A function the site calls has fixed SQL and a pinned `search_path`.
- **Fantasy game data is owner-only**: anything derived from FPL or Fantasy EFL goes only where
  the owner's sign-in can read it (`fpl_owner_data`).
- **No added cost** (`guide/costs.md`): say what a change adds in storage, Disk IO and egress
  before writing it; anything that could need a higher Supabase plan goes to the owner first.
- **Go easy on the live database.** No repeated full exports, whole-table copies or looped
  heavy calls for testing. Test a new function on a local Postgres that holds every table it
  joins at full size, then call it twenty at once live after it is applied.
- A Python change a migration depends on must be on `main` (where the jobs run) before the
  migration is applied.
