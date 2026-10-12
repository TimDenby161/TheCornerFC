---
name: pre-push
description: Run every check The Corner FC needs before a push and report each on its own result line - Python unit tests, the site's unit tests and type check, the browser check - then stop for the owner. Use when the owner asks whether work is ready to push, or asks for a push.
---

# Before a push

A push to `sveltekit` deploys the live site (Cloudflare builds it). The scheduled jobs run from
`main`. Never push without being asked, and never force-push: give the owner the command.

Run each check on its own, not chained through a pipe, and read its own result line.

1. **What is going out.** `git status --short`, `git log --oneline origin/<branch>..HEAD`,
   `git diff --stat origin/<branch>..HEAD`. Name the branch and what a push to it does.
2. **Nothing private.** Nothing from `audit/`, no `.env`, no saved feed data
   (`inputs.json.gz`, pickles), no FPL-derived data in a public file. This repository is public.
3. **Python** (a venv from `requirements.txt`; on this Mac `/opt/homebrew/bin/python3.14`):
   `python -m unittest discover -s tests`
   The line to read is `OK` (or `OK (skipped=17)` without numpy and scipy), with the count on
   the `Ran N tests` line above it. Log lines printed after it are not the result.
4. **Site unit tests**, from `web/`: `npm test`. Read `Test Files  N passed` and
   `Tests  N passed`.
5. **Types**, from `web/`: `npm run check`. Read `0 ERRORS 0 WARNINGS`.
6. **Browser**, from `web/`: `npm run build`, then `npm run preview -- --port 4517` in the
   background, then `node scripts/browser-check.mjs`; `node scripts/fantasy-check.mjs` if a
   fantasy page changed. Every line should start `ok`. It reads the live database through the
   app: run it once.
7. **If a model file changed**: `tests/test_model_fingerprints.py` passed in step 3 only if
   its table was updated on purpose. Say which model versions will be new.
8. **If a migration is waiting**: say so, and whether the Python it needs is on `main`.

Then report: each check with its result line, anything skipped and why, and what the push will
do. Stop there. Push only if the owner has asked for this push; a general go-ahead from earlier
does not count.
