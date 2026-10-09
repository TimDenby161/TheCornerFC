# API usage and quota protection

`python -m thecornerfc usage` reports recorded attempts today (UTC), totals by
endpoint and workflow, the latest run, and the last observed daily quota with its
timestamp. It works with `THECORNERFC_NO_API=true` and needs no database connection.
An illustrative populated report is:

```text
API attempts today (UTC): 143; successful: 140
By endpoint: fixtures=120, teams=20, status=3
By workflow: Nightly sync=120, Backfill leagues=23
Latest run 123456/1: 23 attempts
Last observed daily quota: 6850 (at 2026-09-26T10:00:00+00:00)
Subscription allowance period: unconfirmed; no monthly allowance assumed
```

The SQLite ledger defaults to `.api-usage/ledger.sqlite3` (`API_LEDGER_PATH`).
It records each HTTP attempt, including retries and transport failures, with UTC
time, endpoint, SHA-256 parameter digest, workflow, run and process identifiers,
command label, HTTP status, response record count, observed daily quota, duration,
success and a short error category. No API keys, raw parameters or response bodies
are stored. HTTP 200 API errors count as failures. Transport failures have unknown
HTTP status and quota; an attempt is not proof the provider charged a request.
Daily totals reflect this client only, not other consumers of the account.

Actions share the ledger through a separate cache and archive a copy as an artifact
on every run, including failed jobs; summaries appear in logs and the job summary.
The existing shared concurrency group serializes these workflows. Cache eviction,
branch cache scope, artifact retention or abrupt runner termination can leave gaps;
this is lightweight operational tracking, not an authoritative billing ledger.
Download an artifact and point `API_LEDGER_PATH` at its SQLite file to inspect it.
Local ledgers persist on disk. Ledger write errors stop execution rather than silently
continue spending untracked quota. Parallel local processes should use separate run
IDs; the optional budget check is designed for sequential execution, as in Actions.

`API_QUOTA_WARN_THRESHOLDS=2000,1000,500` configures absolute daily remaining-call
warnings. The existing `API_DAILY_RESERVE=200` still applies and is now checked before
retries too. Retry counts and backoff delays are unchanged. The approximately 75,000
subscription allowance has **no confirmed period** in repository configuration;
no monthly or subscription-period reset is assumed or enforced. Quota protection
uses the observed daily remaining header only. A displayed quota may be stale;
the report always includes its observation time.

Manual backfills now accept a `call_budget` (default 2,000 attempts). Before ingestion,
a preflight prints a lower bound for league/team/fixture/standing requests, calls
`status`, and verifies the budget fits above the daily reserve. Stats for newly
fetched fixtures, odds pagination and retries are additional unknown costs. The cap
is enforced across every process in that Actions run, including preflight and retries;
a cap stop may leave a partial backfill that can be resumed in a later run.
For intentional local backfills, use the existing local safety override and share
an explicit unique `API_RUN_ID` and positive `API_RUN_BUDGET` across preflight and sync
commands. `API_RUN_BUDGET=0` disables the extra cap, not the daily reserve. Preflight
requires a positive budget and an observed daily quota header.

Additional SQLite queries (no API calls):

```sql
-- Calls today (UTC)
SELECT count(*) FROM api_calls WHERE timestamp >= date('now');
-- Calls by endpoint / workflow today
SELECT endpoint, count(*) FROM api_calls WHERE timestamp >= date('now') GROUP BY endpoint;
SELECT workflow, count(*) FROM api_calls WHERE timestamp >= date('now') GROUP BY workflow;
-- Processes/commands within runs
SELECT run_id, process_id, command, count(*) FROM api_calls GROUP BY run_id, process_id, command;
-- Last observed remaining daily quota
SELECT quota_remaining, timestamp FROM api_calls
WHERE quota_remaining IS NOT NULL ORDER BY id DESC LIMIT 1;
```
