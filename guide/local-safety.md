# Local development safety

A local run must not be able to write to the production database or spend API-Football quota.
Since 2026-10-12 there is a staging copy to write to instead ([Production and staging](environments.md)),
and nothing on this machine writes to production at all. Three things stand in the way,
strongest first.

## 1. No write address on the machine

`.env` is written by `python scripts/environment.py staging|production`, from a profile kept
outside the repository, and is never edited by hand. In production mode it holds one address,
a role that can only read, under both names (the scripts in `experiments/` read `DATABASE_URL`
directly), no API key and both flags on. The switch asks the database before it selects
production, and refuses unless the role has no insert, update, delete or create, does not pass
row-level security, and is read-only by default. Production's write address and the
API-Football key live in GitHub's `production` environment, where the jobs run.

To see what each address may do, without showing either:

```bash
python scripts/environment.py status
python db/check_local_access.py
```

## 2. The code refuses

Whatever `.env` says:

- A run that names no environment, or names production outside a GitHub Actions run, connects
  with the read-only address in a read-only session, and `require_db_write` raises
  `SafetyError` (`config.writes_allowed`, `tests/test_safety_guards.py`). The override token no
  longer changes that: it lifts the API block for a local **staging** run only.
- A run that may write (a job, or a local run in staging mode) goes no further unless its
  address belongs to its own environment's project and the database says the same of itself.
- `require_api_access` and `require_fpl_access` raise before any request unless the run is a
  job, or a local staging run carrying the token with the API flag switched off.

In production mode, locally:

| Command | Local safe mode? | Needs DB writes? | Needs API-Football? |
|---|---:|---:|---:|
| `python -m thecornerfc export` | Yes (writes `.export/` only) | No | No |
| `python -m thecornerfc health`, `usage`, `evaluate` | Yes | No | No |
| The site: `npm run dev` in `web/` | Yes (it reads the database with the public key) | No | No |
| Read-only scripts using `connect()` | Yes | No | No |
| `python -m thecornerfc status` | Blocked | No | Yes |
| `python -m thecornerfc sync ...` | Blocked | Yes | Yes |
| `python -m thecornerfc nightly` | Blocked | Yes | Yes |
| `python -m thecornerfc matchday` | Blocked | Yes | Yes |
| `python -m thecornerfc init-db` | Blocked | Yes | No |
| `python -m thecornerfc rank` | Blocked | Yes | No |
| `python -m thecornerfc predict` | Blocked | Yes | No |
| `python -m thecornerfc player-ratings` | Blocked | Yes | No |
| `python -m thecornerfc fantasy`, `fpl ...` | Blocked | Yes | No |

In staging mode the "Blocked" commands that need only the database run against staging, and
those that need API-Football stay blocked. Production's jobs are started from GitHub, and a
person is removed with the **Remove a person** workflow ([Retention](retention.md)).

## 3. Claude Code

`.claude/settings.json` stops a session reading `.env` and the profiles, asks before any
`python -m thecornerfc` command that writes or calls an API, `psql`, a commit, a push, a deploy
or a switch to production, and runs `.claude/hooks/guard.py` before every shell command. The
hook refuses a command that sets the override, switches either flag off, sets production mode,
names the environment by hand, sets `DATABASE_URL`, switches FPL capture on, pretends to be a
GitHub Actions run, reads `.env` or a profile (`cat`, `grep`, `source` and the like), forces a
push, or pushes to `main` in any form but the promotion. A command that only mentions those
names, such as a search for one, is let through. `tests/test_claude_guard.py` holds the list of
both kinds.
