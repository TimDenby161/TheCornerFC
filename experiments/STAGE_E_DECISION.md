# Stage E: model-improvement gate decision

**Date:** 2026-09-27
**Decision: NO PRODUCTION MODEL CHANGE**

## Gate rule

> A production model change is made only when the relevant experiment demonstrates a convincing out-of-sample improvement that meets its pre-specified deployment criteria.

A numerically better metric is not enough. The improvement must clear the experiment's practical threshold on held-out data, with supporting uncertainty intervals, secondary metrics and stability over time. Subgroup and post-hoc findings can generate hypotheses. They cannot authorise a change.

## Outcome and why it is a success

None of the tested changes produced a large and robust enough out-of-sample improvement to justify extra production complexity. So the gate kept production as it is. That is the gate working as intended, not a failed modelling stage:

- Three existing design choices were checked against alternatives on held-out data and held up: the 0.6/0.4 blend, club scaling in player ratings, and goalkeeper line weight 0.
- Two candidate additions were shown to be small or mostly already captured, so they were not deployed on the strength of a numerical edge: squad strength, and better XI prediction.

## Experiments reviewed

Experiments 11–14 are taken to be, in order:

| # | Directory | Question |
|---|---|---|
| 11 | `experiments/strength_weight/` | Weighting of Current vs Baseline club strength near kickoff |
| 12 | `experiments/player_club_strength/` | Whether player ratings depend too strongly on club strength |
| 13 | `experiments/squad_forward/` | Whether squad strength adds forward information beyond club ratings |
| 14 | `experiments/lineup_value/` | The value of predicted and actual lineup information |

All four are historical chronological reconstructions. They use a validation period (July 2023 – June 2024) to choose settings and report held-out results from July 2024 onward. Intervals are paired cluster-bootstrap 95% intervals: weeks for match outcomes, players for player outcomes, clubs for club outcomes. They are pointwise and not adjusted for multiple comparisons.

## Summary

| # | Candidate change | Deployment threshold | Principal held-out result | Met? | Decision |
|---|---|---|---|---|---|
| 11 | Current weight other than 0.6 | ≥0.002 log-loss reduction, supported by Brier, calibration, intervals and both time periods | Validation and test both choose 0.6. Best alternative 0.7: Δ log loss −0.00010 to +0.00029 | No | Keep 0.6 / 0.4 |
| 12 | Remove, weaken or residualise club scaling in player ratings | ≥1% player-target MSE or ≥0.002 match log loss, supported by uncertainty and time periods | Unscaled and residual versions tie with scaled (differences ≤0.003% MSE). Scaled is best for match log loss | No | Keep club scaling and defender/full-back treatment |
| 13 | Add squad strength or a squad residual to club forecasts or ratings | ≥1% MSE beyond embedded club-history controls, with support on direct GD, points **and** opponent-adjusted GD, and time/cohort consistency | Neutral squad: GD +0.8–1.8%, points +0.7–1.9%, adjusted GD only +0.4–0.8% (20-match CI crosses 0, negative in 2024-25) | No | Do not feed squad strength into production |
| 14 | Change lineup weights, GK weight or invest in XI prediction | ≥0.002 log loss per fixture (provisional) | Lineup-specific gain beyond a club proxy is 0.0013. Perfect XI adds 0.0005 over the predicted XI. Validation picks GK weight 0 | No | Keep lineup implementation and GK weight 0 |

## 11. Current/Baseline strength weight

- **Protocol:** there is no `DESIGN.md`. The protocol lives in `run.py` and the `practical_threshold` field of `results.json`: "held-out log-loss reduction ≥0.002, corroborating Brier/calibration, uncertainty and period consistency". The grid (0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0) is fixed in code, and validation log loss selects the weight.
- **Sample:** 19,239 validation fixtures and 43,658 test fixtures, identical across weights.
- **Result:** 0.6 has the lowest validation and test log loss (0.99399) and the lowest test Brier (0.59303). It also has the lowest loss in 2024-25 and in 2025 onward.
  - Neighbouring weights: 0.5 is Δ +0.00004 to +0.00044, and 0.7 is Δ −0.00011 to +0.00029.
  - Extreme weights are clearly worse: 0.0 is +0.0065 and 1.0 is +0.0024.
- **Pull the other way (not decisive):** 0.7 is marginally more accurate (51.57% vs 51.54%), and binned ECE falls as the Current weight rises. Proper scores worsen above 0.6, and accuracy alone is not a selection criterion.
- **Exploratory subgroups:** the weight validation chose for established top-flight teams (0.7) is *worse* than 0.6 on test (Δ +0.00001 to +0.00112). This confirms subgroup-specific weights should not be built.
- **Threshold met:** no. There is no candidate change. The production value is itself the validated optimum.
- **Decision:** keep `MATCH_RANK_NOW_TODAY = 0.6`.
- **Limitations:**
  - Only the near-kickoff blend was tested. The year-ahead value (`MATCH_RANK_NOW_YEAR = 0.2`) and the interpolation between the two are untested and outside this decision.
  - Rebuilt historical ranks are combined with frozen components of the stored predictions.
  - The paired bookmaker sample was n = 0.

## 12. Player club scaling

- **Protocol (`DESIGN.md`):**
  - Four variants: production scaled, pre-club percentile, fixed-club (club = 1000) and a residual against a quadratic in club strength fitted on training data only.
  - Thresholds: ≥1% player-target MSE or ≥0.002 match log loss, supported by Brier, intervals and time periods.
  - The stricter historical-club controls were **added after a diagnostic fit** and are a robustness check, not independent confirmation.
- **Result:**
  - Strong correlation with club strength is confirmed (Pearson 0.60 for strikers up to 0.77 for full-backs), with material spread within clubs. Correlation was not treated as proof of error.
  - **Future performance** (245,791 test rows): every player-signal variant improves MSE by about 1.8–2.1% over context controls. With stricter controls:
    - fixed-club vs scaled: +0.000032 (CI −0.000066 to +0.000153)
    - residual vs scaled: −0.000011 (CI −0.000015 to −0.000007), about 0.003% of MSE
  - **Future minutes:** every variant improves MSE by 0.23–0.31%, below 1%. Residual vs scaled with stricter controls is −0.029 of 1082.7, about 0.003%.
  - **Match prediction** (10,995 test fixtures): the scaled XI improves log loss by 0.00175 over club controls and 0.00123 over stricter controls (CI excludes 0). Neutral and residual gains are about 0.0009–0.0010, with CIs crossing 0. No variant reaches 0.002, and none beats scaled.
- **Threshold met:** no, for any alternative representation. The residual shows how the gate rule works: its edge over scaled is statistically detectable yet practically negligible, about 300 times smaller than the 1% bar.
  - The existing scaled rating clears 1% against no player information, which supports keeping it rather than changing it.
- **Decision:** keep the existing club scaling and defender/full-back treatment. Do not introduce transfer-direction adjustments.
- **Limitations:**
  - The replay is the rolling match-player formula, not the exact website season rating (only 2 immutable captures exist).
  - Provider ratings are a selected outcome, transfers are inferred from club changes, and normalisation and model development overlap these years.
  - The transfer-direction asymmetry (scaled minutes MSE −9% for strong→weak movers, +5% for weak→strong) is exploratory.

## 13. Squad forward signal

- **Protocol (`DESIGN.md`):**
  - Baselines: Baseline only, Current only, the 0.6/0.4 blend, and Current + Baseline separately.
  - Additions: raw squad, a squad residual, embedded player club history, history + raw, and history + neutral squad.
  - Horizons of 5, 10 and 20 matches. Labels are purged at the split boundaries. Shrinkage is chosen on validation.
  - Threshold: ≥1% out-of-sample MSE reduction beyond embedded club-history controls, with directional support on direct GD, points **and** adjusted GD, plus time/cohort consistency.
  - Cohorts are defined at prediction time and are exploratory.
- **Circularity:** raw squad strength correlates 0.946 with the club blend. Raw and residual additions give identical predictions (same predictor space), so residualisation is not an independent test in itself. The decisive comparison adds a club-neutral squad component on top of Current + Baseline and the squad's embedded club history.
- **Result** (neutral squad over the strong club/history baseline; 3,239–4,126 test forecast points, about 295 clubs):

| Target | 5 matches | 10 matches | 20 matches |
|---|---:|---:|---:|
| Goal difference | 0.84% | 1.42% | 1.77% |
| Points per game | 0.73% | 1.28% | 1.87% |
| Opponent/venue-adjusted GD | 0.38% | 0.76% | 0.69% (CI crosses 0) |

  - 20-match adjusted GD is −0.27% in 2024-25 and +1.77% from 2025.
  - Promoted-club gains on direct outcomes (3.3% GD at 10 matches) almost vanish after opponent adjustment (0.1%).
- **Threshold met:** no.
  - Some direct-outcome cells exceed 1%, but the pre-specified criterion also requires adjusted-GD support and consistency.
  - Adjusted GD stays below 1% at every horizon, is uncertain at 20 matches and changes sign between periods.
  - The experiment also never tested feeding squad strength *into club ratings*. It tested a separate forecast feature. Nothing supports that production route, and it would compound the club information already inside player ratings.
- **Decision:** do not feed raw squad strength or squad residuals into production club ratings or forecasts.
- **Limitations:**
  - Squads are observed deployments, not registered squads. Transfer windows are calendar proxies. Clubs leaving coverage are excluded.
  - Many horizon × outcome × cohort cells are tested without multiplicity adjustment.

## 14. Lineup value

- **Protocol (`DESIGN.md`):**
  - Paired ablation on identical fixtures: no lineup, current predicted XI, and actual XI as a retrospective counterfactual.
  - GK weight chosen on validation log loss from −0.005 to 0.02, with outfield weights fixed.
  - Provisional practical threshold: 0.002 log loss per fixture.
  - The **club-strength proxy** (no lineup information) and the **outfield-weight sensitivity** are **post-hoc robustness checks** not in the original protocol. The sensitivity is flagged as such in `DESIGN.md`.
- **Result** (9,601 test fixtures, 112 weeks):
  - **Predicted XI vs none:** log loss −0.00241 (CI −0.00344 to −0.00135), Brier −0.00138, accuracy unchanged.
  - **Club proxy vs none:** −0.00108. So about 45% of the gain is reproducible from club strength alone.
  - **Predicted XI vs club proxy:** −0.00133 (CI −0.00190 to −0.00082). This is the lineup-specific component.
  - **Actual XI vs predicted XI:** −0.00054 (CI −0.00087 to −0.00018). That is 0.00087 in 2024-25 and 0.00024 from 2025, whose CI crosses 0.
  - **Outfield weight scale:** validation picks production scaling (×1.0) for both predicted and actual XI. The best test scale for the actual XI (×1.5) gains only 0.00019 more.
  - **GK weight:** validation picks 0 for both XIs. Weights of 0.0025–0.005 are indistinguishable from 0 on test. Weights of 0.01 or more are significantly worse.
  - **Timing, XI accuracy, availability and market:** only 12 prospective fixtures from one week, so these breakdowns cannot be evaluated. No historical timestamped odds exist.
- **Threshold met:** no, for any change.
  - The lineup-specific gain (0.0013) and the perfect-XI ceiling (0.0005) are both below 0.002.
  - GK weight 0 is the validated choice.
  - The existing system's total gain over no lineup (0.0024) clears 0.002 against that naive baseline. That supports keeping it; it does not justify expanding it.
- **Decision:** keep the lineup implementation unchanged and keep `XI_LINE_WEIGHTS = (0.0, 0.005, 0.005, 0.005)`. Do not prioritise predicted-XI optimisation.
- **Limitations:**
  - The historical baseline and predicted XIs mostly lack injury inputs. Ratings are rebuilt with current code and full-history percentile references.
  - The actual XI is not a strict upper bound for a differently structured formula.
  - The conclusion "lineup-specific value is below threshold" rests on the post-hoc club proxy.

## Discrepancies and clarifications

No evidence contradicts the expected conclusions. Points recorded for accuracy:

1. **`strength_weight` has no `DESIGN.md`.** Its threshold is written into `run.py` and `results.json` as a "predeclared review threshold".
2. **Pre-specification cannot be independently verified from the repository.** The design documents were written on the same days as the runs, and three of the four experiment folders are uncommitted. No commit timestamp predates the results. Every decision here is to leave production as it is, so this cannot have caused an unjustified change. Future experiments should commit their protocol before running.
3. **Lineup wording:** "much" of the lineup value is reproducible from club strength, about 45%. The lineup-specific share (about 55%) is still the larger part, but at 0.0013 it falls below the threshold.
4. **Squad direct outcomes:** some direct GD and points cells clear 1%. The pre-specified criterion also requires adjusted-GD support and consistency, which fail.
5. **Scope of decision 11:** it covers the near-kickoff weight only. The year-ahead weight of 0.2 is untested.

## Production integrity checks (2026-09-27)

| Check | Method | Result |
|---|---|---|
| Production formulas unchanged | `git status` / `git diff` on `thecornerfc/`, `db/`, `.github/` | No uncommitted changes |
| Experiments ran on current production code | Source SHA-256 recorded in `player_club_strength/results.json` and `lineup_value/results.json` vs current files | `predictions.py`, `player_ratings.py`, `positions.py`, `config.py` all match |
| Commits during the experiment period | `git log --since=2026-09-26` on production paths after the experiments started | Plumbing only (DB URL stripping, binary fetch, evidence serialisation, export validation, health checks, standings ingest). No model formula or constant changes |
| Model configuration | `predictions.py` | `MATCH_RANK_NOW_TODAY = 0.6`, `MATCH_RANK_NOW_YEAR = 0.2`, `XI_LINE_WEIGHTS = (0.0, 0.005, 0.005, 0.005)` |
| No database writes | Code review of all experiment extractors | Every connection uses `READ ONLY` transactions (and `default_transaction_read_only=on` where used). No INSERT/UPDATE/DELETE/DDL in experiment code. The squad experiment has no database access. Server-side audit logs were not available |
| Experiments not a production dependency | grep for `experiments` in `thecornerfc/`, `.github/`, `db/`, `requirements.txt` | No references. Experiment code imports production read-only, never the reverse. numpy/scipy are not production requirements |
| Raw squad strength not in club ratings | Inspect `ranking.py` / `rating.py` | No player, XI or squad inputs to club ratings |
| Shadow outputs cannot affect live predictions | grep for shadow/squad features in `thecornerfc/`. Experiment outputs go only to `experiments/*` and ignored `.cache/` | No shadow code paths in production. Experiment artefacts are not read by production |

**Tests:**
- `python3 -m unittest discover -s tests` (production requirements): 90 tests, OK, 16 skipped. 5 need a disposable PostgreSQL database and 11 are experiment tests needing numpy/scipy.
- Experiment tests under an environment with numpy/scipy: 14 passed.
- The lineup experiment test was given the same dependency guard as the other experiment tests. Previously it made the suite fail to import under production requirements. This was a test-only change.

## Explicitly rejected tuning

Stage E does not start new optimisation or grid searches of:
- age decay, position weights, promoted- or relegated-team adjustments, draw adjustment, attack/defence weighting, home advantage or player shrinkage
- Current/Baseline weighting, club scaling, squad residuals, goalkeeper weighting or lineup weighting

It creates no competition- or subgroup-specific coefficients from exploratory results, and adds no formula complexity without a separately designed and validated experiment.

## Hypotheses retained for prospective/shadow evaluation

**Registered 2026-09-27** in `experiments/prospective/PROTOCOLS.md`, with a blinded read-only evaluator (`evaluate.py`) and sample-size planning (`power.py`). P3, P4, P6 and P7 are accruing. P1, P2 and P5 are blocked on data capture that would require production pipeline changes, which were proposed but not made.

These are evaluation candidates only, not permission to change production. Each should have its protocol, primary metric, threshold and sample size (from a clustered power calculation) committed **before** data collection begins. Each should run as shadow output that live predictions never read.

1. **Club-neutral squad strength after large verified squad changes.** 10-match shadow forecast; must improve both raw and opponent-adjusted outcomes. Needs dated registered squads and verified transfers.
2. **Player ratings after verified upward and downward transfers.** Tests whether club scaling lags for players moving to stronger clubs. Must keep non-selections and players leaving coverage in the minutes outcome.
3. **Predictions before vs after official starting XIs.** Compare predictions refreshed after the official lineups with earlier captures on the same fixtures, using prospective snapshots.
4. **Availability and injury information.** Value of availability reports and injury uncertainty, captured with timestamps before kickoff.
5. **Goalkeeper information:** only if a goalkeeper-specific representation (for example shot-stopping evidence) is developed first. Do not re-weight the current keeper rating.
6. **Model vs timestamped pre-kickoff bookmaker odds.** Paired comparison on identical fixtures, using `odds_observations` captured and inserted before the prediction cutoff (collection began 2026-09-26).
7. **Year-ahead Current/Baseline weight (optional).** Only if horizon-dependent forecasts matter commercially. The 0.2 year-ahead value was not evaluated here.

## Artefacts

- Per-experiment protocol, report, results and code: the four directories above.
- Tests: `tests/test_strength_weight_experiment.py`, `tests/test_player_club_experiment.py`, `tests/test_squad_forward_experiment.py`, `tests/test_lineup_value_experiment.py`.
- Frozen inputs are local in `.cache/`, which Git ignores, and contain no credentials.
