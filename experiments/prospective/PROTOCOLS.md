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
| P8 | Fantasy v1.1 expected points (Amendments 2, 3) | **Capturing** once the snapshot migration is applied | v1.1 minus stored recent-average / PPG benchmarks, points MAE and MSE | 95% CI excluding 0 | 10 Premier League rounds and 3,000 player rows | 0 |
| P9 | Fantasy v1.3: bonus, cards, penalty saves, keeper minutes, defensive contributions (Amendment 3) | **Capturing** from 2026-09-29; evaluator written blinded 2026-09-30 (`fantasy_p9.py`) | v1.3 minus v1.1 on the same player-fixtures, points MAE and MSE | 95% CI excluding 0 | 10 Premier League rounds and 3,000 player rows | 0 |
| P10 | Fantasy v1.4: v1.3 plus each player's own FPL defensive-contribution record (Amendment 4) | **Capturing** from 2026-09-30; evaluator written blinded 2026-09-30 (`fantasy_p10.py`) | v1.4 minus v1.3 on the same player-fixtures, DC points Brier and points MAE / MSE | 95% CI excluding 0 | 10 Premier League rounds and 3,000 player rows | 0 |
| P11 | Fantasy v1.5: v1.4 plus penalty takers, misses and FPL-only assists (Amendment 5) | **Capturing** once v1.5 deploys (2026-09-30); evaluator written blinded 2026-09-30 (`fantasy_p11.py`) | v1.5 minus v1.4 on the same player-fixtures, goal + penalty + FPL assist points MAE / MSE, then all points | 95% CI excluding 0 | 10 Premier League rounds and 3,000 player rows | 0 |
| P12 | Fantasy v1.6: v1.5 plus FPL's injury status as an availability factor (Amendment 6) | **Capturing** once v1.6 deploys (2026-09-30); evaluator written blinded 2026-09-30 (`fantasy_p12.py`) | v1.6 minus v1.5 on the same player-fixtures, log loss of P(play) | 95% CI excluding 0 | 6 Premier League rounds and 300 FPL-flagged player rows | 0 |
| P13 | Shadow corrections to the match predictions: boosted trees, and a shot formula (Amendment 7) | **Accruing** from 2026-10-13; evaluator written blinded 2026-10-12 (`shadow_p13.py`) | Corrected minus stored production probabilities, log loss | 0.002 | 9,400 (re-estimate at 500) | 0 |
| P14 | The formula candidates against production, the bookmakers' prices and as shadow bets: shot formula, goal level, movers, all three, with the boosted trees beside them (Amendment 8) | **Accruing** from 2026-10-14; evaluator written blinded 2026-10-12 (`shadow_p14.py`) | `combined` minus stored production probabilities, log loss | 0.002 | 6,200 (re-estimate at 500) | 0 |
| P15 | Every runnable change in the model change record (17), scored on live matches and watched as it goes (Amendment 9) | **Running** from 2026-10-14; evaluator `live_p15.py`, run by the Live tracking workflow | Each candidate minus stored production probabilities, log loss, with a confidence sequence | 0.002, and its interval below zero | None: judged continuously, from 500 fixtures and 8 weeks | 0 |

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
- **Evidence.** `fantasy_fixture_snapshots` rows with `source = 'prospective'`, with `captured_at` and `created_at` before kickoff, written by `thecornerfc.fantasy_games.fantasy_snapshots` on each nightly and match-day run. Availability is the injury lists and manual absences as observed at capture time.
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

## P9: Fantasy v1.3 expected points

- **Question.** Is v1.3 better than v1.1 on gameweeks neither has seen? v1.3 is v1.1 plus:
  - reconstructed bonus, cards and penalty saves
  - keeper-specific minutes and team-adjusted saves (`experiments/fantasy_v1_2/`)
  - defensive contributions fitted on FPL's 2026/27 GW1–5 results (`experiments/fantasy_dc/`)

  Its v1.2 core failed its backtest on MAE (better RMSE and bias), and everything after the designs was seen before freezing. So only this test can support it.
- **Evidence.** `fantasy_fixture_snapshots` rows whose model version is named `fantasy-v1.3`, with P8's timing rules. Parameters are frozen in `thecornerfc/fantasy_games/fantasy_params_v1_3.json`.
- **Views.** As P8: latest before kickoff (primary) and before the round deadline (secondary).
- **Target.** Points as FPL scores them, as far as the data allows:
  - the reconstructed total (`fantasy.actual_points` 'total', with the snapshot's position)
  - plus FPL's own bonus and defensive-contribution points from captured results (owner-approved use, 2026-09-29)
  - A player-fixture in a double gameweek, or one without a final FPL result, is left out of the primary analysis.
- **Primary.** v1.3 minus v1.1, paired on player-fixtures present in both versions' chosen snapshots. Points MAE and MSE, 95% round-cluster bootstrap. v1.3 is supported only if both intervals exclude 0 in its favour.
- **Secondary.**
  - Bias overall and by position (±5% / ±10%).
  - DC points and bonus, predicted against FPL's own, by position.
  - Goalkeeper start ECE.
- **Target size.** 10 rounds and 3,000 player rows from the first v1.3 capture.
- **Evaluator.** `python3 experiments/prospective/fantasy_p9.py` (blinded; accrual only), then `--unblind` at target. Written on 2026-09-30, before any fantasy snapshot had a finished fixture (first run: 0 rows). Details fixed with it:
  - FPL's bonus and defensive-contribution points are read from its `explain` (identifiers `bonus` and `defensive_contribution`) in the latest final result for each gameweek.
  - Rows are player-fixtures in both versions' chosen snapshots, in single-fixture gameweeks, with a final FPL result.
  - Bootstrap seed 20260929.
- **Decision relevance.** If supported, v1.3 may replace v1.1 on the public FPL tab. Otherwise the FPL tab keeps v1.1, and the failing component is fixed first.

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
- Parameters are frozen in `thecornerfc/fantasy_games/fantasy_params.json` (fitted 2021-07 to 2024-06). Any refit is a new model version, and its snapshots accrue separately.
- **Migration:** `db/migrations/20260927_fantasy_fixture_snapshots.sql`, **not yet applied**. Until it is, the capture logs a warning and skips.

**Amendment 3 (2026-09-29): P8 restricted to v1.1; P9 registered.** From 2026-09-29 the capture also stores fantasy v1.3 snapshots in `fantasy_fixture_snapshots`. P8's evaluator (`fantasy_p8.py`) and the site's accrual counter (`export._fantasy_progress`) now read only rows whose model version is named `fantasy-v1.1`, as Amendment 2 intended ("its snapshots accrue separately"). This was made before any P8 outcome existed, with no Premier League round played since capture began.

## P10: Fantasy v1.4 expected points

- **Question.** Does each player's own FPL defensive-contribution record improve v1.3 on gameweeks neither has seen? v1.4 is v1.3 with each player's per-90 DC mean updated by his FPL count and minutes this season: (count + mean × m) / (minutes / 90 + m). m and each position's r are fitted on GW2–5 (`experiments/fantasy_v1_4/`). On GW4–5, with m chosen on GW2–3, it beat v1.3's Brier score for defenders (0.133 vs 0.147) and midfielders (0.053 vs 0.057). That backtest is small, and it was designed after seeing Tarkowski's case.
- **Evidence.** `fantasy_fixture_snapshots` rows whose model version is named `fantasy-v1.4`, with P8's timing rules. Parameters are frozen in `thecornerfc/fantasy_games/fantasy_params_v1_4.json`. Each snapshot stores the FPL record it used (`fpl_dc_minutes`, `fpl_dc_count`): only final (`data_checked`) results captured before the snapshot.
- **Target.** As P9.
- **Primary.** v1.4 minus v1.3, paired on player-fixtures present in both. First, the Brier score of P(DC) against FPL's own DC points, for FPL defenders and midfielders. Then points MAE and MSE. 95% round-cluster bootstrap. v1.4 is supported only if the Brier interval excludes 0 in its favour and points MAE is not worse (the upper end of its interval ≤ 0.02).
- **Secondary.** As P9, plus DC calibration by the size of a player's record.
- **Target size and evaluator.** As P9: 10 rounds and 3,000 player rows from the first v1.4 capture. Evaluator: `python3 experiments/prospective/fantasy_p10.py` (blinded; accrual only), then `--unblind` at target. Written on 2026-09-30, before any fantasy snapshot had a finished fixture. It reuses `fantasy_p9.py`'s target and pairing. Details fixed with it:
  - P(DC) is a version's stored DC points / 2, and the hit is FPL's DC points > 0.
  - "FPL defenders and midfielders" means FPL's position in the latest capture.
  - The record-size bins are 0, 1–269, 270–539 and 540+ FPL minutes.
  - Bootstrap seed 20260930.

**Amendment 4 (2026-09-30): P10 registered; the public FPL tab shows v1.4.** From 2026-09-30 the capture also stores fantasy v1.4 snapshots. P8 still reads only `fantasy-v1.1` rows and P9 only `fantasy-v1.3` rows, so neither changes. The owner chose to show v1.4 on the public FPL tab before any of P8–P10 is evaluated. This is a display decision, not evidence. P9's and P10's "decision relevance" clauses no longer decide what the tab shows; their results will be reported on the tab when they exist.

## P11: Fantasy v1.5 expected points

- **Question.** Do penalty takers, penalty misses and FPL-only assists improve v1.4 on gameweeks neither has seen? v1.5 takes expected penalty goals (league rate × conversion) out of the team total. It gives them by taker weight: decayed penalty attempts for the club, plus α × non-penalty goal rate, blended with FPL's `penalties_order`. It shares the rest by non-penalty evidence, and adds the assists FPL gives that API-Football doesn't. See `experiments/fantasy_v1_5/`.
- **Retrospective result.** On 2025-26 and 2026-27 to date, taker log loss was 1.19 against 1.33 for the last taker and 1.81 for v1.4. The scorer log-likelihood change was +0.0004 per goal (95% CI −0.0030 to +0.0037), which does not pass. FPL's order weights (0.75, 0.15) were set without data.
- **Evidence.** `fantasy_fixture_snapshots` rows whose model version is named `fantasy-v1.5`, with P8's timing rules. Parameters are frozen in `thecornerfc/fantasy_games/fantasy_params_v1_5.json`. Each snapshot's inputs store every player's FPL penalty order and penalty record (`penalty_takers`).
- **Target.** FPL's own points per player-fixture: goals, penalty misses and assists from `fpl_player_results`. FPL results don't separate penalty goals, so the primary is the sum of goal + penalty + FPL assist + assist points.
- **Primary.** v1.5 minus v1.4, paired on player-fixtures present in both: MAE and MSE of goal + assist points (v1.5's goal, penalty, assist and FPL assist parts, against v1.4's goal and assist parts). 95% round-cluster bootstrap. Reported separately for players with a predicted penalty share above 0.5. v1.5 is supported only if the MAE interval excludes 0 in its favour and all-points MAE is not worse (upper end ≤ 0.02).
- **Secondary.** As P9. Also calibration of predicted penalty share against FPL's `penalties_missed` and the API-Football penalty takers.
- **Target size and evaluator.** As P9: 10 rounds and 3,000 player rows from the first v1.5 capture. Evaluator: `python3 experiments/prospective/fantasy_p11.py` (blinded; accrual only), then `--unblind` at target. It was written on 2026-09-30, before any v1.5 snapshot had a finished fixture (first run: 0 rows). Details fixed with it:
  - Rows: player-fixtures in both versions' latest snapshots before kickoff; the deadline view is secondary, as in P8.
  - Scored against FPL's final results (goals, assists, penalties missed, total points) at FPL's position. Predictions are rescored at that position from their stored parts.
  - Left out: double gameweeks, and players with no final FPL result.
  - Taker log loss uses each snapshot's expected penalty goals. Takers outside the snapshot count at a floor of 1e-6.
  - Bootstrap seed 20260930.

**Amendment 5 (2026-09-30): P11 registered; the public FPL tab shows v1.5.** From the deploy of v1.5 the capture also stores fantasy v1.5 snapshots. P8, P9 and P10 read only their own versions' rows, so none of them changes. The owner chose to show v1.5 on the public FPL tab before any of P8–P11 is evaluated. This is a display decision, not evidence.

## P12: Fantasy v1.6 availability from FPL's injury status

- **Question.** Does FPL's injury status, applied as an availability factor (`experiments/fantasy_v1_6/DESIGN.md`), predict who plays better than v1.5? v1.5 uses only API-Football's match-day lists and manual absences. And what factor does each FPL status actually warrant?
- **Evidence.** `fantasy_fixture_snapshots` rows whose model version is named `fantasy-v1.6`, paired with `fantasy-v1.5` rows for the same team-fixture, with P8's timing rules. Each v1.6 snapshot's inputs store every FPL-flagged player's status, chance, news and the factor used (`fpl_availability`).
- **Target.** Whether he played (minutes > 0) and whether he started, from `fixture_players`. A player in the snapshot with no match line counts as not playing.
- **Primary.** v1.6 minus v1.5, paired: mean log loss of P(play), over all player-fixtures and over FPL-flagged ones. 95% round-cluster bootstrap. v1.6 is supported if the flagged interval excludes 0 in its favour and the all-players interval's upper end is ≤ 0.001.
- **Secondary.** The same for P(start). Expected-minutes MAE. Calibration of P(play) by bucket: dated absence before its date; no date; doubtful at 25 / 50 / 75%; API missing; API questionable; both sources.
- **The refit, registered now.** At target, each FPL bucket's fitted factor is its observed play rate over v1.5's mean P(play) for the same rows, capped at 1. Buckets with fewer than 30 rows keep the v1.6 value. The fitted factors become a proposed v1.7, judged prospectively in turn.
- **Target size and evaluator.** 6 Premier League rounds and at least 300 FPL-flagged player rows from the first v1.6 capture, analysed once. Evaluator: `python3 experiments/prospective/fantasy_p12.py` (blinded), then `--unblind` at target.

**Amendment 6 (2026-09-30): P12 registered; the public FPL tab shows v1.6.** From the deploy of v1.6 the capture also stores fantasy v1.6 snapshots. P8–P11 read only their own versions' rows, so none of them changes. The owner approved using FPL's injury status as a model input and chose to show v1.6 on the public FPL tab. This is a display decision, not evidence.

## P13: Shadow corrections to the match predictions

- **Question.** Does a correction learned from pre-match figures improve production's match predictions on matches no one has seen? On a historical reconstruction (`experiments/architectures/REPORT.md`, 44,383 matches from July 2024) a boosted-tree correction improved log loss by 0.0028 and met the standing bar. That period had been looked at before and was scored fourteen times in one research round (`experiments/research_frame/REGISTER.md`), so only prospective evidence can confirm it.
- **Candidates.** Two, each applied to the projected goals of a snapshot and followed by the probability step as it stood at registration (`experiments/research_frame/frame.py`):
  - **`gb` (primary).** The boosted-tree correction exactly as registered in `experiments/architectures`: the settings and features in its `chosen.json`, two regressions (margin error, total error) retrained every 1 July and 1 January on every scored match before that date, with the weekly-refitted Poisson model's margin and total among the features. The model in force at the start is the one trained on matches before 2026-07-01.
  - **`formula` (secondary).** A ridge regression (penalty 50) of the margin error on five differences between the two sides' last-ten figures (xG difference, shot difference, on-target difference, in-box shot difference, goals minus xG; a missing figure counts as zero) and a constant, refitted on the same dates and added to the expected margin. On the 2022 to 2024 selection window it scored −0.00245; it has never been scored after June 2024.
  - The files that define both are pinned by SHA-256 in `shadow_p13.py`, which stops if any has changed. A changed file is a different candidate and needs its own protocol.
- **Population.** Finished fixtures (`FT`, regulation score) kicking off from 2026-10-13 00:00 UTC, with a latest prospective snapshot before kickoff whose stored probabilities the registered probability step gives back from its stored projected goals to within 1e-8. A snapshot made by a later production model whose probability step differs is left out and counted.
- **Comparison.** The corrected probabilities against that snapshot's own stored probabilities, on the same fixtures.
- **Timing deviation, registered up front.** Nothing is captured at prediction time: the corrections are worked out at analysis, from the database as it then stands. They use only matches that kicked off before the fixture, but a past match's statistics as later corrected, and the feed can deliver xG some days after a match. So this estimates what an operational correction *could* capture. Each row records whether both sides' latest earlier match had its statistics fetched before the snapshot was made (conservative: a later re-fetch counts as late), and that **operational subset** is a secondary endpoint. An operational test needs a production pipeline change, which is not made here.
- **Primary.** Mean paired log loss, `gb` minus production, with the common week-cluster bootstrap. **Secondary:** the same for `formula`; Brier; calibration error and the ends gap (`experiments/ends_and_draws`); leagues and cups; the five goal markets (over 1.5 to 4.5 and both teams to score, each side's projected goals through production's calibration); by month; the operational subset.
- **Named weak spot.** Ties in the Champions League, Europa League and Conference League were worse under `gb` on the reconstruction. They are in the population, reported separately, and a candidate whose European ties are worse (point estimate above zero) may be proposed for other competitions only.
- **Target.** 9,400 fixtures, analysed once. Planned from `gb`'s reconstruction: a paired standard deviation of about 0.097 a fixture (week-clustered) and an effect of 0.0028, two-sided 5%, 80% power. The one-time re-estimate at 500 uses the standard deviation only, with the same planning effect. At about 1,600 scored fixtures a month this is roughly six months. An effect of 0.002, the size of the formula's development figure, would need about 18,000 and is not what this protocol is sized for.
- **Decision relevance.** By the common rule: an improvement of at least 0.002 with the interval excluding zero and Brier agreeing, and the goal markets not worse on average by more than 0.0005, would justify *proposing* the correction as a production change, for the owner to decide, built and reviewed as a model release of its own. `formula` is the form that could be written into production's margin and explained on the site; `gb` is the ceiling it is judged against. Anything less: no change.
- **Not measured.** Anything against the bookmakers (no odds are read; P6 is untouched), and paper-betting returns.
- **Evaluator.** `python experiments/prospective/shadow_p13.py` asks the database one question, how many fixtures have accrued, and writes `status_P13.json`. `--reestimate` and `--unblind` read every finished fixture once from production (read-only) and need the packages in `requirements-p13.txt`; a run with other versions is recorded as a deviation. Bootstrap seed 20260927.

**Amendment 7 (2026-10-12): P13 registered.** Written the day the research round finished and before any fixture in its population had kicked off: the first accrual check, against production, counted 0. The evaluator was run once on already-seen fixtures before 13 October (the research inputs, with stored live predictions standing in for snapshots) to check that it runs; no outcome metric was printed or kept. `shadow_p13.py` SHA-256 at registration: `0d54e221ca3fd922bc1357fbef104eca4e65a01b8a334acf0218aab3ef37fff8`. Nothing in production is changed by this protocol and nothing reads its output.

## P14: The formula candidates against production, the market and as shadow bets

- **Question.** Three improvements came out of the October research round: shot figures where there is no xG, a calibration that is relearned as it goes, and clubs changing division. Does each, and do all three together, make the match predictions more accurate on matches no one has seen, do they bring the predictions closer to the bookmakers' prices, and would the paper-betting rule have done better with them? P13 asks the first question of the boosted trees and the shot formula only, and reads no prices.
- **Candidates.** Five, each applied to the projected goals of a snapshot and followed by the probability step as it stood at registration (`experiments/research_frame/frame.py`). Every setting was fixed on matches up to June 2024 (`experiments/relearned_calibration/DESIGN.md`); none of the first four has been scored on a later match.
  - **`combined` (primary).** `movers`, then `formula` fitted on what is left, then `calibration` fitted on what is left of that. On the 2022 to 2024 selection window it scored −0.00347.
  - **`formula`.** P13's secondary candidate, unchanged: a ridge regression (penalty 50) of the margin error on five differences between the two sides' last-ten figures, refitted every 1 January and 1 July.
  - **`calibration`.** The projected goal total follows recent scoring, overall and by competition (half-life 60 days, 100 matches of shrinkage: `experiments/goals_home_scores`). Development was asked whether a curve relearning the margin's error should be added and chose none, so this is the goal level alone.
  - **`movers`.** The rank replay with a club that changes division moved halfway to its new division's average on arrival and a club with little history moving faster (`pull` 0.5, `boost` 0.5, `tau` 40: `experiments/rating_dynamics`). The expected margin moves by the candidate replay's match-rank gap less production's own replay's.
  - **`gb` (reference).** P13's boosted-tree correction, exactly as there. It is here so that the trees are also seen against the prices and as bets; its accuracy is P13's to judge.
  - The files that define them are pinned by SHA-256 in `shadow_p14.py`, which stops if any has changed. A changed file is a different candidate and needs its own protocol.
- **Population.** Finished fixtures with a 90-minute score kicking off from 2026-10-14 00:00 UTC, with a latest prospective snapshot before kickoff whose stored probabilities the registered probability step gives back from its stored projected goals to within 1e-8.
- **Deviation from the common rules, registered up front: ties decided after 90 minutes are in.** The common rule leaves out `AET` and `PEN` fixtures. Here they are scored on their 90-minute result, because a bet on one settles on it and most of them are draws: leaving them out removes cup draws from the sample (706 fixtures from July 2024 to October 2026, 83% level at 90 minutes). The fixtures that finished in 90 minutes are reported separately, for comparison with P13. The candidates' own fitting still uses 90-minute finishes only, as they were developed.
- **Three comparisons, on the same fixtures.**
  - **Accuracy.** Each candidate's probabilities against that snapshot's own stored ones.
  - **Market.** Each candidate and production against the bookmakers' margin-free chances, on the fixtures that have them: for each bookmaker the latest price of each selection captured and inserted no later than the snapshot was made, each complete market normalised, then the mean across bookmakers (P6's definition). The result market, over 2.5 and both teams to score.
  - **Shadow bets.** The paper rule as `thecornerfc/models/betting.py` stood at registration, copied into the evaluator: a 1-unit bet on any selection whose chance times Bet365's price at that moment is at least 1.10, prices above 10 left out, in the result market, over/under 1.5 to 4.5 and both teams to score, one bet of each kind a fixture (the best by the rule's own score). Settled on the 90-minute score. Worked out for production's stored chances and for each candidate's, from the same prices. Closing-line value is the price taken times the margin-free chance from every bookmaker's last price before kickoff, less one. These are not the site's paper bets (one moment a fixture, no early and late strategies, no tags), no bet is recorded anywhere, and production's own shadow bets are the comparison.
- **Timing deviation, registered up front.** As P13: the corrections are worked out at analysis, from the database as it then stands, using only matches that kicked off before the fixture. The **operational subset** (both sides' latest earlier match had its statistics fetched before the snapshot was made) is a secondary endpoint. The prices are not affected: they are append-only observations with their own timestamps.
- **Primary.** Mean paired log loss, `combined` minus production, with the common week-cluster bootstrap. **Secondary:** the same for the other four; Brier; calibration error and the ends gap; leagues, cups and European ties; the 90-minute-finish subset; the five goal markets; by month; the operational subset; every model minus the market (log loss and Brier) and the share of production's deficit a candidate closes; each model's shadow bets (number, return, closing-line value, winners against the number the market's chances and the model's own imply, by kind of bet, at odds under 4, and without result bets on outsiders) and each candidate's profit a priced fixture less production's.
- **Target.** 6,200 fixtures, analysed once. Planned from `combined` on the selection window: a paired standard deviation of 0.078 a fixture (week-clustered) and an effect of 0.0028, four fifths of its figure there, two-sided 5%, 80% power. The one-time re-estimate at 500 uses the standard deviation only. At about 1,600 scored fixtures a month this is roughly four months. An effect of 0.002 would need about 12,000.
- **What the sample can and cannot show.** Nearly nine fixtures in ten have had prices so far (646 of 740 from 26 September to 11 October), and the paper rule has bet on about half of those, so the target should bring roughly 5,400 priced fixtures and about 4,000 shadow bets a model. That estimates a model's distance from the market to about ±0.004 of log loss, and a return to about ±5 points. It can show that a candidate is more accurate and closer to the market. It can show an edge only if the edge is large; a small one would need several times the sample, and the result will say so.
- **P6 comes first.** Reading P14 shows production against the market on its fixtures, which is P6's question. `--unblind` refuses until `results_P6.json` exists.
- **Decision relevance.**
  - *Accuracy:* by the common rule. An improvement of at least 0.002 with the interval excluding zero and Brier agreeing, and the goal markets not worse on average by more than 0.0005, would justify *proposing* the candidate as a production change, for the owner to decide, built and reviewed as a model release of its own.
  - *Edge:* estimation, not a gate. A candidate is recorded as showing an edge only if all three hold: it is not behind the market's prices on the result (model minus market at or below zero), its shadow bets' return has an interval above zero, and their closing-line value has an interval above zero. Anything less is recorded as no edge shown. No result here authorises a real bet or a change to the paper rule; an edge that is shown would earn a betting protocol of its own, on new fixtures, with the rule fixed beforehand.
- **Evaluator.** `python experiments/prospective/shadow_p14.py` asks the database how many fixtures have accrued and how many have a price, and writes `status_P14.json`. `--reestimate` and `--unblind` read every finished fixture once from production (read-only) and need the packages in `requirements-p13.txt`; a run with other versions is recorded as a deviation. The prices are reduced in the database to one row a fixture and selection. Bootstrap seed 20260927.

**Amendment 8 (2026-10-12): P14 registered.** Written the same day as the audit that asked for it, and before any fixture in its population had kicked off: the first accrual check, against production, counted 0. The owner chose what it measures (accuracy, the market and shadow bets) before the evaluator was written. The evaluator was run on already-seen fixtures before 12 October (the research inputs, with stored live predictions standing in for snapshots and stored result prices standing in for observations) to check that it runs; shapes and counts were printed and no outcome metric was printed or kept. `shadow_p14.py` SHA-256 at registration: `5f5fd9c1c3b384b4c0575ae28b8a952e44cad9040d8eb60c325916a2863961fa`. Nothing in production is changed by this protocol and nothing reads its output.

## P15: Every runnable change, scored on live matches and watched as it goes

- **Question.** Which of the changes in the model change record (`experiments/changes/`, `guide/admin-area.md`) improve the match predictions on matches played after they were fixed, shown as the matches come in? The owner asked on 2026-10-13 for every change on that list to be tracked on live matches and for the results to be visible, and chose a method made for watching over a blind read at a fixed sample.
- **Candidates.** The 17 changes that exist as something to run, each with the setting its own experiment fixed and nothing chosen afterwards (`CANDIDATES` in `live_p15.py`, with the file each setting comes from): the 0.7 rank blend; sharpening, the refitted draw boost, and the two together; the league gaps and the no-league markdown; movers, new clubs, and the two together; the weekly Poisson model, the boosted trees, and their pool; the goal level and home advantage by competition; shots as a stand-in for xG; the shot formula; and the three formulas together. Sixteen of them are rejected or below the bar on history; they are here because they were asked for, and a rejected change that later shows a gain earns a fresh experiment, not a release.
- **Not run.** The other ten, each for a stated reason (`NOT_RUN`): five where testing chose no setting, three that are not match predictions, and two already in production.
- **Population.** As P14: finished fixtures with a 90-minute score kicking off from 2026-10-14 00:00 UTC (ties decided after 90 minutes count as the draws they were), with a latest prospective snapshot before kickoff that the registered probability step reproduces.
- **Comparison.** Each candidate's probabilities against that snapshot's own stored ones, mean paired log loss. No odds are read and no bets are simulated: those are P14's.
- **The method.** A two-sided confidence sequence for the mean difference (Robbins' normal mixture in its asymptotic form), which holds at every look at once, so the record can be read as often as anyone likes. The mixture is set to be tightest at 6,200 fixtures. The standard deviation is widened by the week-cluster design effect, never narrowed. The 5% is split across the 17 candidates (0.29% each), so that the chance of any of them being wrongly called at any time is about 5%. Nothing is called before 500 fixtures and 8 weeks. A call stands once made.
- **What it costs.** Being able to look at any time is paid for in matches, and most of the price is the looking itself, not the number of candidates. Worked out from the method before any fixture was scored: a candidate worth 0.0028 with the trees' standard deviation (0.097) is expected to be called at about 19,000 fixtures, roughly a year, where one candidate watched alone would need about 11,000 and P13's single read needs 9,400. The three formulas together (standard deviation 0.078) are expected at about 12,000 if they are worth 0.0028 and about 7,700 at their development figure of 0.0035. A gain the size of movers alone (0.0008) would need about 41,000 and will not be called in practice. So the fixed reads of P13 and P14 remain the quicker route to a verdict for the candidates they cover; P15 is what lets every candidate be seen in the meantime. The owner was first told "a third to a half more matches", which was wrong, and was given these figures on 2026-10-13.
- **Reading it.** "Proven better": the whole interval of candidate minus production is below zero. "Ready": proven better and the gain is at least 0.002. "Proven worse": the whole interval is above zero. Anything else is undecided, whatever its sign.
- **Timing deviation, registered up front.** As P13 and P14: the candidates are worked out afterwards from the database as it then stands, using only matches that kicked off before each fixture, so this shows what a production version could capture, not what one did.
- **Decision relevance.** A candidate that is ready may be *proposed* as a production change, for the owner to decide, built and reviewed as a model release of its own (`/model-experiment`). Nothing is accepted or deployed by this protocol, and it says nothing about betting.
- **Evaluator.** `python experiments/prospective/live_p15.py` prints the record; `--store` writes the administrator's document `live_tracking`, which only the Admin area reads. The Live tracking workflow runs it on Mondays and Thursdays and by hand. The files that define the candidates are pinned by SHA-256; a changed file is a different candidate.

**Amendment 9 (2026-10-13): P15 registered; P13 and P14 are no longer blind.** Written before any fixture in P15's population had kicked off. The owner chose it, knowing the cost: P15 shows, as they come in, the same comparisons with production that P13 (the boosted trees and the shot formula) and P14 (the formulas, the goal level, movers and the trees) were registered to read once, and P15's population is P14's. So from 2026-10-14 the accuracy results of P13 and P14 are visible before their targets. Their fixed-sample reads still happen once, at 9,400 and 6,200 fixtures, as registered, and are to be reported as confirmations made with the running result already known. What stays blind: everything in P14 against the bookmakers' prices and its shadow bets, which P15 does not compute, and P6. The evaluator was run on already-seen fixtures before 12 October (the research inputs, stored live predictions standing in for snapshots) to check that every candidate gives valid probabilities; shapes and counts were printed, and no gain, interval or verdict was printed or kept. `live_p15.py` SHA-256 at registration: `138542daab78cebda5d2f86356959a323207501616380854f6d4d809e9e7752f`.

## P16: The club-rank release against the model it replaced, on live matches

- **Question.** Does the release of movers, new clubs and shots for xG in the club rank (MC-0028, the owner's decision of 2026-10-14) make the match predictions better on matches played after it, compared with the version it replaced? Both parts were proven better than production on the final period (MC-0016, MC-0024); they are released together, and this is their first test on matches no one has seen.
- **Population.** Finished fixtures with a 90-minute score kicking off from 2026-10-15 00:00 UTC (ties decided after 90 minutes count as the draws they were), whose latest prospective snapshot before kickoff was made by the released version: a match-model version whose `source_digests` differ from the version before it in `ranking.py` and in no other file (`BEFORE` in `live_p16.py`). A fixture whose latest snapshot came from the old version is left out and counted, as is one whose stored probabilities the registered probability step does not reproduce.
- **Comparison.** The snapshot's stored probabilities against the version before the release, re-created from the same snapshot: its projected goals moved by the change in the match-rank gap between the old club rank (`frame.replay`) and the released one (`shots_proxy/run.py`'s replay at goals weight 0.5 and K 10, with pull 0.5, boost 0.5 and 40 matches), both replayed over every match before it, then the registered probability step. Mean paired log loss, released minus old. This is how P15 applied its rank candidates, the other way round.
- **The method.** P15's confidence sequence, imported from `live_p15.py` (`track`) so it cannot drift, with the whole 5% on this one comparison: tightest at 6,200 fixtures, widened by the week-cluster design effect, nothing called before 500 fixtures and 8 weeks, a call standing once made.
- **What it costs.** Worked out before any fixture in the population had kicked off, on the final period already seen: per-fixture standard deviation 0.0545, design effect 1.30. At the two together's 0.00118 a call is expected at about 27,000 fixtures, around seventeen months; at movers' 0.0008, about 64,000. A worse release is called as quickly as a better one.
- **Reading it.** "Proven better": the whole interval is below zero, and the release stands. "Proven worse": the whole interval is above zero; the owner is told and decides whether to revert. Anything else is undecided, whatever its sign.
- **Checks with every run.** How far the frame's replay of the released rank is from the match ranks the snapshots stored (mean and largest, in rank points), and the counts left out for each reason. Before the release the frame reproduced the stored ranks of the version it replaces to a mean of 0.026 points (median 0.001) over 752 live fixtures from 1 September 2026, so a release built as the experiment was should read about the same.
- **Decision relevance.** The release is already the owner's decision; P16 confirms it or flags it for reverting. It says nothing about betting.
- **Evaluator.** `python experiments/prospective/live_p16.py` prints the record; `--store` writes the administrator's document `live_tracking` in P15's shape, which the Model Change Tracker reads. The Live tracking workflow runs it from the release on. The files that define both ranks and the judgement are pinned by SHA-256.

**Amendment 10 (2026-10-14): P16 registered.** Written before the model code it judges and before any fixture in its population had kicked off. The evaluator was run once on already-seen fixtures (the research inputs, 752 stored live predictions from 1 September 2026 standing in for the release's snapshots) to check that it runs: counts, shapes and the rank checks were printed, and no log loss, gain, interval or verdict was printed or kept. `live_p16.py` SHA-256 at registration: `210c490e0da74f609117e6b0d543870267d126e5f93c1164a853f7e8da9723a2`. P13, P14 and P15 close by an amendment of their own on the day the release reaches `main`.

**Amendment 11 (2026-10-14): P13, P14 and P15 close; the club-rank release reaches production.** On the owner's decision of 2026-10-14 the match model's club rank takes movers, new clubs and shots for xG (MC-0028), from the first scheduled run after this reaches `main`. All three protocols compare their candidates with production's stored predictions, and those now come from the released version. P15 applies each rank candidate as a difference from the old rank, so it would count the movers and the shots a second time, and P13's trees and P14's formulas were fitted to the old version's errors. So all three close from today, before any of their fixtures was read: none had reached its minimum sample (P15 needs 500 fixtures and 8 weeks; its population began on 14 October), and no gain, interval or verdict of any of them exists. A candidate still worth testing is registered afresh against the released version. P6 measures production as stored, so from the release its fixtures come from the released version: it continues, and its report gives the figure for each model version as well as for the whole. The fantasy protocols are unaffected. The Live tracking workflow runs P16 from today.

## P17: Every runnable idea on top of the live model, scored on live matches and watched as it goes

- **Question.** P15's question, asked again of the model now live: which ideas in the change register improve the match predictions of the released version (MC-0028) on matches played after it? The owner asked on 2026-10-14 for every idea to be back on live matches, worked out on paper from the stored predictions, with no production code and nothing extra stored.
- **Candidates.** The 13 that can be run on top of the released model, each with the setting P15 registered for it (`CANDIDATES` in `live_p17.py`, taken from `live_p15.py`): the 0.7 rank blend, on the released rank; sharpening, the refitted draw boost and the two together; the league gaps and the no-league markdown; the weekly Poisson model, the boosted trees and their pool; the goal level and home advantage by competition; the shot formula; and the three formulas together, whose movers step adds nothing because the movers are in the live model.
- **Learning on the live model.** History before the release is the stored projections moved onto the released club rank (`frame.reprojected` with the released replay), and the live fixtures are the released snapshots. So the ideas that learn from the model's errors as they go (the goal level, home advantage by competition, the shot formula, the three formulas, the trees and the pool) learn the released model's, with their registered settings; the trees and formulas are refitted in the same half-season blocks as in P13. This makes them a test of each idea's recipe on the live model, not of a fit made on the old one.
- **Not run.** The other 15, each with its reason (`NOT_RUN`): movers, new clubs, the two together and shots for xG are in production; the release is P16's; and P15's ten with nothing to run.
- **Population.** P16's: finished fixtures with a 90-minute score kicking off from 2026-10-15 00:00 UTC whose latest prospective snapshot before kickoff was made by the released version, reproduced by the registered probability step.
- **Comparison and method.** As P15: each candidate's probabilities against the snapshot's stored ones, mean paired log loss, judged by P15's confidence sequence (`track`, imported), tightest at 6,200 fixtures, widened by the week design effect, the 5% split across the 13 candidates (0.38% each), nothing called before 500 fixtures and 8 weeks, a call standing once made.
- **What it costs.** As P15, a little less split: a candidate worth 0.0028 with the trees' standard deviation is expected to be called at about 18,000 fixtures, roughly a year; one worth less than 0.001 will not be called in practice.
- **Reading it.** "Proven better": the whole interval is below zero, which the tracker shows green (the owner's rule of 2026-10-14). "Proven worse": the whole interval is above zero. Anything else is undecided.
- **When the live model changes again.** A release rebases this record by a dated amendment in the same commit: the new live version, the replay of its rank, and which ideas it takes in. The record so far is kept in that amendment.
- **Decision relevance.** A proven candidate may be put forward as a model release of its own (`/model-experiment`), or first as the stored challenger beside the live model. Nothing is accepted or deployed by this protocol, and it says nothing about betting.
- **Evaluator.** `python experiments/prospective/live_p17.py` prints P16's and P17's record from one read; `--store` writes the administrator's document `live_tracking` with both, in P15's shape. The Live tracking workflow runs it on Mondays and Thursdays and by hand. The files that define the candidates and both ranks are pinned by SHA-256, P15's and P16's pins included.

**Amendment 12 (2026-10-14): P17 registered.** Written before any fixture in its population had kicked off. The evaluator was run once on already-seen fixtures (the research inputs, 752 stored live predictions from 1 September 2026 standing in for the release's snapshots) to check that every candidate gives valid probabilities and that every change in the register is tracked or says why not; counts and shapes were printed, and no gain, interval or verdict was printed or kept. `live_p17.py` SHA-256 at registration: `8110136e31a227a307a9716fb9a26e76f2bf5a136ac3550ed7149ba97858530e`.

## P18: The stored challenger against the live model

- **Question.** Does A18's recipe on top of the live model (`a18`) predict live matches better than the live model alone (`base`), judged from predictions both made before each match? The owner chose on 2026-10-14 to run the two side by side in production, with a switch in the Admin area, A18 built into the production code (`experiments/challenger/DESIGN.md`, MC-0029).
- **Population.** Finished fixtures with a 90-minute score (ties after extra time count as the draws they were) kicking off from the first day after the release that adds the challenger reaches `main` (`START` in `live_p18.py`, set by the amendment made that day), whose latest prospective snapshot before kickoff names the model that made it (`inputs.match_model`), and whose other model's row in `challenger_predictions` was captured and written before kickoff. Fixtures without either are left out and counted.
- **Comparison.** Mean paired log loss, `a18` minus `base`, whichever was live.
- **The method.** P15's confidence sequence (`live_p15.track`, imported), the whole 5% on this one comparison: tightest at 6,200 fixtures, widened by the week design effect, nothing called before 500 fixtures and 8 weeks, a call standing once made.
- **What it costs.** Worked out before any fixture, from P15's figure for the trees' per-fixture standard deviation (0.097) and the refit's 0.0019 on the released rank: a call is expected at about 26,000 fixtures, 34,000 with a week design effect of 1.3; roughly a year and a half to two years. P17 scores the same recipe on paper and may call it sooner; P18 is the confirmation from predictions that existed before each match.
- **Reading it.** "Proven better": the whole interval is below zero; the owner may switch to `a18`, and nothing switches by itself. "Proven worse": the owner is told. Anything else is undecided.
- **Decision relevance.** Which model is live is the owner's, by the switch; each switch is logged (`match_model_switches`) and recorded in the change record. It says nothing about betting.
- **Evaluator.** `experiments/prospective/live_p18.py`, three small reads; run with P16 and P17 by `live_tracking.py`, which stores the one document `live_tracking`. No numpy.

**Amendment 13 (2026-10-14): P18 registered.** Written before the model code it judges and before the challenger table exists (migration `20261014_challenger_model.sql`, waiting for the owner). Its start is left unset (`START = None`, which reads nothing) until the release reaches `main`, when an amendment sets it. `live_p18.py` SHA-256 at registration: `95f94bbf507fbfca9fbc8b64bdffa5d9e187aaf028a82bf0aaada266a673b783`.
