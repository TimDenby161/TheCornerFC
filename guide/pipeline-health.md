# Pipeline and dataset health

```bash
python -m thecornerfc health
```

This reads recorded health without making API calls or connecting to Postgres, and
works with local `NO_API` / read-only mode. A fresh ledger reports `UNKNOWN` and an
overall `WARNING` until stages have run. Example after several pipeline runs:

```text
Overall: WARNING
teams HEALTHY
fixtures HEALTHY
standings HEALTHY
players HEALTHY
club_ratings HEALTHY
player_ratings HEALTHY
predictions HEALTHY
injuries STALE
odds HEALTHY
exports HEALTHY
```

The actual report includes a concise explanation for each dataset and the latest
command's status/failed stage. `FAIL` exits 1; warnings and informational results
exit 0. `STALE` means no successful monitored stage within `HEALTH_STALE_HOURS`
(default 72), not that a league should have played a match recently. `RUNNING`
without completion can indicate an interrupted process and is a warning.

Two small tables share the existing SQLite API ledger and its Actions cache/artifact:

- `pipeline_runs`: one row per CLI command, linked by Actions run ID/attempt, with
  workflow, command, code SHA, start/completion, status, failed stages, API attempt
  count, last observed quota during that command, warnings and exception type.
- `dataset_status`: latest attempt, last healthy success, status, row count, latest
  underlying timestamp where available, message, command-run ID, and previous
  successful count. Failed/warning observations never replace the healthy baseline.

The health hooks surround existing ingestion/rating/prediction/export stages. They
also record exceptions caught by the nightly runner. A later successful league in
the same command cannot erase a failure or warning. Health queries are SELECT-only;
monitoring does not change football calculations or refresh schedules. Error
records retain exception types rather than potentially sensitive exception text;
use the existing stage logs for debugging. Hard termination can leave `RUNNING`
records, and cache eviction can lose history, as described under API usage.

Checks distinguish fatal failures from coverage warnings:

- **FAIL:** stage exceptions; player/club-rating/player-rating populations below
  `HEALTH_COLLAPSE_RATIO` (default 20%) of their last healthy count, when that count
  was at least `HEALTH_MIN_BASELINE` (default 100). This uses stored populations,
  not short seasonal windows. First observations establish a baseline.
- **FAIL:** existing staged export validation rejects invalid JSON, missing critical
  files and catastrophic major JSON/detail population shrinkage before publication.
  Export failures are now recorded as dataset and pipeline failures. Existing output
  stays in place when build/validation fails. Full export success updates `exports`;
  matchday's partial bets/injuries exports do not claim a full export succeeded.
- **WARNING:** zero teams/fixtures in league seasons between seven days after their
  recorded start and their end; absent standings only where coverage says standings
  are supported. Checks do not rely solely on the provider's `is_current` flag.
- **WARNING:** upcoming fixtures in the next seven days lack predictions; no odds
  for fixtures in the next three days in leagues with odds in the previous 30 days.
  Empty upcoming windows are informational, including off-season.
- **WARNING:** every successful API response for an ingestion stage is empty. This
  catches silent empty responses even when upserts leave historical DB rows intact,
  including zero injury responses across the major leagues. Empty injuries are
  never automatically fatal and may reflect legitimate coverage/season conditions.

Global row counts describe stored datasets, not rows changed by a single league
sync. Underlying timestamps are table update/provider times, except club ratings
use their latest contributing match; player position ranks have no source timestamp.
These timestamps are distinct from the stage's last successful refresh. Checks flag
suspected issues; they do not roll back model outputs already committed by a stage.
Fatal checks stop normal subsequent publication through the CLI's failure status.

All three Actions workflows include an always-run health summary and persist the
ledger even on failure. No external monitoring service or production schema
migration is required. SQL examples against the downloaded/local SQLite ledger:

```sql
SELECT command, started, completed, status, failed_stage, api_calls, quota_remaining
FROM pipeline_runs ORDER BY started DESC LIMIT 20;
SELECT dataset, last_attempt, last_success, status, row_count,
       latest_data_timestamp, message FROM dataset_status ORDER BY dataset;
```
