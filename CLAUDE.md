# The Corner FC

Football data, club and player ranks, match predictions and a paper betting record, published at
thecornerfc.com. One owner, no team. This repository is public.

How the models work, what every table holds and why each decision was made is in `README.md`
(long: search it by heading, don't read it whole). This file is the short list of what to know
before changing anything.

## The parts

| Folder | What it is |
|---|---|
| `thecornerfc/` | The Python jobs: fetch from API-Football, rank, predict, and export to the database. Run as `python -m thecornerfc <command>`. |
| `db/` | `schema.sql` and dated files in `migrations/`. A Supabase Postgres database. |
| `web/` | The site: SvelteKit, deployed as the Cloudflare Worker `thecornerfc` (`web/wrangler.jsonc`). |
| `docs/` | The old static site (GitHub Pages). `web/` still reads its stylesheets (`docs/assets`) and text pages (`docs/*.html`) at build time, so don't delete or restyle them casually. |
| `tests/` | Python unit tests, with stand-in database connections. |
| `experiments/` | One folder per model experiment, with its evaluator and results. |
| `.github/workflows/` | The scheduled jobs (nightly, match day, FPL, backfills). They write to the database and commit nothing. |
| `audit/` | Private notes, plans and drafts. Gitignored: never commit it or quote it in a public file. |

The site reads only the database, through functions with fixed SQL that the public key is
allowed to call. `docs/data/` is a local export folder and is not in git.

## Commands

Python (the system Pythons lack the packages: make a venv from `requirements.txt` first):

```bash
python -m unittest discover -s tests
python -m thecornerfc export        # read-only locally
```

Site, from `web/`:

```bash
npm run dev
npm test                            # unit tests
npm run check                       # types
node scripts/browser-check.mjs [address]   # drives the pages in headless Chrome
```

Run all three site checks before a push. `browser-check.mjs` catches crashes that fetching a
page can't: add a step to it for each new interactive piece, and wait with its `until()`, not a
fixed sleep. `scripts/depth-check.mjs` and `scripts/fantasy-check.mjs` cover the club squad
pitch and the fantasy pages.

## Rules that must not be broken

- **Local runs are read-only.** `.env` blocks database writes and API-Football calls. Don't set
  the override flag or work around the guard.
- **The owner applies migrations**, in the Supabase SQL editor. Write the file in
  `db/migrations/`, say it is waiting, and once it has been applied mark its first line and the
  copy in `db/schema.sql`.
- **Go easy on the live database.** No repeated full exports, whole-table copies or looped heavy
  calls against it for testing. Test a new function on a local Postgres that holds every table
  it joins at full size, then call it twenty at once live after it is applied.
- **Push only when the tests have passed**, checked on their own `OK` line, not through a pipe
  whose last command can succeed on its own. A push to the branch Cloudflare builds from deploys
  the live site.
- **Fantasy game data is owner-only.** Anything derived from FPL or Fantasy EFL goes only where
  the owner's sign-in can read it (`fpl_owner_data`): never into a public table, file, page or
  server-rendered HTML. Any new use of that data is the owner's decision: ask first.
- **New tables and views are reachable by the public key** unless shut: keep row-level security
  on and revoke `anon` from views.
- **A signed-in visitor's requests** go through `askAs(fetch, locals.token, ...)`, never
  `keptAsk`, and their pages answer `private, no-store`.
- **Lists behind the paywall keep the subscriber's order** with the ranks hidden. Never reorder
  hidden players or drop the list.

## Conventions

Site (`web/`):

- No back buttons on any page. Navigation is the menu and the browser.
- Logic goes in tested `src/lib/*.ts`; database reads in `src/lib/server/`; pages stay thin.
- A page's choices live in its address, through GET forms. No inline styles: computed positions
  are classes from `placed.css` (the security policy forbids inline styles).
- Each page's intro and key come from `src/lib/tabInfo.ts`. Kick-off times go through
  `LocalTime.svelte`.
- Keep `#ad-top` and `#ad-rail` free when laying out a page. Adverts never go on Home, the two
  betting pages, the fantasy pages or the text pages.
- Heavy sums run in the browser, not the Worker (the free plan allows about 10 ms of CPU a
  request).
- Redirects to another site must name it: `redirect(..., { external: [...] })`.
- Secrets are Cloudflare Worker secrets, declared in `src/env.ts`. None in the code.

Python and data:

- A page asks the database for what it shows. Don't add whole-list files or prepared copies of
  whole datasets.
- Model changes are versioned and judged by an evaluator written before the results are seen
  (`experiments/`, `thecornerfc/model_versions.py`).
- API-Football is the only match data source. A new data source needs the owner's yes first.

Commits: one plain sentence saying what the site or job now does, as in `git log`.

## Working with the owner

- Put decisions to the owner as plain multiple-choice questions, one at a time.
- Never commit, push or run anything that writes to production without being asked.
