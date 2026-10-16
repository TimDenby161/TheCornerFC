# The Corner FC

Football data, club and player ranks, match predictions and a paper betting record, published at
thecornerfc.com. One owner, no team. This repository is public.

How the models work, what every table holds and why each decision was made is in `guide/`, one
page per topic, listed in `README.md`: read the page the work touches, not the whole folder.
Start with `guide/architecture.md` (the parts, what may depend on what, how data reaches a page,
what deploys and what gates it). This file is the short list of what to know before changing
anything; the conventions for each part load from `.claude/rules/` when you work in it.

## Read the brain first

Before working on any request, read `.claude/brain/index.md`, then the brain files it names for
the task: the owner's decisions, lessons learned, experiments and the current state. Find the
request in `tasks.md` (or add it, typed Requested, Broken or Recommended), then read the code and
guide pages, then work; a finished task moves to `completed.md` with how it was verified, and
the rest of `tasks.md` is reorganised at once (unblocked, re-checked, re-sorted). Update a brain file only when something important is
learned (a decision, a bug's real cause, a failed approach, a concluded experiment, a change in
what is live), as `index.md` describes, and say so in one line. The brain is local and
gitignored, like `audit/`: never commit it or quote it in a public file. If it is missing (a
fresh clone or a cloud session), carry on from this file and `guide/`.

## The parts

| Folder | What it is |
|---|---|
| `thecornerfc/` | The Python jobs, run as `python -m thecornerfc <command>`. Six folders: `pipeline/` (fetch from API-Football, the database, the nightly and match-day runs), `models/` (ranks, ratings, predictions, bets), `evidence/` (model versions and the append-only snapshots), `fantasy_games/` (FPL and Fantasy EFL), `publish/` (the export to the database), `privacy/` (accounts, retention, removals). `config.py` and `__main__.py` stay at the top. |
| `db/` | `schema.sql` and dated files in `migrations/`. A Supabase Postgres database. |
| `web/` | The site: SvelteKit, deployed as the Cloudflare Worker `thecornerfc` (`web/wrangler.jsonc`). Its stylesheets are in `src/styles`, its text pages in `src/text`. |
| `guide/` | The written explanation, one page per topic. `README.md` is its contents list. |
| `tests/` | Python unit tests, with stand-in database connections. |
| `experiments/` | One folder per model experiment, with its evaluator and results. |
| `.github/workflows/` | The scheduled jobs (nightly, match day, FPL, backfills): they write to the database and commit nothing, and each runs the unit tests first. `tests.yml` runs both test suites on every push. |
| `scripts/` | `environment.py`: the switch between staging and production on this machine. `already_ran.py`: whether a scheduled job's slot is already done. |
| `timer/` | The Cloudflare Worker `thecornerfc-timer`: Cron Triggers that start the nightly, match-day and FPL jobs on time (GitHub's schedules are the back-up). |
| `audit/` | Private notes, plans and drafts. Gitignored: never commit it or quote it in a public file. `audit/system-plan.md` is the owner's plan for the whole system. |
| `.claude/brain/` | Claude's working knowledge of the project (start at `index.md`). Gitignored, like `audit/`. |

The site reads only the database, through functions with fixed SQL that the public key is
allowed to call. `.export/` is a local export folder and is not in git.

## Commands

There are two copies of everything, production and staging: `guide/environments.md`. Find out
which this machine is on before anything else, and never take a variable's word for it:

```bash
python scripts/environment.py status       # which is selected, and what each address may do
python scripts/environment.py staging      # develop: may write to staging
python scripts/environment.py production   # look at live data: read-only
```

Python (the jobs run on 3.13; the system Pythons lack the packages, so use the venv, `.venv`,
made on this Mac with `/opt/homebrew/bin/python3.14 -m venv .venv`, then
`pip install -r requirements.txt`):

```bash
python -m unittest discover -s tests    # the result is its own `OK` line
python -m thecornerfc export            # production mode: writes .export/ only. Staging mode: also writes staging's database
python db/check_local_access.py         # what this machine's database addresses may do
```

Site, from `web/`:

```bash
npm run dev
npm test                            # unit tests
npm run check                       # types
node scripts/browser-check.mjs [address]   # drives the pages in headless Chrome
```

Run all three site checks before a push (`/pre-push` runs everything and reports each result
line). `npm run build` runs the first two before it builds, which is what gates a deploy.
`browser-check.mjs` catches crashes that fetching a page can't: add a step to it for each new
interactive piece, and wait with its `until()`, not a fixed sleep. `scripts/fantasy-check.mjs`
covers the fantasy pages.

Skills: `/new-migration` (any database change), `/model-experiment` (any change to a model),
`/pre-push` (work goes to `staging`), `/promote-production` (the only way onto `main`), `/add-task` (puts one task on the brain's list).

## Rules that must not be broken

- **Never add cost.** Before building any change, work out what it costs on each service it
  touches: API-Football (calls a day), Supabase (storage, Disk IO, egress, compute), Cloudflare
  (Worker requests, CPU, builds) and GitHub (free only while public). Pick the design that adds
  nothing; if a change would raise a bill or need a higher plan, ask the owner first and say the
  cost. Each plan's limits are in `guide/costs.md`.
- **Production is never written from this machine**, and no local run calls API-Football.
  Staging is the copy to write to. Don't set the override flag, name the environment by hand or
  work around a guard, and don't read `.env` or `~/.config/thecornerfc/`
  (`guide/environments.md`, `guide/local-safety.md`).
- **`main` moves only by promotion** of the commit `staging` tested
  (`git push origin origin/staging:main`). Work is pushed to `staging`.
- **Seventeen model files are fingerprinted**: their bytes are part of each model version's
  identity, so any edit, even a comment, starts a new model version. Never touch one to tidy,
  rename or reformat it; change one only as a deliberate model release (`/model-experiment`,
  `guide/model-versions.md`). The list is in `tests/test_model_fingerprints.py`. No two `.py`
  files in `thecornerfc/` may share a name.
- **The owner applies migrations**, in the Supabase SQL editor, to staging first. Write the file in
  `db/migrations/`, say it is waiting, and once it has been applied mark its first line and the
  copy in `db/schema.sql`.
- **Go easy on the live database.** No repeated full exports, whole-table copies or looped heavy
  calls against it for testing. Test a new function on a local Postgres that holds every table
  it joins at full size, then call it twenty at once live after it is applied.
- **Push only when the tests have passed**, checked on their own `OK` line, not through a pipe
  whose last command can succeed on its own. A push to `staging` deploys the staging site; a
  promotion to `main` deploys the live one.
- **Fantasy game data is owner-only.** Anything derived from FPL or Fantasy EFL goes only where
  the owner's sign-in can read it (`fpl_owner_data`): never into a public table, file, page or
  server-rendered HTML. Any new use of that data is the owner's decision: ask first.
- **New tables and views are reachable by the public key** unless shut: keep row-level security
  on and revoke `anon` from views.
- **A signed-in visitor's requests** go through `askAs(fetch, locals.token, ...)`, never
  `keptAsk`, and their pages answer `private, no-store`.
- **The Admin area is the administrator's only** (`guide/admin-area.md`): the paper bets live in
  `admin_docs`, read through `adminDoc(fetch, locals.token, ...)` on a page under `/admin`, never
  in `site.docs`, `.export` or a public page, and so do the model switch and anything about
  matches still to be played. The model change record and its live tests are also public, on
  The Model (`/model`, owner's decision 2026-10-16), as `model.json` without the Admin notes
  (`site_record.public_model`). The files in `experiments/changes/` are added to, never edited.
- **Lists behind the paywall keep the subscriber's order** with the ranks hidden. Never reorder
  hidden players or drop the list.

## Conventions

Each part's conventions are in a rule file that loads when you open a file there:

- `.claude/rules/web.md`: the site (`web/`)
- `.claude/rules/python.md`: the jobs, tests and experiments, and the `publish/` import order
- `.claude/rules/database.md`: migrations and what the public key may reach (`db/`)
- `.claude/rules/environments.md`: production and staging, and how to tell which you are on

Two that apply everywhere: model changes are versioned and judged by an evaluator written
before the results are seen (`experiments/`, `thecornerfc/evidence/model_versions.py`), and
API-Football is the only match data source (a new one needs the owner's yes first).

Commits: one plain sentence saying what the site or job now does, as in `git log`.

## Working with the owner

- Put decisions to the owner as plain multiple-choice questions, one at a time.
- Never commit, push or run anything that writes to production without being asked.
