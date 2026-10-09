# My FPL team

The **My FPL team** page runs the owner's own FPL team (entry 3996593, `FPL_TEAM_ENTRY`): it
suggests this week's transfers, plans the next six gameweeks, sets the line-up and captain, and
says when to play each chip left. **Owner's decision, 2026-09-30:** read FPL's manager endpoints
for this entry (`entry/{id}/`, `entry/{id}/history/`, `entry/{id}/transfers/`,
`entry/{id}/event/{gw}/picks/`) and show the squad, plan and chip advice publicly. It's a new FPL
source under the licensing notes above, and no other entry is read. Since 2026-10-02 the page is
for the owner only (see the licensing notes): its menu entry, and the FPL tab's, appear once the owner has
signed in in that browser (README: Accounts).

- `python -m thecornerfc fpl team` (in the FPL update and nightly workflows, after the export)
  stores `fpl_team` in `fpl_owner_docs`: the squad after any transfers already made for the next
  deadline, each player's selling price (bought at FPL's start price, or at `element_in_cost` for
  later buys, keeping half of any rise), bank, free transfers (1 a week up to 5, less those used;
  a Wildcard or Free Hit week keeps them), chips with their windows from `bootstrap-static`, and
  the season's history. API-Football ids come from `fpl_id_map_current`.
- The planning runs in the browser (`docs/assets/fpl-planner.js`, tested by
  `tests/fpl_planner.test.mjs`) from `fpl_predictions`. It's a beam search over six weeks.
  Each week it rolls the free transfer or makes the best one, two or three moves, and a move
  beyond the free ones costs 4 points. A squad scores its best legal XI with the captain doubled,
  plus 0.1 of the bench. Each later week is weighted 0.9 of the one before, and a free transfer
  still banked at the end is worth 1.5 points. Chips: Triple Captain's gain is the captain's
  points, Bench Boost's the bench's, Free Hit's the best one-week squad over the planned one, and
  Wildcard's the best squad over six weeks against the plan (first four weeks only). A chip is
  advised once its week's gain reaches 10 / 18 / 12 / 15, which usually takes a double
  gameweek. Otherwise it's held, unless its window closes within the predictions. All of these
  numbers are judgment, not fitted.
- **Locking in.** "I've made these transfers" calls `lock_fpl_transfers` in Supabase with the
  week's moves. The page then plans from the squad after them, until the next FPL update reads
  the real transfers from FPL (FPL's squad wins). The page carries Supabase's public anon key
  (`SUPABASE` in `app.js`), and CSP `connect-src` allows only this project.
  `lock_fpl_transfers` / `unlock_fpl_transfers` and `fpl_owner_data` (which returns the lock-ins)
  are SECURITY DEFINER, can be called by signed-in visitors only, and do nothing unless the
  caller's confirmed email address is the one in `fpl_team_owners` for the entry
  (`db/migrations/20261004_fpl_owner_login.sql`; before 2026-10-04 they checked a passphrase).
  `20260930_fpl_team_locks.sql` also revokes anon's read of the `upcoming_predictions` view,
  since views skip RLS.

  One-time setup:
  1. Run `db/migrations/20260930_fpl_team_locks.sql` in the Supabase SQL editor (it's also in
     `db/schema.sql`).
  2. Put the project's anon (or publishable) key from Supabase → Project Settings → API Keys into
     `SUPABASE.key` in `docs/assets/app.js`.
  3. Run `db/migrations/20261003_fpl_owner_docs.sql` (owner-only FPL data; applied 2026-10-03,
     also in `db/schema.sql`).
  4. Run `db/migrations/20261004_fpl_owner_login.sql` (applied 2026-10-04, also in `db/schema.sql`), then say whose sign-in is the owner's:
     `INSERT INTO fpl_team_owners VALUES (3996593, 'owner@example.com') ON CONFLICT (entry_id) DO UPDATE SET email = EXCLUDED.email;`
