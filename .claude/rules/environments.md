# Production and staging

Two copies of everything: production (branch `main`, thecornerfc.com, the live database) and
staging (branch `staging`, staging.thecornerfc.com, its own database). `guide/environments.md`
has the whole picture.

- **Find out where you are first**: `python scripts/environment.py status`. A variable, a file
  name or a branch name is never proof of the environment: the code checks the database's
  address and asks the database, and so should you before anything that writes.
- **Staging** is where work is done. Local commands may write to it; API-Football stays off.
  `init-db`, the staging copy and `suppress --apply` need the owner at a terminal.
- **Production is read-only from here**, always. `python scripts/environment.py production` is
  for looking. Nothing on this machine writes to it or spends its API quota, and no command may
  try: its jobs run in GitHub, and the owner applies its migrations.
- **Never name the environment by hand** (`THECORNERFC_ENV=...`, `VITE_SITE_ENV` in a file) or
  read `.env` or `~/.config/thecornerfc/`. The switch writes them.
- **Experiments and evaluations read production**: switch to production first, and say which
  environment a result came from.
- **Work is pushed to `staging`** (`/pre-push`). `main` moves only by `/promote-production`.
- **A migration** goes to staging first, is checked there, then to production: both by the owner.
- **Secrets** have different names in each: staging's start `STAGING_`. A staging workflow
  never names `DATABASE_URL` or `API_FOOTBALL_KEY` as a secret, and a job that does is held to
  `main` and the `production` environment (`tests/test_workflows.py`).
- **A failure on one side only**: compare `/version` on each site (environment, commit,
  database), then the workflow's run for that environment, then
  `python scripts/environment.py status`.
