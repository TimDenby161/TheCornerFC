# Local development safety

A local run must not be able to write to the production database or spend API-Football quota.
Three things stand in the way, strongest first.

## 1. No write address on the machine

`.env` should hold only a role that can read:

```bash
THECORNERFC_MODE=local
THECORNERFC_READ_ONLY=true
THECORNERFC_NO_API=true
READ_ONLY_DATABASE_URL=postgresql://local_readonly:...@.../postgres
DATABASE_URL=<the same read-only address>
API_FOOTBALL_KEY=
```

The write address and the API key live in GitHub's repository secrets, where the jobs run. With
both names holding the read-only role, nothing on the machine can write, whatever is run. The
scripts in `experiments/` connect with `DATABASE_URL` directly, so it needs a value: the
read-only one.

To see what each address may do, without showing either:

```bash
python db/check_local_access.py
```

It prints the role each one signs in as and `cannot write` or `CAN WRITE`, and exits 1 if either
can. The role should have `select` only and `default_transaction_read_only = on`.

## 2. The code refuses

Whatever `.env` says, outside a GitHub Actions run and without the override token:

- `config.DATABASE_URL` is the read-only address, and `connect()` opens a read-only session.
  Switching `THECORNERFC_READ_ONLY` off on its own does not reach the write address
  (`config.writes_allowed`, `tests/test_safety_guards.py`).
- `require_db_write`, `require_api_access` and `require_fpl_access` raise `SafetyError` before
  any write or request.

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

An intended local write needs all of: a write address in `DATABASE_URL`, the read-only and
no-API flags switched off, and `THECORNERFC_LOCAL_OVERRIDE` set to the token in
`thecornerfc/config.py`. GitHub Actions sets production mode itself, so the scheduled jobs are
unaffected.

## 3. Claude Code

`.claude/settings.json` stops a session reading `.env`, asks before any
`python -m thecornerfc` command that writes or calls an API, `psql`, a commit, a push or a
deploy, and runs `.claude/hooks/guard.py` before every shell command. The hook refuses a
command that sets the override, switches either flag off, sets production mode, sets
`DATABASE_URL`, switches FPL capture on, pretends to be a GitHub Actions run, or reads `.env`
(`cat`, `grep`, `source` and the like). A command that only mentions those names, such as a
search for one, is let through. `tests/test_claude_guard.py` holds the list of both kinds.
