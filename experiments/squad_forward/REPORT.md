# Does squad strength add forward information beyond club ratings?

**Recommendation: retain production unchanged. Take a separate, context-neutral squad signal into prospective shadow forecasting; do not feed raw squad strength into club ratings.**

There is evidence of modest incremental forecast information, not just a recycled club-strength term. A neutral squad component improves next-10/20-match raw goal-difference and points forecasts after controlling for both Current and Baseline strength and the club levels embedded in player ratings. However, opponent-adjusted gains are smaller, the 20-match adjusted result is uncertain, and several subgroup effects fail to replicate clearly. The experiment therefore does not establish a robust independent club-ability signal suitable for deployment.

## Design, provenance and scope

- Input: the prior frozen player experiment (32,023 completed fixtures; last observed kickoff 2026-09-27 02:30:00+00:00). No new database queries or API requests were needed for this experiment.
- Player scores use prior 20 appearances within 540 days and pre-2022 statistical normalization. This is a chronological reconstruction of the rolling match-player formula, not a prospective archive of website career/season ratings. Centre-back team_xga was unavailable in early training and is omitted consistently.
- Squad strength is the prior-five-match-minutes-weighted mean of eligible recently observed players. Require at least eleven players, including a goalkeeper, each with at least 180 historical minutes. It represents observed playing resources, not the registered squad or confirmed transfer signings. New signings enter after an observed appearance; departures can persist in the previous-five-match pool.
- Anchor every fifth observed club match. Predict average performance over the immediately upcoming 5, 10 or 20 observed completed league matches, requiring a full horizon within 365 days.
- Training anchors: January 2022–June 2023; validation: July 2023–June 2024; test: July 2024 onward. **Training labels must finish before validation starts; validation labels must finish before test starts.** The same eligible rows are used by every model within an endpoint/horizon.
- Validation MSE selects augmentation shrinkage from 0, .25, .5, .75, 1. Refit coefficients on training+validation and apply that selected shrinkage to the held-out test. Baseline and historical-club-control models are OLS; their player additions are shrunk against the corresponding baseline.
- Common baseline controls: competition, month sine/cosine and early season, in addition to rank and its square. The fourth, stricter baseline retains Current and Baseline separately, their squares and interaction. This prevents a squad feature from being credited merely for undoing the fixed blend.
- The blend is the production near-anchor 0.6 Current / 0.4 Baseline rule. We do not test the production year-ahead interpolation curve or claim measured improvement over the entire deployed match model.
- Target adjustment uses the opponent blend **frozen at the anchor**, plus home advantage estimated before 2022. It never uses future opponent ratings. Actual future opponents define this retrospective adjusted target; they are not future-information predictors.
- No production formulas, rating tables, database rows, migrations or deployed model inputs were changed.

## Chronological samples and boundary exclusions

| Horizon | Training anchors | Validation anchors | Test anchors | Test clubs | Adjusted-target test anchors | Purged crossing split boundaries |
|---|---:|---:|---:|---:|---:|---:|
| 5 matches | 2,794 | 1,827 | 4,126 | 297 | 4,085 | 428 |
| 10 matches | 2,505 | 1,557 | 3,831 | 295 | 3,711 | 914 |
| 20 matches | 1,931 | 1,019 | 3,239 | 292 | 2,897 | 1,886 |

Adjusted targets require a known pre-anchor opponent strength for every future opponent, so their sample is smaller. Results across different horizons are not directly comparable as identical populations; results across models within each table are paired. “All clubs” means all eligible clubs in the covered league dataset, not worldwide coverage.

## Baseline, Current and blend comparisons

Lower MSE is better. Raw and residual squad additions have numerically identical predictions here, so they share one column. Positive percentage improvement means lower test MSE. These are averaged future outcomes, not single-match probability scores.

| Target | Horizon | Club baseline | Club-only MSE | + Raw/residual squad MSE | Improvement | Paired Δ MSE 95% CI |
|---|---:|---|---:|---:|---:|---|
| Mean goal difference | 5 | Baseline only | 0.63407 | 0.62423 | 1.55% | -0.01441 to -0.00575 |
| Mean goal difference | 5 | Current only | 0.62162 | 0.60527 | 2.63% | -0.02158 to -0.01137 |
| Mean goal difference | 5 | Existing 0.6/0.4 blend | 0.61138 | 0.60705 | 0.71% | -0.00636 to -0.00228 |
| Mean goal difference | 5 | Current + Baseline separately | 0.61316 | 0.60708 | 0.99% | -0.00846 to -0.00386 |
| Mean goal difference | 10 | Baseline only | 0.37586 | 0.36676 | 2.42% | -0.01409 to -0.00484 |
| Mean goal difference | 10 | Current only | 0.36843 | 0.35158 | 4.57% | -0.02236 to -0.01147 |
| Mean goal difference | 10 | Existing 0.6/0.4 blend | 0.35769 | 0.35190 | 1.62% | -0.00940 to -0.00236 |
| Mean goal difference | 10 | Current + Baseline separately | 0.35826 | 0.35230 | 1.66% | -0.00887 to -0.00349 |
| Mean goal difference | 20 | Baseline only | 0.24094 | 0.23347 | 3.10% | -0.01213 to -0.00267 |
| Mean goal difference | 20 | Current only | 0.23636 | 0.22088 | 6.55% | -0.02153 to -0.00888 |
| Mean goal difference | 20 | Existing 0.6/0.4 blend | 0.22601 | 0.22077 | 2.32% | -0.00892 to -0.00126 |
| Mean goal difference | 20 | Current + Baseline separately | 0.22514 | 0.22032 | 2.14% | -0.00757 to -0.00191 |
| Points per game | 5 | Baseline only | 0.35399 | 0.34940 | 1.30% | -0.00663 to -0.00264 |
| Points per game | 5 | Current only | 0.34875 | 0.34148 | 2.09% | -0.00943 to -0.00510 |
| Points per game | 5 | Existing 0.6/0.4 blend | 0.34419 | 0.34169 | 0.73% | -0.00393 to -0.00121 |
| Points per game | 5 | Current + Baseline separately | 0.34569 | 0.34279 | 0.84% | -0.00410 to -0.00187 |
| Points per game | 10 | Baseline only | 0.20214 | 0.19783 | 2.13% | -0.00654 to -0.00230 |
| Points per game | 10 | Current only | 0.19884 | 0.19139 | 3.75% | -0.00966 to -0.00508 |
| Points per game | 10 | Existing 0.6/0.4 blend | 0.19407 | 0.19140 | 1.38% | -0.00412 to -0.00125 |
| Points per game | 10 | Current + Baseline separately | 0.19506 | 0.19219 | 1.47% | -0.00410 to -0.00173 |
| Points per game | 20 | Baseline only | 0.12492 | 0.12107 | 3.08% | -0.00613 to -0.00156 |
| Points per game | 20 | Current only | 0.12329 | 0.11544 | 6.37% | -0.01124 to -0.00427 |
| Points per game | 20 | Existing 0.6/0.4 blend | 0.11840 | 0.11571 | 2.27% | -0.00423 to -0.00103 |
| Points per game | 20 | Current + Baseline separately | 0.11863 | 0.11604 | 2.18% | -0.00395 to -0.00123 |
| Opponent/venue-adjusted goal difference | 5 | Baseline only | 0.58598 | 0.57886 | 1.21% | -0.01102 to -0.00329 |
| Opponent/venue-adjusted goal difference | 5 | Current only | 0.57826 | 0.56272 | 2.69% | -0.02060 to -0.01058 |
| Opponent/venue-adjusted goal difference | 5 | Existing 0.6/0.4 blend | 0.56535 | 0.56191 | 0.61% | -0.00539 to -0.00153 |
| Opponent/venue-adjusted goal difference | 5 | Current + Baseline separately | 0.56701 | 0.56276 | 0.75% | -0.00636 to -0.00214 |
| Opponent/venue-adjusted goal difference | 10 | Baseline only | 0.34955 | 0.34416 | 1.54% | -0.00994 to -0.00115 |
| Opponent/venue-adjusted goal difference | 10 | Current only | 0.34721 | 0.33161 | 4.49% | -0.02111 to -0.01026 |
| Opponent/venue-adjusted goal difference | 10 | Existing 0.6/0.4 blend | 0.33311 | 0.32969 | 1.03% | -0.00576 to -0.00128 |
| Opponent/venue-adjusted goal difference | 10 | Current + Baseline separately | 0.33331 | 0.32995 | 1.01% | -0.00589 to -0.00103 |
| Opponent/venue-adjusted goal difference | 20 | Baseline only | 0.22240 | 0.21861 | 1.70% | -0.00838 to +0.00074 |
| Opponent/venue-adjusted goal difference | 20 | Current only | 0.22017 | 0.20711 | 5.93% | -0.01938 to -0.00652 |
| Opponent/venue-adjusted goal difference | 20 | Existing 0.6/0.4 blend | 0.20705 | 0.20446 | 1.25% | -0.00498 to -0.00005 |
| Opponent/venue-adjusted goal difference | 20 | Current + Baseline separately | 0.20623 | 0.20419 | 0.99% | -0.00459 to +0.00063 |

The fixed blend is a stronger simple baseline than Current alone in these held-out forecasts. Adding raw squad strength to Current alone therefore overstates the practical gain available relative to the existing blend. Against the blend, raw squad additions improve GD MSE by 0.71%, 1.62% and 2.32% at 5/10/20 matches, respectively.

## Circularity and genuinely incremental information

Raw squad strength correlates **0.946** with the existing blend on the ten-match test sample. Much of its level is already club information.

**Residualization is not an independent test by itself.** The squad residual is raw squad strength minus its training-only expectation from the complete club baseline. Adding either variable to that same linear baseline spans the same predictors. Predictions agree to numerical precision (maximum differences recorded in results.json). A smaller residual correlation does not prove new information.

The stronger test below keeps both club ratings separately, adds the squad’s embedded historical club-strength mean and mean square, then adds either raw squad rating or the neutral squad component. Neutral ratings keep the existing statistical/position transformation but fix the explicit club-strength input to 1000. The remaining statistics can still reflect club tactics and environment; “neutral” does not mean causal intrinsic talent.

| Target | Horizon | Strong club/history baseline MSE | + Raw squad MSE | + Neutral squad MSE | Neutral improvement | Neutral Δ MSE 95% CI |
|---|---:|---:|---:|---:|---:|---|
| Mean goal difference | 5 | 0.61106 | 0.60605 | 0.60592 | 0.84% | -0.00746 to -0.00301 |
| Mean goal difference | 10 | 0.35632 | 0.35143 | 0.35127 | 1.42% | -0.00778 to -0.00276 |
| Mean goal difference | 20 | 0.22325 | 0.21952 | 0.21930 | 1.77% | -0.00651 to -0.00122 |
| Points per game | 5 | 0.34507 | 0.34251 | 0.34254 | 0.73% | -0.00366 to -0.00148 |
| Points per game | 10 | 0.19445 | 0.19193 | 0.19196 | 1.28% | -0.00359 to -0.00144 |
| Points per game | 20 | 0.11797 | 0.11579 | 0.11577 | 1.87% | -0.00337 to -0.00097 |
| Opponent/venue-adjusted goal difference | 5 | 0.56491 | 0.56157 | 0.56274 | 0.38% | -0.00320 to -0.00118 |
| Opponent/venue-adjusted goal difference | 10 | 0.33105 | 0.32857 | 0.32852 | 0.76% | -0.00467 to -0.00046 |
| Opponent/venue-adjusted goal difference | 20 | 0.20414 | 0.20276 | 0.20274 | 0.69% | -0.00371 to +0.00098 |

This supports some incremental statistical information beyond explicit club scaling: the neutral component retains gains, and raw squad strength is not materially necessary to obtain them. But adjusted-performance gains are only 0.38%, 0.76% and 0.69%; the 20-match interval includes zero. The review criterion of at least 1% MSE improvement beyond historical-club controls with consistent support across direct and adjusted outcomes is not satisfied overall.

## Cohorts: strongest controls plus neutral squad

All cohorts are defined at prediction time and overlap. Promotion/relegation requires observed prior-season membership in mapped domestic tiers. Missing membership is unknown. Early season is fewer than five prior league-season matches. The transfer-window proxy is January/July/August in mapped European leagues, not exact registration deadlines. Large squad change is at least 0.35 total-variation distance between minutes shares in the previous five and preceding five matches; it also captures injuries, rotation and coverage effects.

The ten-match horizon illustrates the cohort results; all 5/10/20 grids and intervals are retained in results.json. Negative Δ MSE favours adding the neutral component.

| Cohort | GD/points anchors | Clubs | Adjusted anchors | GD improvement | GD Δ MSE 95% CI | Points improvement | Adjusted GD improvement | Adjusted Δ MSE 95% CI |
|---|---:|---:|---:|---:|---|---:|---:|---|
| all | 3,831 | 295 | 3,711 | 1.42% | -0.00778 to -0.00276 | 1.28% | 0.76% | -0.00467 to -0.00046 |
| promoted | 293 | 41 | 289 | 3.32% | -0.01846 to -0.00242 | 2.77% | 0.11% | -0.01028 to +0.01250 |
| relegated | 179 | 19 | 176 | 2.40% | -0.01927 to +0.00457 | 1.44% | 2.64% | -0.01824 to +0.00295 |
| early_season | 510 | 276 | 496 | 0.92% | -0.00934 to +0.00176 | 0.52% | 0.34% | -0.00623 to +0.00394 |
| transfer_window_proxy | 554 | 180 | 548 | 1.49% | -0.00996 to +0.00015 | 1.16% | 0.37% | -0.00580 to +0.00343 |
| large_squad_change | 616 | 253 | 615 | 1.83% | -0.01189 to -0.00242 | 1.72% | 1.27% | -0.00873 to -0.00046 |

- **Promoted:** promising direct-outcome gains at ten matches (3.32% GD; 2.77% points), but only 0.11% adjusted-GD improvement. At twenty matches adjusted GD worsens by 1.57%, with a wide interval. Do not treat the direct gains as confirmed independent ability measurement.
- **Relegated:** limited to 19 test clubs at the ten/twenty-match horizons; longer-horizon intervals are wide. No reliable special coefficient follows.
- **Early season:** no clear long-horizon advantage; ten-match GD and points gains are under 1%, with intervals spanning zero.
- **Transfer-window calendar proxy:** direct point estimates are positive, but intervals are generally inconclusive. Calendar months are not verified transfer events.
- **Large observed squad change:** the most promising targeted follow-up. At ten matches the neutral component improves GD by 1.83%, points by 1.72%, and adjusted GD by 1.27%, with pointwise club-bootstrap intervals below zero. This subgroup was predefined, but multiple comparisons and noisy turnover measurement still require prospective confirmation. At twenty matches the adjusted-GD interval crosses zero.

## Temporal dependence and stability

Anchors every five matches overlap for the 10/20-match targets. The principal bootstrap resamples entire clubs, retaining within-club horizon overlap. As a sensitivity, circular moving blocks of 26 calendar weeks retain stretches of common calendar shocks. The test period supplies only about four such blocks, so those intervals should not be read as abundant independent temporal evidence. Neither method fully captures all shared-opponent dependence or model-fitting uncertainty.

| Target | Horizon | Club-cluster Δ MSE 95% CI | 26-week-block Δ MSE 95% CI | Nonoverlapping test anchors | Nonoverlapping improvement |
|---|---:|---|---|---:|---:|
| Mean goal difference | 5 | -0.00746 to -0.00301 | -0.00675 to -0.00361 | 4,126 | 0.84% |
| Mean goal difference | 10 | -0.00778 to -0.00276 | -0.00662 to -0.00368 | 1,905 | 1.47% |
| Mean goal difference | 20 | -0.00651 to -0.00122 | -0.00628 to -0.00225 | 808 | 2.05% |
| Points per game | 5 | -0.00366 to -0.00148 | -0.00351 to -0.00147 | 4,126 | 0.73% |
| Points per game | 10 | -0.00359 to -0.00144 | -0.00337 to -0.00144 | 1,905 | 1.29% |
| Points per game | 20 | -0.00337 to -0.00097 | -0.00319 to -0.00130 | 808 | 2.03% |
| Opponent/venue-adjusted goal difference | 5 | -0.00320 to -0.00118 | -0.00297 to -0.00152 | 4,085 | 0.38% |
| Opponent/venue-adjusted goal difference | 10 | -0.00467 to -0.00046 | -0.00421 to -0.00119 | 1,852 | 0.80% |
| Opponent/venue-adjusted goal difference | 20 | -0.00371 to +0.00098 | -0.00361 to +0.00038 | 720 | 0.69% |

Nonoverlapping sensitivity selects every Hth club-match anchor from the test predictions of the same fitted models; it is not another tuning exercise. Direct-outcome gains persist. The uncertain twenty-match adjusted result also persists.

| Horizon | Period | GD improvement | Points improvement | Adjusted-GD improvement |
|---:|---|---:|---:|---:|
| 5 | 2024-25 | 0.72% | 0.64% | 0.31% |
| 5 | 2025-onward | 0.96% | 0.82% | 0.45% |
| 10 | 2024-25 | 1.18% | 1.11% | 0.42% |
| 10 | 2025-onward | 1.65% | 1.45% | 1.11% |
| 20 | 2024-25 | 1.04% | 1.34% | -0.27% |
| 20 | 2025-onward | 2.73% | 2.55% | 1.77% |

Twenty-match adjusted performance is slightly worse in the earlier period and better in the later one. That limits claims of stable long-horizon independent skill information.

## Limits and recommended next experiment

- These are forward chronological predictions with purged labels, but reconstructed inputs and statistical weights were developed using historical data, including these years. They are not pristine prospective or untouched development holdouts.
- Observed completed league matches may differ from the next actual fixtures when a club exits coverage. Full-horizon requirements select clubs that remain observable; relegation/transfer coverage exits are not missing at random.
- Current registered squads, signed-but-not-yet-observed players, reliable historical injury availability and prospective squad component snapshots are unavailable. Deployment changes do not equal transfer changes.
- Subgroup intervals are pointwise and not adjusted for the many horizons, outcomes, baselines and cohorts. A positive subgroup result alone is not a production rule.
- Effects on direct performance need not be effects on intrinsic club ability. Adjusting for frozen opponent strength reduces some of the apparent gain, particularly among promoted clubs.

**Next experiment:** freeze the production club model and run a separate ten-match shadow forecast. Capture dated registered squads, eligibility/availability, incoming/outgoing player IDs, prior minutes, the neutral player component and its club-history controls before outcomes. Preregister the full sample and a large-squad-change interaction, rather than fitting a special promoted/relegated coefficient from these results. Require replicated improvements in both raw and opponent-adjusted performance, use verified transfer events instead of month proxies, retain coverage exits, and select the evaluation duration from a club-clustered power analysis.

The experiment supports investigating a separate forward-looking squad forecast feature. **It does not support feeding raw squad rating into production club strength, which would risk reinforcing the club information already present in player ratings. No implementation changes were made.**

## Reproduction

```bash
/tmp/thecornerfc-experiment-venv/bin/pip install -r experiments/player_club_strength/requirements.txt
# Requires the prior frozen player replay and membership caches; no database access:
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 /tmp/thecornerfc-experiment-venv/bin/python experiments/squad_forward/run.py
# To refit using the already frozen squad anchors:
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 /tmp/thecornerfc-experiment-venv/bin/python experiments/squad_forward/run.py --cached-rows
/tmp/thecornerfc-experiment-venv/bin/python experiments/squad_forward/write_report.py
/tmp/thecornerfc-experiment-venv/bin/python -m unittest discover -s tests -p "test_squad_forward_experiment.py"
```

Run source SHA-256: `900a6af258fb1e0889a75f3244d94eccc699de16203b3e4ac7d3d756a8207cba`. Frozen squad-row SHA-256: `a4cd7edff4559b992a6548c554024e087b6fcd9ee7066a7a70283aec6ddd4308`. Source-data, membership and upstream replay fingerprints are recorded in `results.json`. Frozen inputs remain in ignored `.cache/`; tracked artifacts contain no credentials.
