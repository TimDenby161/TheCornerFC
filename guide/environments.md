# Production and staging

There are two copies of the system. Production is the live site and its data. Staging is where
a change is tried first: its own website, database, secrets and workflow, which can reach
nothing of production's.

| | Production | Staging |
|---|---|---|
| Branch | `main`, moved only by promotion | `staging`, where every push lands |
| Site | Worker `thecornerfc`, thecornerfc.com | Worker `thecornerfc-staging`, staging.thecornerfc.com, behind Cloudflare Access |
| Database | The live Supabase project | Its own Supabase project, in its own organisation |
| Jobs | The scheduled workflows, GitHub environment `production` | `Staging pipeline`, by hand only, GitHub environment `staging` |
| API-Football | The key, in the `production` environment | Off unless a run is given a call budget |
| Sign-in, mail, payment | As the site has them | Email sign-in only, no mail service, Turnstile's test key, Stripe test keys only |
| Data | Every competition | England's four divisions and their cups, copied once (`scripts/staging_copy.py`), then built by staging's own runs. The paywall is on, as production's is |

## How each part knows which it is

Nothing trusts a name on its own.

- **The jobs and local commands.** `THECORNERFC_ENV` says `production` or `staging`; with
  neither, nothing writes. Before a session that may write is used (`pipeline/db.py connect()`):
  the address must belong to that environment's Supabase project (`config.PROJECTS`; the project
  is read from the user name of a pooler address or the host of a direct one), and the database
  must answer `site.environment()` with the same word. That row is set once in each database
  and can't then be changed (`db/migrations/20261012_database_environment.sql`).
- **These are checks, not the boundary.** The boundary is that each side's credentials exist
  only on that side: staging's secrets, Worker and local profile hold staging's addresses, which
  do not open production; production's write address is in the `production` GitHub environment
  and nowhere else; this machine holds only a production role that can read.
- **The site.** A build must name its environment (`VITE_SITE_ENV`); with none, or a wrong one,
  the build fails (`web/src/lib/environments.ts`, `web/vite.config.ts`). Each Worker also says
  which it is (`SITE_ENV` in `web/wrangler.jsonc`), and the site serves nothing if the two
  differ. `/version` on either site answers its environment, commit and database project.
- **GitHub.** Production's secrets are in the `production` environment, which only `main` may
  use, and each job that names one also refuses any other branch itself. Staging's secrets have
  their own names (`STAGING_...`), so nothing of production's can stand in for a missing one
  (`tests/test_workflows.py`).

## Switching on this machine

```bash
python scripts/environment.py staging       # develop: may write to staging
python scripts/environment.py production    # look at live data: read-only
python scripts/environment.py status        # which is selected, and what each address may do
```

The addresses are in two files outside the repository, `~/.config/thecornerfc/staging.env` and
`production.env`, each holding an address and nothing else. A switch checks the file and then
replaces `.env` whole, so nothing of the other environment is left; it also writes the site's
environment name in `web/`. It prints no value and never touches git.

- **Production is selected only when the database itself says the role cannot write**: no
  insert, update, delete or create, no passing row-level security, read-only by default.
  Production's write address is never kept on this machine, and neither is the API-Football key.
- **Staging** may write. API-Football stays off. `init-db`, the staging copy and
  `suppress --apply` ask for `staging` to be typed at the terminal.
- Each keeps its own local cache, export and API ledger (`.cache-staging/`, `.export-staging/`).
- The scripts in `experiments/` read whatever is selected. Evaluations are of production's
  record: switch to production first.

## Day to day

1. `python scripts/environment.py staging`, and work on the `staging` branch.
2. Run the checks (`/pre-push`) and push to `staging`. Cloudflare builds the staging site from
   the push; the **Staging** workflow waits for that build and checks it
   (`web/scripts/staging-smoke.mjs`): the site serves this commit, says it is staging, reads the
   staging database, and is closed to anyone without the Access token.
3. If the change needs the pipeline: Actions → **Staging pipeline** → Run workflow, on the
   `staging` branch. "models and export" rebuilds ranks, predictions and the site's data from
   what staging holds. A call budget of 0, the default, makes no API-Football request.
4. Look at staging.thecornerfc.com.
5. Promote (`/promote-production`): `git push origin origin/staging:main`. `main` moves forward
   to the very commit staging tested. GitHub refuses the push unless that commit passed
   `python`, `site` and `staging-check` and was deployed to the `staging` environment, so there
   is no other way onto `main`. Pull requests, Dependabot's included, are opened on `staging`.
6. Check `https://thecornerfc.com/version` names the commit, and the next Match day run is green.

A migration goes to staging first (paste it in the staging project's SQL editor), is checked
there, then to production.

A new staging database is built by pasting the whole of `db/schema.sql` into its SQL editor
once, then setting its identity row. The file builds an empty database; it can't be run a second
time on one that already has it, so after that a database gets migrations one at a time.

## Where every key lives

| Key | Where it comes from | Where it goes |
|---|---|---|
| Production, read-only address | Supabase → production project → Connect → Session pooler, with the user `local_readonly.<project id>` and that role's password | `~/.config/thecornerfc/production.env` as `READ_ONLY_DATABASE_URL=` |
| Staging database address | Supabase → staging project → Connect → Session pooler, with the database password chosen when the project was made | `~/.config/thecornerfc/staging.env` as `DATABASE_URL=`, and the GitHub `staging` environment as `STAGING_DATABASE_URL` |
| Staging project id and publishable key | Supabase → staging project → Settings → API Keys (the id is in the project's address) | In the code, not secret: `PROJECTS` in `thecornerfc/config.py` and `staging` in `web/src/lib/environments.ts` |
| Production database address (write) | Supabase → production project → Connect → Session pooler, with the saved database password | GitHub `production` environment as `DATABASE_URL`. Nowhere else |
| API-Football key | dashboard.api-football.com → Account → My Access | GitHub `production` environment as `API_FOOTBALL_KEY`; and `staging` as `STAGING_API_FOOTBALL_KEY` only if staging is ever to fetch |
| Access service token | Cloudflare → Zero Trust → Access → Service Auth → Create service token | GitHub `staging` environment as `STAGING_ACCESS_CLIENT_ID` and `STAGING_ACCESS_CLIENT_SECRET` |
| The site's environment name | Not a secret: `production` or `staging` | Each Worker → Settings → Build → Variables as `VITE_SITE_ENV` |
| Stripe and the database service key | Stripe's dashboard; Supabase → Settings → API Keys | Each Worker's own secrets (`web/src/env.ts`). Staging takes Stripe **test** keys only: a live key there is treated as no key |

GitHub environments are under the repository's Settings → Environments. `production` allows the
branch `main` only and has no reviewer (its jobs run every 30 minutes); `staging` allows
`staging` only.

## Making the staging Worker again

Cloudflare's "import a repository" form has no branch option, so its first build is from `main`.
To keep that copy from ever being public: on the form set the name `thecornerfc-staging`, build
command `npm run build`, deploy command `npx wrangler deploy --env staging`, path `web`, the
build variable `VITE_SITE_ENV=staging`, preview builds off and "Protect with Cloudflare Access"
on. Then, in the new Worker's Settings → Builds, change the production branch to `staging` and
push to `staging`. The live Worker (`thecornerfc`) builds `main` only: its preview builds are
off, and its build variable is `VITE_SITE_ENV=production`. The lock on staging.thecornerfc.com
is a Zero Trust self-hosted application for that hostname, with one policy allowing the owner's
email and one for the check's service token.

## When something goes wrong

- **The live site is wrong after a promotion.** Cloudflare → Workers → thecornerfc → Deployments
  → Rollback puts the last deployment back in seconds. Then revert the commit on `staging` and
  promote the revert, so `main` matches what is live.
- **A job is wrong.** Revert on `staging` and promote. Until then the site shows the last
  export: a job that fails writes nothing new.
- **A job stops with "the database does not say which it is".** The identity row is missing or
  the address is another project's. Check `python scripts/environment.py status`; never work
  round the check.
- **A migration fails.** Migrations are written to be run twice, and are tried on staging
  first, so a failure should be met there. On production: the SQL editor runs a migration in
  one transaction, so a failed one leaves nothing behind; fix the file, try it on staging, run
  it again. One that ran and was wrong is undone by a new migration, never by editing data by
  hand.
- **Staging is asleep.** A free Supabase project pauses after a week unused. Wake it in the
  dashboard (a few minutes); the staging check fails until then, which holds a promotion back
  and nothing else.
- **A credential may have leaked.** [SECURITY.md](../SECURITY.md), "Rotating a credential".

## What it costs

Nothing a month as set up: the staging database is a free Supabase project (500 MB, shared
CPU, paused after a week unused), so it holds a few leagues, not everything; the staging Worker
is on Cloudflare's free plan and shares the account's 100,000 requests a day and one build at
a time; Cloudflare Access is free up to 50 people; GitHub's environments, rulesets and Actions
are free on a public repository; there is no second API-Football subscription. If staging
outgrows 500 MB, a paid Supabase project is about $10 a month in an organisation already on
Pro, or $25 otherwise.
