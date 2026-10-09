# Immutable match prediction capture

`match_prediction_snapshots` is now the domain-specific historical store.
`fixture_predictions` continues serving current website state. Apply the registry
migration first, then `db/migrations/20260926_match_prediction_snapshots.sql`, before
running the updated prediction code. Both are included in `db/schema.sql`. No old
prediction rows are copied, rewritten, or claimed as genuinely captured snapshots.

Nightly, matchday and `predict` all capture through `update_predictions`; the existing
nightly reconstruction path captures through `backfill_predictions`. Current output
and snapshot inserts share one transaction and commit together. Missing snapshot
schema or a failed insert fails the prediction stage rather than silently losing
history. Apply the migration before deploying these writers.

Each row preserves fixture/teams/league, registry version, all W/D/L probabilities,
projected xG, expected margin, likely score, over-2.5 and BTTS probabilities, observed
kickoff (`effective_at`), capture time, DB insertion time and seconds to kickoff
(divide by 60 or 3600 for minutes/hours). `model_reference_at` separately records the
clock used for the rank blend and history window: live computation start or the
historical kickoff for a reconstruction. Capture time is taken after inputs were
read and the prediction computed; it is never backdated to the historical event.

The match-specific `inputs` object records actual calculation arguments:

- Current ranks, LT ALGO baseline ranks, blended match ranks; live reliability,
  fallback starting rank and whether a team's default rank was used.
- Home-at-home and away-at-away goal/xG form pairs, and competition goal averages.
- `sides`, in existing function order: home/away attack splits, home/away home-edge
  adjustments, home/away competition goal bases. The attack split is
  `(attack - current_rank) / 2`; edge is `home_rating - current_rank`.
- `predicted_lines`: home and away `[GK, DEF, MID, FWD]` averages, or null. Partial
  lines remain partial; the existing model uses them only when all are present.
- Home/away missing strengths, preserving null versus measured zero. The model's
  actual fallback to zero stays unchanged.

The registry captures the actual match constants, including home advantage,
European bonus, injury beta, home-edge and attack/defence weights, line weights,
Poisson and market calibration constants, plus source-file digests. These constants
and stored arguments permit the existing `predict_match` calculation to be replayed
without querying today's mutable inputs. No artificial explanation components or
unavailable upstream version IDs are invented. Source digests distinguish changed
code even when a working tree has no trustworthy clean Git SHA.

`source` has three explicit values:

- `prospective`: captured **and inserted** before the kickoff known at observation.
- `reconstruction`: historical/backfilled calculation made later; never eligible
  as genuine pre-event evidence, regardless of its calculated inputs.
- `late_observation`: current-state calculation at/after kickoff. The current model
  can process stale `NS`/`TBD` fixtures up to three hours late; those never become
  prospective snapshots. A DB trigger also downgrades a prospective insert that
  crosses kickoff while the batch is being written.

Normal writers use INSERT with conflict DO NOTHING. Database triggers prohibit
UPDATE, DELETE and TRUNCATE, validate match-model references, and generate insertion
time. The content key includes fixture, model version, source, kickoff, actual inputs
and outputs, but excludes observation/reference clock metadata. An identical retry
keeps the first row and timestamp. A changed prediction, model, input or kickoff
creates a new row. The existing rank blend varies with time-to-kickoff; those input
and output changes are scientifically relevant and are retained. This is a history
of distinct prediction states, not a heartbeat log of every computation.

For prospective evaluation, explicitly filter rather than combining sources:

```sql
SELECT fixture_id, captured_at, effective_at AS kickoff,
       seconds_to_kickoff / 3600 AS hours_to_kickoff, model_version_id,
       p_home, p_draw, p_away, home_xg, away_xg, likely_score
FROM match_prediction_snapshots
WHERE source = 'prospective'
ORDER BY fixture_id, captured_at;
```

Prospective means pre-scheduled-kickoff capture based on the fixture state then
available; it does not certify upstream vendor data timeliness or the actual start
of a rescheduled match. Snapshot capture begins with deployment. The existing
backfill still fills only missing current predictions; it does not manufacture a
retrospective snapshot history for every already-populated fixture.
