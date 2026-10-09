# Local development safety

Local runs default to safe mode through `.env`:

```bash
THECORNERFC_MODE=local
THECORNERFC_READ_ONLY=true
THECORNERFC_NO_API=true
READ_ONLY_DATABASE_URL=postgresql://readonly_user:...@.../postgres
```

In this mode the app can read the latest production Supabase data, run read-only analysis, export `.export` locally and preview the static site, but it refuses database-write commands and refuses API-Football access before making network requests. Use a genuinely read-only Supabase/Postgres role for `READ_ONLY_DATABASE_URL`; the application also sets read-only transactions, but database permissions are the real safety net.

Command safety:

| Command | Local safe mode? | Needs DB writes? | Needs API-Football? |
|---|---:|---:|---:|
| `python -m thecornerfc export` | Yes | No | No |
| Static website preview from `docs/` | Yes | No | No |
| Read-only SQL/evaluation scripts using `connect()` | Yes | No | No |
| `python -m thecornerfc status` | Blocked | No | Yes |
| `python -m thecornerfc sync ...` | Blocked | Yes | Yes |
| `python -m thecornerfc nightly` | Blocked | Yes | Yes |
| `python -m thecornerfc matchday` | Blocked | Yes | Yes |
| `python -m thecornerfc init-db` | Blocked | Yes | No |
| `python -m thecornerfc rank` | Blocked | Yes | No |
| `python -m thecornerfc predict` | Blocked | Yes | No |
| `python -m thecornerfc player-ratings` | Blocked | Yes | No |
| `python -m thecornerfc fantasy` | Blocked | Yes | No |

Intentional local writes or API calls require all relevant safety flags to be turned off and `THECORNERFC_LOCAL_OVERRIDE=I_UNDERSTAND_THIS_CAN_WRITE_PRODUCTION_DATA_AND_USE_API_QUOTA`. GitHub Actions sets production mode explicitly, so the scheduled production pipelines continue to use the production Supabase credential and API-Football key.
