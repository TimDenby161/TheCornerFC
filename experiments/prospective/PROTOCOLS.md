# Prospective / shadow evaluation protocols

**Registered 2026-09-27, before any outcome for these protocols was examined.** These protocols follow from the Stage E gate (`experiments/STAGE_E_DECISION.md`). They evaluate hypotheses. They do **not** authorise production changes.

## Rules common to every protocol

- **No production effect.** Evaluation code lives in `experiments/prospective/`. It imports production functions without modifying them, reads the database in a READ ONLY / REPEATABLE READ transaction, and makes no API calls. Nothing it produces is read by production. Committed outputs are `status.json`, which records accrual only, and `results_<P>.json`, written only once a protocol is unblinded.
- **Evidence.** Only `match_prediction_snapshots.source = 'prospective'` rows count, with both `captured_at` and `created_at` before kickoff. Reconstructions and late observations are excluded.
- **Outcomes.** Regulation-time results of `status_short = 'FT'` fixtures. Extra-time and penalty matches are excluded, not relabelled.
- **Blinding and a fixed sample.** `evaluate.py` reports accrual only. `--unblind P#` refuses until the registered target is reached, and each protocol is analysed **once**, at its target. An early look (`--interim`) is labelled a protocol deviation and cannot support any decision.
- **Sample-size re-estimation.** A one-time re-estimate is allowed at 500 accrued fixtures (`--reestimate P#`). It uses the standard deviation of the paired differences only, never their mean, and the new target is recorded here as a dated amendment. Floor: 500.
- **Uncertainty.** Paired UTC-week cluster bootstrap, 2,000 draws, seed 20260927. Pointwise 95% intervals. At least 8 weekly blocks are required.
- **Decision rule for any future change.** The paired improvement in the primary metric must be at least the threshold, the 95% interval must exclude zero on the improving side, and Brier must agree. Only then may a change be *proposed*, as a separately reviewed production change with its own gate. Nothing is deployed automatically.
- **Amendments.** Any change to a target, population or metric is recorded below with its date and reason, before unblinding.

Sample-size basis (`power.py` → `power.json`): two-sided α = 0.05, 80% power, week-cluster design effect estimated from 2024-07+ historical lineup rows. For a 0.002 log-loss effect:
- XI-substitution differences (SD 0.018) need about **600** fixtures.
- Single-component ablations (SD 0.058) need about **6,500**.
- The observed design effect was 1.0.

## Summary

| ID | Hypothesis | Status | Primary comparison | Threshold | Target | First accrual (2026-09-27) |
|---|---|---|---|---|---|---:|
| P1 | Club-neutral squad strength after large verified squad changes | **Capturing** from 2026-09-28 (Amendment 1); evaluator not yet built | Shadow 10-match forecast with vs without neutral squad | ≥1% MSE, raw and adjusted GD | Set when capture exists | — |
| P2 | Player ratings after verified up/down transfers | **Capturing** from 2026-09-28 (Amendment 1); evaluator not yet built | Scaled vs neutral/residual for future minutes | ≥1% MSE | Set when capture exists | — |
| P3 | Re-predicting with the official XI | **Ready**; operational pre-kickoff capture from 2026-09-27 (Amendment 1) | Official-XI minus predicted-XI log loss | 0.002 | 600 | 12 |
| P4 | Availability/injury adjustment | **Ready** | Production minus availability-off log loss | 0.002 | 6,500 (re-estimate at 500) | 13 |
| P5 | Goalkeeper information | **Blocked**: needs a keeper-specific rating | — | — | — | — |
| P6 | Model vs timestamped pre-kickoff market | **Ready** | Model minus market log loss | Estimation (see P6) | 2,000 (re-estimate at 500) | 79 |
| P7 | Year-ahead Current weight | **Ready** | Selected weight minus 0.2 on the confirmation half | 0.002 | 6,500 confirmation fixtures | 0 |
| P8 | Fantasy v1.1 expected points (Amendment 2) | **Capturing** once the snapshot migration is applied | v1.1 minus stored recent-average / PPG benchmarks, points MAE and MSE | 95% CI excluding 0 | 10 Premier League rounds and 3,000 player rows | 0 |

Run `python3 experiments/prospective/evaluate.py` at any time to refresh accrual; it is blinded.

---

## P3: Re-predicting with the official starting XI

- **Question.** How much would re-scoring a fixture with the official XI in place of the predicted XI improve the forecast? Stage E found a retrospective ceiling of about 0.0005 log loss.
- **Population.** Fixtures whose latest prospective snapshot before kickoff:
  - is reproduced by the current formula to within 1e-8, with matching `XI_LINE_WEIGHTS`
  - has complete predicted lines
- Both teams also need a prospective lineup snapshot created no later than that snapshot, and an official XI of 11 starters, all rated among that snapshot's scored candidates.
- **Shadow model.** The snapshot's own inputs, with official-XI line ratings in place of predicted lines. Ratings come from the pre-kickoff lineup snapshot. Line assignment uses `player_ratings.line_of`.
- **Timing deviation, registered up front.** Production currently records official XIs only with results, after kickoff: 0 of 42 team-lineups at registration were recorded before kickoff. Starters don't change after kickoff and the ratings are pre-kickoff, so the counterfactual is leakage-free. It estimates the value an operational post-lineup re-prediction *could* capture, not one it did capture.
  - An operational test needs a production workflow change to fetch official lineups about 60 minutes before kickoff. That is not made here.
  - Each row records `official_recorded_before_kickoff`. If pre-kickoff capture is introduced, the operational subset is analysed as a secondary endpoint.
- **Primary.** Mean paired log loss, official XI minus predicted XI. **Secondary:** Brier, classwise ECE and accuracy; hours between official-XI recording and kickoff.
- **Decision relevance.**
  - Improvement ≥0.002 with the interval excluding zero would justify *proposing* a pre-kickoff lineup refresh.
  - Anything less confirms Stage E: don't prioritise XI accuracy or lineup refresh.

## P4: Availability / injury adjustment

- **Question.** Does the production availability adjustment (`home_missing`/`away_missing`) improve forecasts?
- **Population.** Reproducible latest prospective snapshots before kickoff in `config.INJURY_MODEL_LEAGUES`.
- **Comparison.** `predict_match` on the snapshot inputs, with production missing-player adjustments vs both set to zero.
- **Primary.** Mean paired log loss over all eligible fixtures, production minus availability-off. **Secondary:** the same restricted to fixtures with a nonzero adjustment; Brier, ECE, accuracy.
- **Target.** 6,500, with a one-time blinded re-estimate at 500. The planning SD comes from a whole-lineup ablation and is probably conservative.
- **Decision relevance.**
  - Worse by ≥0.002 with the interval excluding zero → propose reviewing the availability adjustment.
  - Better by ≥0.002 → evidence for investing in availability data quality.
  - Otherwise → no change.

## P6: Model versus timestamped pre-kickoff market

- **Question.** How does the production model compare with the bookmaker market on identical fixtures, using only prices available when the prediction was made?
- **Population.** Fixtures with a latest prospective snapshot before kickoff, and at least one bookmaker with a complete H/D/A 1X2 price set captured and inserted no later than that snapshot's creation.
- **Market probability.** For each bookmaker, the latest complete set at or before the cutoff, normalised to remove the margin. Then the mean across bookmakers. Model probabilities are the stored snapshot probabilities; no re-scoring.
- **Primary.** Mean paired log loss, model minus market, estimated with its 95% interval. This is an **estimation** protocol, not a deployment gate. The planning criterion is an interval half-width of about ≤0.01, giving a 2,000 target, re-estimated once at 500.
- **Secondary:** Brier; calibration of both; the subset where the model and market disagree by more than 10 percentage points.
- **Decision relevance.** This informs trust in paper-betting edges and model credibility. It does not by itself justify a formula change.

## P7: Year-ahead Current/Baseline weight

- **Question.** The near-kickoff weight (0.6) was validated in Stage E. The year-ahead weight `MATCH_RANK_NOW_YEAR = 0.2` and the straight-line interpolation between the two were not.
- **Population.** For each fixture, the **earliest** reproducible prospective snapshot made at least 7 days before kickoff. Days ahead is `effective_at − model_reference_at`, as in production. The snapshot's stored match ranks must be reproduced from its stored Current/Baseline ranks at weight 0.2.
- **Grid.** Year-ahead weight 0.0, 0.1, 0.2, 0.3, 0.4, 0.6. The near-kickoff weight stays at 0.6, and only the far end of the interpolation changes.
- **Design.** Fixtures ordered by kickoff. The first half selects the grid value with the lowest log loss; the second half confirms that value against 0.2. Target: 6,500 confirmation fixtures, 13,000 in total.
- **Primary.** Confirmation-half mean paired log loss, selected minus 0.2. If 0.2 is selected, the result is "production confirmed".
- **Decision relevance.** An improvement of at least 0.002 with the interval excluding zero and supporting Brier would justify proposing a change as a separately reviewed production change.

## P8: Fantasy v1.1 expected points

- **Question.** Does fantasy v1.1 hold up on gameweeks it has never seen? v1 (`experiments/fantasy_v1/REPORT.md`) beat the benchmarks on a 2024–26 backtest but failed its bias criterion. v1.1 (v1 plus goalkeeper saves plus injury-list availability) was **chosen after seeing that test**, so only prospective evidence can validate it.
- **Evidence.** `fantasy_fixture_snapshots` rows with `source = 'prospective'`, with `captured_at` and `created_at` before kickoff, written by `thecornerfc.fantasy_snapshots` on each nightly and match-day run. Availability is the injury lists and manual absences as observed at capture time.
- **Views.**
  - Primary: the latest snapshot before kickoff for each team-fixture.
  - Secondary: the latest snapshot before a round-level deadline, 90 minutes before the round's first kickoff. That is the view an FPL manager would have.
- **Outcomes.** `status_short = 'FT'` Premier League fixtures. Points are reconstructed with `fantasy.actual_points`, using the position stored in the snapshot; this is the same target as the backtest. Players who played but were left out of a snapshot are counted as coverage, not scored.
- **Benchmarks.** Recent 5-match average and points per game, stored in each snapshot's `inputs` at capture time. Official FPL expected points and price are **not** part of P8: they need FPL capture, which awaits the licensing decision.
- **Criteria** (the backtest's, minus the flat-goals ablation, which cannot be rebuilt from stored outputs):
  1. MAE and MSE lower than both benchmarks, 95% round-cluster bootstrap interval excluding zero.
  2. Bias within ±5% overall and ±10% per position, against the v1-scope target.
  3. Start ECE ≤ 0.03 and team clean-sheet ECE ≤ 0.03.
- **Secondary.** Minutes MAE and RMSE against the stored recent 5-match minutes, top-10 and top-25 hit rates, and appearances by players outside the snapshot.
- **Target.** 10 rounds and at least 3,000 player rows, analysed once. At the 2026/27 schedule that is expected around December 2026. Evaluator: `python3 experiments/prospective/fantasy_p8.py` (blinded), then `--unblind` at target.
- **Decision relevance.**
  - All three pass: v1.1 may be *proposed* as the base for fantasy features, still without claims against official FPL xP.
  - Otherwise, fix the failing component first, and don't build major fantasy UI.

## P1: Club-neutral squad strength after large verified squad changes (blocked)

- **Question.** Does a club-neutral squad component improve 10-match forecasts after large *verified* squad changes? Stage E found a hypothesis-grade signal using a noisy, appearance-based turnover proxy.
- **Blocking data.** Not captured today:
  1. Dated registered squads.
  2. Verified transfer events with dates.
  3. The club-neutral player component (the player formula with club strength = 1000), captured with each rating.
  - Items 1 and 2 need new API-Football calls (squads/transfers endpoints) and new append-only tables. Item 3 needs `player_rating_history` to store the component. All three are production pipeline changes with an API budget cost, so they are **proposed, not made**, by this protocol.
- **Planned design once captured.**
  - A frozen shadow 10-match forecast for each club at every fifth match.
  - Baseline: Current + Baseline separately, plus the squad's embedded club history.
  - Addition: the neutral squad component. Pre-specified interaction: large verified squad change.
  - Primary: MSE of 10-match mean goal difference **and** opponent-adjusted goal difference, both ≥1%.
  - Club-cluster bootstrap. Target set by a power calculation using the Stage E squad variance.

## P2: Player ratings after verified transfers (partial)

- **Question.** Does club scaling make ratings lag after moves to stronger clubs (Stage E: scaled minutes MSE +5% for weak→strong movers, −9% for strong→weak)?
- **Available now.** `player_rating_history` has had a daily capture since 2026-09-26, holding rating, rank, team and team source. This supports descriptive tracking of club changes and rating trajectories, with future minutes from `fixture_players`.
- **Blocking data.** For the predictive comparison: verified transfer dates (as in P1), and the club-neutral and residual components captured with each rating.
- **Planned design once captured.**
  - Movers with at least 50 LT points of club change, by direction.
  - Target: minutes over the next 5 and 10 club matches, **including zero-minute non-selections** and players who leave coverage (recorded as missing, not dropped).
  - Compare scaled vs neutral vs residual with player-cluster intervals. ≥1% MSE improvement in both directions is needed before any change is proposed.
- **Next accrual point.** The January 2027 transfer window. No evaluator is built until the blocking capture exists.

## P5: Goalkeeper information (blocked)

- Stage E supports GK line weight 0 **for the current goalkeeper rating** only.
- Re-weighting that rating is excluded. It was tested, and 0.0025–0.005 was indistinguishable from 0 while ≥0.01 was worse.
- P5 opens only if a goalkeeper-specific representation is designed first (for example shot-stopping evidence such as goals prevented, where the data provider supports it) and validated historically under its own design.
- Then: a paired shadow test of GK weight on prospective snapshots, with the same rules as P3.

## Amendments

**Amendment 1 (2026-09-27): data capture for P1, P2 and P3.** Added before any P1–P3 outcome was examined. Capture only: ratings and predictions don't read any of it.

- **P3:** the match-day run (every 30 minutes) now records official XIs for player-data fixtures kicking off within 70 minutes that don't yet have both XIs recorded before kickoff (`matchday.capture_prekickoff_lineups`, at most 10 calls a run).
  - The secondary operational endpoint (`official_recorded_before_kickoff`) accrues from this date. The primary counterfactual definition is unchanged.
- **P1 dated squads:** each nightly `/players/squads` fetch now appends a `squad_snapshots` row whenever a club's list changes (API ids, mapped match-data ids, names, positions). This costs no extra calls.
- **P1/P2 verified transfers:** a nightly step fetches `/transfers?team=` for clubs never fetched or whose stored squad changed since their last fetch, at most 300 calls a night.
  - Transfers dated from 2025-07-01 are kept in `transfer_observations`, and every fetch is logged in `transfer_fetches`.
  - A "verified transfer" for P1/P2 means a `transfer_observations` event whose `team_in` or `team_out` is the club. The squad-snapshot change dates bound when it took effect.
- **P1/P2 club-neutral component:** `player_rating_history` now also stores `stat_percentile`, `window_club_rank`, `window_rating` (the rolling club-scaled rating) and `neutral_rating` (the same formula with club strength 1000). These are NULL for captures before 2026-09-28.
  - The residual variant is derived at analysis time, from a club-expectation fit on data before the evaluation window.
- **Remains unchanged:** P1/P2 targets and evaluators are still to be registered in a further amendment before any of their outcomes is examined. The P1 primary metric, P2 minutes endpoint and thresholds above stand.
- **Migration:** `db/migrations/20260927_squad_transfer_capture.sql`, applied 2026-09-27.

**Amendment 2 (2026-09-27): P8, fantasy v1.1.** Registered before any P8 outcome existed: 0 snapshots were stored, and the next Premier League round kicks off 2026-10-10.

- Capture: `fantasy_snapshots.capture_safely` runs after predictions in the nightly job (fixtures in the next 8 days) and in the match-day job (fixtures within 3 hours). It is evidence only: a failure is logged and never fails either run, and nothing reads the table.
- Parameters are frozen in `thecornerfc/fantasy_params.json` (fitted 2021-07 to 2024-06). Any refit is a new model version, and its snapshots accrue separately.
- **Migration:** `db/migrations/20260927_fantasy_fixture_snapshots.sql`, **not yet applied**. Until it is, the capture logs a warning and skips.
