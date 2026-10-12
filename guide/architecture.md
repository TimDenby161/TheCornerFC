# Architecture

What the system is made of, what may depend on what, how data gets from API-Football to a page,
and what deploys. One screen; the topic pages listed in `README.md` have the detail.

## The parts

```
API-Football ──► Python jobs (GitHub Actions) ──► Supabase Postgres ──► SvelteKit site
   (the only        thecornerfc/                               db/schema.sql        web/ (Cloudflare
    match data)     fetch, model, record, export                                    Worker)
```

| Part | Where | Runs |
|---|---|---|
| Jobs | `thecornerfc/`, started as `python -m thecornerfc <command>` (`__main__.py`) | GitHub Actions, on a schedule, from `main` |
| Database | `db/schema.sql`, `db/migrations/` | Supabase. The owner applies migrations by hand |
| Site | `web/` (SvelteKit, `adapter-cloudflare`) | Cloudflare Worker `thecornerfc`, built from `main` |
| Experiments | `experiments/` | By hand, read-only. They judge model changes and are never part of a job |

There is no API server, queue or long-running process of our own: the jobs are batch runs, and
the site's server code is the Worker.

## Inside the jobs

Six folders, with `config.py` (settings and the safety guards) beside them.

| Folder | Job | Depends on |
|---|---|---|
| `pipeline/` | Fetch from API-Football (`api.py`), store (`db.py`, `ingest.py`), the nightly and match-day runs, the query cache, usage and health records | everything below: `ingest.sync_nightly` is the run that calls the models in order |
| `models/` | The numbers: club rank, player ranks and line-ups, match predictions, bets, national teams | `evidence/` to record what they produced |
| `evidence/` | Model versions and the append-only snapshots; the evaluator | `models/` for the functions it replays |
| `fantasy_games/` | FPL and Fantasy EFL: capture, expected points, the owner's team | `models/`, `evidence/` |
| `publish/` | The export: what the site reads | all of the above, read-only |
| `privacy/` | Unconfirmed accounts, retention, removing a person | nothing |

Boundaries that are enforced:

- **Sixteen model files are fingerprinted.** Their bytes are part of each model version's
  identity, so they change only as a deliberate, evaluated model release
  ([Model versions](model-versions.md), `tests/test_model_fingerprints.py`). No two `.py` files
  in the package may share a name.
- **`publish/` has an import order** (`tests/test_publish_imports.py`). `export.py` runs the
  export and passes on every name; the work is in six modules: `site_files` (staging, the
  checks a staged export must pass, publishing, the paid cut), `site_matches`, `site_record`
  (how the models have done), `site_players`, `site_clubs`, `site_fantasy` (owner-only).
  `site_files` imports none of the others, and none imports `export`.
- **Nothing local writes to production** ([Local development safety](local-safety.md)); staging is the
  copy to write to ([Production and staging](environments.md)).

Known and left alone, because fixing them means editing fingerprinted files: `models/` and
`evidence/` import each other inside functions; `models/nations.py` imports two helpers from
`publish.export`; `player_ratings.py` has one 330-line function. Fold each into that model's next
deliberate version.

## How data reaches a page

1. **Fetch.** `nightly` (and `matchday` near kick-offs) calls API-Football through
   `pipeline/api.py`, which counts every call against the daily quota
   ([API usage](api-usage.md)), and upserts rows through `pipeline/db.py`. People removed on
   request are dropped at the upsert.
2. **Model.** The same run rebuilds club ranks, player ranks and predicted line-ups, match
   predictions and paper bets, in that order (`ingest.sync_nightly`). One failed step is
   counted and the rest carry on.
3. **Record.** Each model registers its version and appends snapshots that are never rewritten
   (`evidence/`). That record is what the evaluations read.
4. **Export.** `python -m thecornerfc export` builds the site's data into a staged folder,
   checks it (critical files present, row counts not collapsed against the last export), and
   only then replaces `.export/` and writes it to the database: `site.docs` (one row per page's
   JSON), `site.matches`, `site.players`, `site.lineup_history`. A failed check leaves the last
   export in place. Fantasy data goes to `fpl_owner_docs` for the owner's sign-in only.
5. **Read.** A page's server code (`web/src/lib/server/`) asks the database through functions
   with fixed SQL that the public key may call (`site_doc`, `site_matches`, `site_players` ...).
   The browser talks only to thecornerfc.com. What every visitor shares is kept for a minute
   in the Worker; a signed-in visitor's request carries their own token and is never kept, so
   the database decides what a subscriber sees ([Site data](site-data.md), [Paid tier](paid-tier.md)).

## Inside the site

`web/src/routes/` holds thin pages; logic is in tested `web/src/lib/*.ts`; every database read
is in `web/src/lib/server/`; `hooks.server.ts` finishes sign-ins and sets the cache headers;
`vite.config.ts` holds the security policy; secrets are Worker secrets declared in `src/env.ts`.
Conventions: `.claude/rules/web.md`.

## What deploys, and what gates it

| What | Deploys when | Gate |
|---|---|---|
| The site | `main` moving forward to the commit `staging` tested ([Production and staging](environments.md)): Cloudflare runs the build and deploys the Worker. A push to `staging` does the same for the staging site | `npm run build` runs the unit tests and the type check before `vite build`. A failure fails the build and the last deployment stays live. This holds while Cloudflare's build command is `npm run build` (Workers & Pages → thecornerfc → Settings → Build; the owner confirmed it on 2026-10-12) |
| The jobs | Whatever is on `main` when a schedule fires: nightly 01:17 UTC (two later tries), match day every 30 minutes, FPL at 07:00, 13:00 and 19:00, two backfills by hand | Each job runs `python -m unittest discover -s tests` straight after installing, with no secrets, and stops before it fetches or writes anything if a test fails. The site goes on showing the last export |
| The database | The owner runs a migration in the SQL editor | A test asserts each migration is word for word in `db/schema.sql` |

`.github/workflows/tests.yml` runs both suites on every push and pull request, for an early
answer. The browser check (`web/scripts/browser-check.mjs`) is run by hand before a push: it
needs Chrome and the live database.

The jobs share one concurrency group, so two never write at once. All actions are pinned to
commit SHAs and each job asks for `contents: read` only; nothing is committed by a job.
