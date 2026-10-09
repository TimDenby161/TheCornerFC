# Immutable daily player-rating history

Apply `db/migrations/20260926_player_rating_history.sql` after the model registry
migration before deploying this writer. Existing ranking/player tables and formulas
are unchanged. No historical ratings or ranks are fabricated from current data.

The first successful player-rating rebuild each UTC day stores a complete capture:
`player_rating_captures` holds observation time, DB write time, player model version,
season and population; `player_rating_history` holds each player's rating, world
rank, position/group, team and team-source, rolling-window minutes, season minutes,
and season-model versus fallback rating source. `player_rating_snapshot_history`
joins these into one convenient read view. Daily header and rows commit atomically
with the current rating rebuild. A failed transaction leaves the day available for
retry. Later same-day rebuilds do not replace that day's capture, even if values or
versions change; this is daily movement history, not intraday tracking.

World rank is the descending competition rank of the entire **captured currently
rated population** (ties share a rank, e.g. 1, 1, 3). It is not a claim to cover all
players worldwide or necessarily the frontend's filtered population. Ratings are
stored at the same one-decimal precision as the current player table. Team is the
latest observed squad assignment where present, otherwise the season model's team,
otherwise NULL; `team_source` makes that distinction explicit. It records what was
known, not a verified transfer registry. Zero season minutes remain zero (estimated
season evidence), and missing evidence stays NULL.

All UPDATE, DELETE and TRUNCATE operations on the new history tables are blocked
in normal operation. Daily uniqueness plus a transaction lock prevents duplicate
captures. Model versions include relevant configuration and player-code digests.

```sql
SELECT * FROM player_rating_movement WHERE player_id = 123;
```

This view supplies `7d`, `30d`, `90d` and `season` comparisons using only persisted
history. Day horizons select the latest actual observation at or before the cutoff;
season movement uses the earliest earlier observation in the current captured season.
`baseline_at` shows the exact baseline, including gaps or a mid-season start of
capture. Missing baselines produce NULL movement, not zero or a reconstruction.
Positive `rating_change` means increased rating; positive `rank_movement` means an
improved rank. `model_changed` and both model IDs flag cross-version comparisons;
`population` and `baseline_population` expose changing comparison populations.
A player's latest capture time remains visible if they later leave the rated cohort.
The global season label follows the existing model's `this_season` calculation,
not an inferred per-league calendar. Time elapsed before this feature's deployment
has no genuine observations and cannot supply movement baselines.

Expected annual growth at daily frequency is **365 × captured player count** (366
in a leap year), plus 365 tiny header rows. The checked-in player export currently
contains **7,532 players**, a useful proxy rather than a measurement of the full
rated DB population: approximately **2,749,180 rows/year**. Budgeting roughly
**250–400 bytes per row including the heap and two indexes** gives approximately
**0.69–1.10 GB/year** (decimal units), excluding WAL, backups, replicas and bloat.
At 20,000 captured players the estimate is **7.3 million rows / 1.83–2.92 GB/year**.
These are planning estimates; header-level shared metadata avoids repeating long
version IDs/timestamps in every player row. No retention/deletion job is introduced.

Measure the actual population and storage after deployment:

```sql
SELECT captured_at, population, population * 365::bigint AS annual_rows
FROM player_rating_captures ORDER BY captured_at DESC LIMIT 1;
SELECT pg_size_pretty(pg_total_relation_size('player_rating_history')) AS history_with_indexes,
       pg_size_pretty(pg_total_relation_size('player_rating_captures')) AS captures_with_indexes;
```
