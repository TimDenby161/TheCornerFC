# Research round, October 2026: the register

**Written 2026-10-12, before any candidate was scored on the final period.** This is the shared
protocol for three offline experiments that look for structural improvements to the match
model: `experiments/rating_dynamics`, `experiments/architectures` and
`experiments/goals_home_scores`. Each has its own `DESIGN.md`; what they share is here.

Nothing in this round changes production. No model file, database row, scheduled job or paper
bet is touched, and nothing is deployed whatever is found. A candidate that meets its bar earns
a proposal to the owner and a prospective check, not a release.

## Inputs

One read of production through the read-only role, frozen in `inputs.json.gz` (gitignored feed
data, `extract.py`): every finished fixture kicked off before 2026-10-12 with its match
statistics, the stored projection of each, the leagues, the formations and managers on the
line-ups, and the stored 1X2 prices. Every experiment reads that file and nothing else.

`frame.py` holds copies of production's rank replay and probability step so that years of
matches can be re-run in seconds without the database. They are checked against what
production stored: the result probabilities match on all 102,375 scored matches to 3e-15, and
the replayed match ranks are within one point of the stored ones on 99.5% of reconstructed rows
(the rest moved because results and xG arrived after those rows were written). The baseline in
every comparison is production **replayed through the frame** on the same matches, so both
sides of a comparison come from the same machinery; it scores 0.99760 on all scored matches
against 0.99761 for the stored predictions.

## Periods

| Period | Kickoff (UTC) | Used for |
|---|---|---|
| Burn-in | before 2021-07-01 | Ratings settle. Never scored. |
| Development | 2021-07-01 to 2024-06-30 | Diagnostics, model selection, every tuned number. |
| Selection window | 2022-07-01 to 2024-06-30 | The part of development that settings are chosen on. |
| Final | 2024-07-01 to 2026-10-11 | Scored once per registered candidate, with frozen settings. |

- **Walk-forward throughout.** A prediction for a match uses only matches that kicked off
  before it (before its day, for the running figures). Models that are fitted are refitted
  forward in time: every week for the Poisson model, every half-season for the boosted trees.
- **Why the selection window starts a year in.** Every club starts from a hand-set rank in
  February 2020. The diagnostics show 2021/22 still carrying those starts (the Premier League's
  average rank was falling 27 to 40 points a season until 2023/24). A setting chosen on that
  season would be fitted to the cold start, which production today no longer has.
- **Two stages in each evaluator.** `develop` chooses settings and writes `chosen.json`.
  `final` reads it and scores the final period. `final` is run once, after the evaluator's
  SHA-256 is recorded in the experiment's `DESIGN.md`.

## What was already seen of the final period

The final period is not untouched. The 12 October audit and the two experiments that followed
looked at it: calibration by band, draw rates, goal level and home advantage by season and
league, the sharpening and draw-boost candidates, and the cup-tie level shifts. This round's
hypotheses were formed from those and from new diagnostics on the development period only.
So a pass here is strong historical evidence, not blind confirmation. The clean confirmation is
prospective, on snapshots captured from now on, and anything taken forward needs one registered.

## Measures and intervals

- **Primary, unless an experiment says otherwise:** mean three-outcome log loss on the final
  period, candidate minus replayed production, on identical matches.
- Brier score, ranked probability score, top-pick accuracy, calibration error (ten bands per
  outcome) and the sharpness power, for both sides.
- By season, by competition with 300 or more final matches, leagues against cups.
- The five goal markets (over 1.5, 2.5, 3.5, 4.5, both teams to score) as a guard.
- **Uncertainty:** a paired bootstrap that resamples whole ISO weeks, 2,000 draws, seed
  20261012.
- **Multiple comparisons.** Thirteen candidates are registered across the three experiments
  (five, four and four). Each primary interval is reported at 1 − 0.05 / 13 = 99.6% coverage
  (Bonferroni), so that the chance of any of the thirteen excluding zero by luck is at most 5%.
  The plain 95% interval is reported beside it. A candidate for which development chose
  nothing is not scored on the final period and still counts in the thirteen.
- Simple baselines are reported alongside: the base rates, and production itself. Bookmaker
  prices exist for four weeks only and are kept to the separate market track.

## The bar

Fixed here for all three experiments. It is the project's standing gate
(`experiments/STAGE_E_DECISION.md`) with two guards added.

A candidate **meets the bar** when, on the final period:

1. the primary measure is better by at least 0.002;
2. its 99.6% interval excludes zero;
3. Brier agrees (where the primary is the result log loss);
4. it is better in 2024/25 and in 2025/26;
5. no guard measure is worse by more than 0.0005;
6. at least 60% of the competitions with 300 or more final matches are no worse.

A candidate whose 99.6% interval excludes zero but which misses another condition is recorded as
**a real gain below the bar**. Anything else is **no gain shown**. Every result is kept in the
experiment's report, whichever of the three it is.

## What is kept apart

- **P6** (`experiments/prospective/PROTOCOLS.md`) is not run, read or changed. The only odds
  used in this round are for kickoffs before 2026-10-12, the window the audit had already read,
  and only in the market track, which registers nothing and decides nothing.
- **Paper-betting profit** is not a measure anywhere in this round and no setting is chosen on it.
- **Market-informed models** are a separate track from the independent models above.
