# Chronological evaluation

The evaluation CLI reads immutable evidence without API calls, production writes,
model fitting or changes to formulas:

```bash
python -m thecornerfc evaluate matches --from 2026-09-01 --to 2026-10-01 --hours-before 24 --output match-evaluation.json
python -m thecornerfc evaluate lineups --hours-before 1
python -m thecornerfc evaluate betting
python -m thecornerfc evaluate clubs --include-records --output club-experiment.json
python -m thecornerfc evaluate players --include-records --output player-experiment.json
python -m thecornerfc evaluate fantasy
```

Reports are JSON on stdout and optionally in `--output`. `--include-records` includes
selected snapshot rows, IDs, observed inputs and evaluation labels for downstream
experiments; omit it for aggregate-only reports. The SQL transaction is explicitly
read-only and repeatable-read. Local NO_API mode works; configure the usual read-only
DB connection. Fantasy reads the FPL evidence tables below and reports n=0 until a fantasy model writes snapshots.
Missing migrations or database failures fail visibly; no current-table fallback is used.

Selection rules are part of every report:

- Default source is **prospective immutable snapshots**. `--source reconstruction`
  explicitly selects only reconstructed match evidence (matches/clubs); these are
  never pooled with prospective captures. There is no implicit reconstruction.
- `--from` is inclusive and `--to` exclusive. Defaults cover 90 days ending at
  `--as-of` (now by default). Dates without zones mean UTC. Match/lineup/club windows
  use known kickoff; player windows use capture time; betting uses decision time.
- Match/lineup evaluation chooses the latest eligible snapshot per fixture/team at
  least `--hours-before` kickoff (default 0). Capture and database insertion must
  satisfy the cutoff. Reconstructed matches use their explicitly labelled historical
  evidence and do not pretend their capture clock satisfies a pre-event horizon.
- Match scores use regulation time. AET/PEN matches without regulation scores are
  excluded rather than using extra-time totals. Snapshots whose recorded kickoff
  differs from the fixture's current kickoff are excluded to avoid silently changing
  the horizon. Match labels are current DB results observed when evaluation runs;
  **the repository has no immutable match-result revision history**, so `--as-of`
  controls prediction evidence, not historical truth of subsequently corrected scores.
- Market probabilities use only odds captured before the selected prediction (or
  before kickoff for explicit reconstructions). Each complete 1X2 book is normalized
  proportionally, then averaged. No fresh-price guarantee is invented. Paired model
  versus market metrics use exactly the same labelled fixture subset, with its own n.
- Lineup predictions must precede the first recorded official XI, preventing evaluation
  of selections captured after the answer was observed. Labels use the latest official
  observation available by `--as-of`, and require 11 distinct official starters.
  Missing/incomplete official XIs are counted as exclusions. Official capture may be
  post-kickoff; its timestamp and snapshot ID remain in exported records.
- Betting uses genuine captured decisions made before known kickoff and the latest
  attached outcome available by `--as-of`. It does not evaluate mutable legacy bets.

Matches report sample size, winner accuracy (ties use Home/Draw/Away order), multiclass
log loss, multiclass Brier score, class-wise calibration, exact-score accuracy where
a score prediction exists, competition/model-version groups, favourite-probability
buckets, and model/market disagreement (favourite agreement and maximum probability
gap). Class indices 0/1/2 mean Home/Draw/Away. Calibration bins include both n and mean
predicted/observed probabilities. Multiclass Brier sums the three squared errors
(range 0–2); log loss clips the scored probability at 1e-15 for numerical stability.

Lineups report correct starters out of 11, false positives/negatives and role/line
accuracy among correctly identified starters with known roles/lines. Every metric
shows its denominator. Results are grouped by capture horizon and model version.
Start-probability scoring is supported only for actual stored probabilities; the
current binary model reports n=0 for probability calibration, never invented values.

Paper evaluation reports decision/settled/void/unsettled counts, settled stake, P&L,
ROI, average odds, model/fair probabilities, price CLV and probability movement,
edge buckets and strategy versions. Void bets remain in stake totals (returned stake,
zero P&L), but are excluded from probability scoring. Binary Brier is `(p-y)^2`;
calibration/log loss/Brier show the exact scored sample, with a separate market n
when fair probabilities are missing. Unknown closing metrics remain missing. These
are descriptive measurements, not profitability claims or confidence estimates.

Club/player commands provide **experiment evidence**, not a universal validation
metric. Club records are the strengths preserved within labelled match snapshots
and are clearly identified as such, rather than invented independent club snapshots.
Player records are genuinely observed daily rating history. Reports show row counts,
model versions and (for players) unique players/captures. Export records to test an
explicit future target with a chronological training/evaluation split; rating movement
alone is not predictive validation. Freeze experiment parameters using data strictly
before the evaluation window, and compare versions/targets on identical populations.

All reports include source, cutoffs, selection policy, generated time and evaluator
source digest. History begins when snapshot capture was deployed: early reports may
have n=0. Counts describe eligible observed evidence, not all fixtures the provider
could theoretically cover. Coverage diagnostics separately count selected rows with
missing regulation labels or missing/incomplete official XIs. No p-values or universal
model-quality verdicts are inferred from small samples.
