---
name: pre-push
description: Run every check The Corner FC needs before a push and report each on its own result line - Python unit tests, the site's unit tests and type check, the browser check - then stop for the owner. Use when the owner asks whether work is ready to push, or asks for a push.
---

# Before a push

Work is pushed to `staging`, which builds the staging site and is what the Staging workflow
checks. `main` is production: it moves only by promotion (`/promote-production`), never by a
push of new work. Never push without being asked, and never force-push: give the owner the
command.

Run each check on its own, not chained through a pipe, and read its own result line.

1. **Where this is.** `python scripts/environment.py status`: say which environment is
   selected. `git status --short`, `git log --oneline origin/staging..HEAD`,
   `git diff --stat origin/staging..HEAD`. The branch must be `staging`; if the work is on
   another branch, say so and stop.
2. **Nothing private.** Nothing from `audit/`, no `.env`, no saved feed data
   (`inputs.json.gz`, pickles), no FPL-derived data in a public file. This repository is public.
3. **Python** (the venv is `.venv`, made from `requirements.txt`):
   `python -m unittest discover -s tests`
   The line to read is `OK` (or `OK (skipped=21)` without numpy and scipy), with the count on
   the `Ran N tests` line above it. Log lines printed after it are not the result.
4. **Site unit tests**, from `web/`: `npm test`. Read `Test Files  N passed` and
   `Tests  N passed`.
5. **Types**, from `web/`: `npm run check`. Read `0 ERRORS 0 WARNINGS`. It needs the site's
   environment named, which the switch writes in `web/`: with none it fails, as it should.
6. **Browser**, from `web/`: `npm run build`, then `npm run preview -- --port 4517` in the
   background, then `node scripts/browser-check.mjs`; `node scripts/fantasy-check.mjs` if a
   fantasy page changed. Every line should start `ok`. It reads the selected environment's
   database through the app: run it once. Its checks expect production's data (every league,
   the paywall on, named players), so run it with **production** selected (read-only), and
   switch back to staging afterwards. Against staging's four leagues about ten of its lines
   fail for want of data, not because anything is broken; staging's own check is
   `scripts/staging-smoke.mjs`, which the Staging workflow runs.
7. **If a model file changed**: `tests/test_model_fingerprints.py` passed in step 3 only if
   its table was updated on purpose. Say which model versions will be new.
8. **If a migration is waiting**: say so, whether it has been applied to staging, and whether
   the Python it needs is on `main`.

9. **Cost** (`guide/costs.md`): for each service the diff touches (API-Football, Supabase,
   Cloudflare, GitHub), say what it adds or saves. If it adds cost the owner has not agreed to,
   say so and stop.

Then report: each check with its result line, anything skipped and why, and what the push will
do (Cloudflare builds the staging site; the Staging workflow waits for that build and checks
it). Stop there. Push only if the owner has asked for this push; a general go-ahead from earlier
does not count. After a push, the result to wait for is the `staging-check` job.
