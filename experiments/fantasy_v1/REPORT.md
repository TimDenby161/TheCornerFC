# Fantasy v1: validation of a simple FPL expected-points model

**Verdict: not yet validated. 3 of 4 preregistered criteria pass.** The model clearly beats points-per-game and recent-average benchmarks (MAE 1.166 vs 1.232 and 1.679; lower in 77 of 81 test rounds), is well calibrated on starts and clean sheets, and the match model adds measurable value. It fails the bias criterion because goalkeepers are under-predicted by 25%: the save component was dropped by the preregistered validation rule. That is a narrow, diagnosable failure, not a reason to scrap the approach. It is still a reason not to build fantasy UI on v1 as it stands.

**Three limits frame every number below:**
1. **No official FPL data exists in the database** (every FPL table is empty; capture is off pending the licensing decision). Official FPL expected points and price **could not be benchmarked**, and the target is *reconstructed* FPL points from API-Football stat lines, without bonus, own goals, penalty misses or defensive contributions.
2. **Team goal expectations in the test are reconstructions**, by the current match model, which was tuned on 2023/24. Prospective match snapshots start 2026-09-26, after the last finished fixture (2026-09-20), so **0 test fixtures had a genuinely pre-kickoff input**.
3. Positions are API-Football G/D/M/F, not FPL's. Gameweeks are API-Football rounds, so there are no FPL doubles or blanks.

## Preregistered criteria (DESIGN.md)

| # | Criterion | Result | Detail |
|---|---|---|---|
| 1 | Beat PPG and recent average on MAE and RMSE, 95% CI excluding 0 | PASS | MAE vs recent -0.066 (-0.076 to -0.055); MSE vs recent -0.613 (-0.674 to -0.556) |
| 2 | Bias ≤ ±5% overall, ≤ ±10% per position (v1-scope target) | FAIL | overall -1.2%; GK -24.9%, DEF -0.5%, MID 0.3%, FWD 4.0% |
| 3 | Start ECE ≤ 0.03 and team clean-sheet ECE ≤ 0.03 | PASS | start 0.0075; clean sheet 0.0259 |
| 4 | Beat the flat-team-goals ablation on MAE | PASS | -0.0121 (-0.0167 to -0.0079) |

Criterion 2 fails on goalkeepers alone. Saves were dropped because on validation (2023/24) the busiest tercile's saves were under-predicted (3.68 vs 4.34, beyond the ±10% rule). That season scored 1.64 goals per team-match against a predicted 1.53. *Post hoc and not preregistered:* with saves included on test, goalkeeper bias would be -3.2% and every position within ±10%, at a small cost in overall MAE (1.170 vs 1.166). That is evidence for putting saves back in v1.1, confirmed on fresh prospective gameweeks, not a retroactive pass.

## Test results (2024/25 to 2026/27 so far)

41,167 player-fixtures (38,091 train, 19,524 validation). The target is reconstructed total points. Players outside the universe (mostly debut appearances for a club) scored 2.1% of test points and are not scored here.

| Predictor | MAE | RMSE | Pearson | Spearman | Mean pred | Mean actual |
|---|---:|---:|---:|---:|---:|---:|
| Fantasy v1 | 1.166 | 1.829 | 0.512 | 0.647 | 1.486 | 1.423 |
| Recent average (last 5) | 1.232 | 1.989 | 0.431 | 0.579 | 1.427 | 1.423 |
| Points per game | 1.679 | 2.186 | 0.321 | 0.379 | 2.133 | 1.423 |
| Ablation: flat team goals | 1.178 | 1.854 | 0.490 | 0.638 | 1.472 | 1.423 |
| Variant: + injury lists (timing unverified) | 1.107 | 1.782 | 0.547 | 0.704 | 1.489 | 1.423 |
| v1.1: + injury lists + saves (chosen after test) | 1.112 | 1.777 | 0.552 | 0.708 | 1.516 | 1.423 |

Paired differences (v1 minus benchmark; negative favours v1). Cluster bootstrap over (season, round), 2,000 draws:

| Versus | ΔMAE, all rows | ΔMSE, all rows | ΔMAE, regulars | ΔMSE, regulars |
|---|---|---|---|---|
| Points per game | -0.513 (-0.530 to -0.497) | -1.433 (-1.572 to -1.308) | -0.193 (-0.218 to -0.169) | -0.879 (-1.103 to -0.700) |
| Recent average (last 5) | -0.066 (-0.076 to -0.055) | -0.613 (-0.674 to -0.556) | -0.189 (-0.209 to -0.169) | -1.027 (-1.135 to -0.928) |
| Ablation: flat team goals | -0.012 (-0.017 to -0.008) | -0.096 (-0.120 to -0.072) | -0.026 (-0.035 to -0.016) | -0.208 (-0.260 to -0.158) |
| Variant: + injury lists (timing unverified) | +0.059 (+0.051 to +0.066) | +0.168 (+0.150 to +0.185) | +0.088 (+0.075 to +0.101) | +0.309 (+0.276 to +0.342) |
| v1.1: + injury lists + saves (chosen after test) | +0.054 (+0.046 to +0.061) | +0.187 (+0.169 to +0.206) | +0.080 (+0.066 to +0.093) | +0.351 (+0.313 to +0.388) |

Most rows are fringe players who score about 0 whatever anyone predicts, so correlation and all-row MAE flatter every predictor. The **regulars** subset (started ≥ 3 of the team's last 5, defined before kickoff; 17,241 rows) is the relevant one for picking. There, v1's MAE is 1.744 vs 1.934 for recent average, and Spearman is 0.352 vs 0.237. A rank correlation of 0.35 among regulars is modest: single-gameweek points are mostly noise.

### Top-N hit rates (per round, across all players)

Hit = a predicted top-N player whose actual points reach that round's actual N-th best. Also shown: mean actual points of the predicted top N.

| Predictor | Top 10 | Top 25 | Top 50 | GK top 5 | DEF top 10 | MID top 10 | FWD top 5 | Top-10 mean pts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fantasy v1 | 18.0% | 28.6% | 31.8% | 36.3% | 31.2% | 26.7% | 32.1% | 4.23 |
| Recent average (last 5) | 11.6% | 23.1% | 27.1% | 30.4% | 23.1% | 22.1% | 26.2% | 3.49 |
| Points per game | 12.2% | 21.7% | 25.3% | 21.7% | 24.1% | 21.5% | 22.5% | 3.29 |
| Ablation: flat team goals | 18.0% | 24.0% | 27.0% | 30.4% | 22.1% | 25.1% | 27.9% | 4.01 |
| Variant: + injury lists (timing unverified) | 18.1% | 29.5% | 32.8% | 36.5% | 32.5% | 28.5% | 32.3% | 4.27 |
| v1.1: + injury lists + saves (chosen after test) | 18.1% | 30.6% | 32.8% | 36.8% | 32.5% | 28.5% | 32.3% | 4.28 |

The match model matters more for ranking than for MAE. Without it (flat team goals), the defender and goalkeeper hit rates fall most, as expected, since clean sheets depend on the opponent.

### Expected minutes

| | v1 | Recent 5-match average minutes |
|---|---:|---:|
| MAE (minutes) | 20.1 | 19.5 |
| RMSE (minutes) | 27.4 | 30.2 |
| Mean vs actual 38.4 | 38.7 | 38.4 |
| Availability variant MAE | 17.4 | |

**v1's minutes MAE is slightly worse than the naive 5-match average** (20.1 vs 19.5), though its RMSE is better. Minutes are close to 0-or-90, and MAE rewards committing to one end: a regular who averaged 90 is predicted 90 by the naive rule, while v1's calibrated expectation is around 76. Expected points need the expectation, so v1 keeps it, but the minutes component is not better than naive on the preregistered minutes metric. By position: GK 16.1 vs 14.7; DEF 21.8 vs 21.2; MID 21.0 vs 20.3; FWD 17.7 vs 17.2.

The injury-list variant cuts minutes MAE to 17.4 and points MAE by 0.059. The injury table has no capture times (every row was rewritten 2026-09-23), so historical lists may contain post-kickoff knowledge. Treat that gain as an upper bound until prospective availability (FPL status flags or timed injury captures) confirms it.

**Start calibration**: ECE 0.0075, Brier 0.1255; mean 0.430 vs 0.426 observed. P(play) ECE 0.0127, P(60+) ECE 0.0106.

| Bin | n | Mean predicted | Observed |
|---|---:|---:|---:|
| 0.0-0.1 | 11,155 | 0.035 | 0.033 |
| 0.1-0.2 | 5,447 | 0.161 | 0.143 |
| 0.2-0.3 | 2,823 | 0.247 | 0.234 |
| 0.3-0.4 | 1,864 | 0.344 | 0.340 |
| 0.4-0.5 | 1,449 | 0.446 | 0.433 |
| 0.5-0.6 | 1,919 | 0.543 | 0.559 |
| 0.6-0.7 | 1,935 | 0.653 | 0.656 |
| 0.7-0.8 | 3,608 | 0.756 | 0.741 |
| 0.8-0.9 | 10,967 | 0.861 | 0.863 |

### Clean sheets

Team level, e^(−λ against) from the match model: test ECE 0.0259, mean 0.241 vs 0.248 observed (1,620 team-matches). On validation the ECE was 0.0407, above the 0.03 bar, with clean sheets over-predicted in that high-scoring season. So clean-sheet calibration inherits the match model's season-level goal errors. On test the model predicted 1.50 goals per team-match against 1.42 actual. Player level (GK/DEF, needs 60+): ECE 0.0072.

| Bin | n | Mean predicted | Observed |
|---|---:|---:|---:|
| 0.0-0.1 | 76 | 0.082 | 0.092 |
| 0.1-0.2 | 511 | 0.158 | 0.135 |
| 0.2-0.3 | 620 | 0.248 | 0.289 |
| 0.3-0.4 | 331 | 0.343 | 0.332 |
| 0.4-0.5 | 75 | 0.434 | 0.440 |
| 0.5-0.6 | 7 | 0.522 | 0.571 |

### Components (test means per player-fixture)

| Component | Predicted | Actual |
|---|---:|---:|
| appearance_points | 0.9806 | 0.9817 |
| goal_points | 0.2667 | 0.2492 |
| assist_points | 0.1210 | 0.1139 |
| clean_sheet_points | 0.2091 | 0.2225 |
| goals_conceded_points | -0.0915 | -0.0871 |
| save_points | 0.0000 | 0.0242 |
| exp_goals | 0.0567 | 0.0532 |
| exp_assists | 0.0403 | 0.0380 |

Goals and assists by position (allocation uses attacking evidence and role, not overall rank):

| Position | xG pred | Goals | Pearson | xA pred | Assists | Pearson |
|---|---:|---:|---:|---:|---:|---:|
| GK | 0.0000 | 0.0000 | – | 0.0022 | 0.0044 | 0.059 |
| DEF | 0.0225 | 0.0186 | 0.101 | 0.0251 | 0.0224 | 0.151 |
| MID | 0.0676 | 0.0643 | 0.283 | 0.0582 | 0.0559 | 0.218 |
| FWD | 0.1110 | 0.1071 | 0.346 | 0.0472 | 0.0436 | 0.213 |

## Segments (exploratory)

"Bias vs total" compares with the full reconstructable total, which includes cards that v1 does not model. So a few percent of over-prediction is expected.

### By position

| Segment | Rows | v1 MAE | Recent MAE | PPG MAE | v1 RMSE | Recent RMSE | v1 Spearman | Recent Spearman | v1 bias vs total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GK | 3,150 | 1.113 | 1.269 | 2.250 | 1.902 | 2.015 | 0.709 | 0.672 | -25.1% |
| DEF | 13,928 | 1.252 | 1.307 | 1.789 | 1.910 | 2.096 | 0.581 | 0.497 | 6.8% |
| MID | 15,105 | 1.142 | 1.219 | 1.528 | 1.806 | 1.959 | 0.648 | 0.578 | 7.1% |
| FWD | 8,984 | 1.091 | 1.123 | 1.564 | 1.706 | 1.856 | 0.700 | 0.639 | 7.9% |

### By ability band (stand-in for price, which is not captured)

Latest player rank before the fixture. **This is not FPL price.** The price-tier question stays open until prices are captured.

| Segment | Rows | v1 MAE | Recent MAE | PPG MAE | v1 RMSE | Recent RMSE | v1 Spearman | Recent Spearman | v1 bias vs total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 80+ | 19,636 | 1.410 | 1.540 | 1.964 | 2.088 | 2.289 | 0.605 | 0.525 | 0.0% |
| 70-80 | 16,668 | 1.003 | 1.019 | 1.486 | 1.627 | 1.742 | 0.633 | 0.567 | 9.5% |
| 60-70 | 3,629 | 0.887 | 0.896 | 1.268 | 1.433 | 1.567 | 0.614 | 0.540 | 15.7% |
| <60 | 154 | 0.343 | 0.225 | 0.989 | 0.528 | 0.650 | 0.294 | 0.276 | 336.9% |
| unrated | 1,080 | 0.307 | 0.181 | 0.969 | 0.633 | 0.635 | 0.354 | 0.379 | 90.3% |

### By regular status

| Segment | Rows | v1 MAE | Recent MAE | PPG MAE | v1 RMSE | Recent RMSE | v1 Spearman | Recent Spearman | v1 bias vs total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| regular | 17,241 | 1.744 | 1.934 | 1.937 | 2.333 | 2.544 | 0.352 | 0.237 | 2.9% |
| other | 23,926 | 0.750 | 0.726 | 1.494 | 1.353 | 1.464 | 0.584 | 0.496 | 8.0% |

### By season

| Segment | Rows | v1 MAE | Recent MAE | PPG MAE | v1 RMSE | Recent RMSE | v1 Spearman | Recent Spearman | v1 bias vs total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024 | 19,536 | 1.162 | 1.212 | 1.633 | 1.822 | 1.967 | 0.649 | 0.593 | 4.5% |
| 2025 | 19,342 | 1.156 | 1.235 | 1.708 | 1.819 | 1.992 | 0.649 | 0.576 | 4.5% |
| 2026 | 2,289 | 1.284 | 1.374 | 1.828 | 1.955 | 2.148 | 0.612 | 0.491 | 3.6% |

### By gameweek

| Segment | Rows | v1 MAE | Recent MAE | PPG MAE | v1 RMSE | Recent RMSE | v1 Spearman | Recent Spearman | v1 bias vs total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rounds 1-5 | 7,053 | 1.243 | 1.336 | 1.786 | 1.901 | 2.101 | 0.614 | 0.500 | 6.2% |
| Rounds 6-19 | 14,301 | 1.166 | 1.221 | 1.641 | 1.844 | 1.989 | 0.657 | 0.600 | 4.2% |
| Rounds 20-38 | 19,813 | 1.139 | 1.203 | 1.669 | 1.790 | 1.947 | 0.652 | 0.592 | 3.9% |

<details><summary>Every round number (pooled over test seasons)</summary>

| Segment | Rows | v1 MAE | Recent MAE | PPG MAE | v1 RMSE | Recent RMSE | v1 Spearman | Recent Spearman | v1 bias vs total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GW 1 | 1,226 | 1.434 | 1.462 | 1.837 | 2.060 | 2.210 | 0.448 | 0.418 | 14.0% |
| GW 2 | 1,435 | 1.261 | 1.435 | 1.935 | 2.020 | 2.327 | 0.653 | 0.452 | 3.8% |
| GW 3 | 1,459 | 1.134 | 1.260 | 1.759 | 1.694 | 1.939 | 0.690 | 0.527 | 7.9% |
| GW 4 | 1,456 | 1.275 | 1.324 | 1.745 | 1.972 | 2.083 | 0.621 | 0.539 | 0.7% |
| GW 5 | 1,477 | 1.145 | 1.222 | 1.667 | 1.762 | 1.942 | 0.658 | 0.565 | 6.6% |
| GW 6 | 996 | 1.117 | 1.203 | 1.636 | 1.802 | 1.941 | 0.646 | 0.588 | 13.3% |
| GW 7 | 995 | 1.114 | 1.207 | 1.618 | 1.729 | 1.932 | 0.707 | 0.622 | 3.5% |
| GW 8 | 1,003 | 1.191 | 1.214 | 1.645 | 1.864 | 1.987 | 0.658 | 0.628 | 3.3% |
| GW 9 | 1,009 | 1.126 | 1.153 | 1.559 | 1.751 | 1.878 | 0.653 | 0.622 | 7.9% |
| GW 10 | 1,016 | 1.087 | 1.156 | 1.589 | 1.689 | 1.875 | 0.710 | 0.628 | 5.7% |
| GW 11 | 1,016 | 1.171 | 1.234 | 1.678 | 1.815 | 1.973 | 0.700 | 0.636 | 1.4% |
| GW 12 | 1,018 | 1.257 | 1.290 | 1.715 | 2.021 | 2.113 | 0.611 | 0.577 | 2.2% |
| GW 13 | 1,021 | 1.171 | 1.217 | 1.648 | 1.930 | 2.080 | 0.656 | 0.584 | 5.9% |
| GW 14 | 1,025 | 1.213 | 1.315 | 1.676 | 1.984 | 2.179 | 0.632 | 0.547 | 1.5% |
| GW 15 | 1,032 | 1.169 | 1.206 | 1.610 | 1.812 | 1.923 | 0.657 | 0.624 | 6.5% |
| GW 16 | 1,035 | 1.162 | 1.151 | 1.601 | 1.895 | 1.953 | 0.654 | 0.635 | 5.2% |
| GW 17 | 1,040 | 1.258 | 1.333 | 1.704 | 1.978 | 2.119 | 0.588 | 0.526 | -0.9% |
| GW 18 | 1,045 | 1.097 | 1.171 | 1.620 | 1.698 | 1.902 | 0.681 | 0.598 | 3.3% |
| GW 19 | 1,050 | 1.183 | 1.238 | 1.670 | 1.807 | 1.963 | 0.656 | 0.592 | 1.4% |
| GW 20 | 1,054 | 1.078 | 1.163 | 1.656 | 1.712 | 1.948 | 0.683 | 0.611 | 8.3% |
| GW 21 | 1,059 | 1.078 | 1.131 | 1.627 | 1.707 | 1.869 | 0.695 | 0.644 | 6.2% |
| GW 22 | 1,061 | 1.179 | 1.271 | 1.691 | 1.865 | 2.046 | 0.639 | 0.576 | 1.6% |
| GW 23 | 1,055 | 1.132 | 1.205 | 1.628 | 1.776 | 1.950 | 0.651 | 0.566 | 7.0% |
| GW 24 | 1,053 | 1.197 | 1.267 | 1.701 | 1.866 | 2.034 | 0.629 | 0.538 | 4.1% |
| GW 25 | 1,032 | 1.127 | 1.197 | 1.635 | 1.847 | 2.005 | 0.654 | 0.577 | 5.8% |
| GW 26 | 1,041 | 1.180 | 1.260 | 1.734 | 1.840 | 2.030 | 0.655 | 0.579 | 1.8% |
| GW 27 | 1,038 | 1.112 | 1.164 | 1.670 | 1.792 | 1.937 | 0.685 | 0.620 | 1.8% |
| GW 28 | 1,036 | 1.082 | 1.127 | 1.621 | 1.693 | 1.834 | 0.673 | 0.621 | 6.5% |
| GW 29 | 1,040 | 1.110 | 1.129 | 1.672 | 1.765 | 1.848 | 0.704 | 0.655 | 1.8% |
| GW 30 | 1,035 | 1.157 | 1.207 | 1.627 | 1.721 | 1.856 | 0.594 | 0.586 | 2.7% |
| GW 31 | 1,040 | 1.156 | 1.221 | 1.699 | 1.785 | 1.977 | 0.660 | 0.604 | 3.0% |
| GW 32 | 1,039 | 1.186 | 1.231 | 1.702 | 1.961 | 2.086 | 0.625 | 0.589 | 3.9% |
| GW 33 | 1,043 | 1.151 | 1.238 | 1.693 | 1.807 | 1.966 | 0.671 | 0.586 | 0.6% |
| GW 34 | 1,044 | 1.127 | 1.194 | 1.690 | 1.735 | 1.895 | 0.668 | 0.607 | 3.7% |
| GW 35 | 1,037 | 1.101 | 1.205 | 1.648 | 1.703 | 1.884 | 0.627 | 0.568 | 7.1% |
| GW 36 | 1,040 | 1.173 | 1.223 | 1.680 | 1.806 | 1.952 | 0.627 | 0.563 | 2.0% |
| GW 37 | 1,037 | 1.169 | 1.212 | 1.695 | 1.833 | 1.961 | 0.644 | 0.596 | 3.2% |
| GW 38 | 1,029 | 1.145 | 1.204 | 1.641 | 1.780 | 1.896 | 0.597 | 0.558 | 4.0% |

</details>

## Selection and parameters

On validation, decay was chosen on minutes MAE (0.5: 20.54, 0.7: 20.47, 0.85: 20.45), which gave **0.85**. K was chosen on points MAE (450: 1.1951, 900: 1.1962, 1800: 1.1977), which gave **450** pseudo-minutes. The differences are tiny, so neither choice matters much. The parameters were refitted on train + validation, then frozen for test; the full set is in results.json.

## What this means for building on it

- **Do not build major fantasy UI on v1 yet.** It beats the simple benchmarks convincingly, but it has not been compared with the benchmark that matters (official FPL xP), nor with price, and its test inputs are reconstructions. None of that can change until the FPL licensing decision is made: FPL IDs are also needed to write `fantasy_prediction_snapshots` (the table keys predictions by FPL player id).
- **v1.1, small and justified by this run:** restore goalkeeper saves; capture availability prospectively; score it on prospective gameweeks against official xP once licensed.
- Consider judging expected minutes by RMSE or a proper score (calibration and Brier are good), since MAE penalises a calibrated expectation of bimodal minutes.

## v1.1 and prospective validation

v1.1 = v1 + goalkeeper saves + injury-list availability. On this test it scores MAE 1.112, with goalkeeper bias vs total 1.1%. But it was **chosen after seeing these test results**, so those numbers are not evidence for it. Its parameters are frozen in `thecornerfc/fantasy_params.json`. `thecornerfc/fantasy_snapshots.py` now stores every component for every upcoming Premier League player before kickoff, with the timed availability and the benchmark values, in `fantasy_fixture_snapshots`. It is judged only on those prospective snapshots, under protocol P8 (`experiments/prospective/PROTOCOLS.md`): 10 rounds, then unblinded once.

## Provenance

- Frozen read-only extract at 2026-09-27 15:24 UTC, input SHA-256 `6319155217e12500…`; code `296bca981bdbd3f0…`; model `4791b21f752fba7d…`.
- FPL tables at extraction: fpl_captures 0, fpl_player_states 0, fpl_player_results 0, fpl_id_map 0, fantasy_prediction_snapshots 0.
- Every test component is stored as immutable content-hashed records (81 rounds) in the local archive `.cache/fantasy_v1_snapshots.jsonl.gz` (SHA-256 `e75e6574980a8c97…`), model version `mv_663faca72325a965d…` (ModelType.FANTASY identity; not registered in the database). Nothing was written to the database.
- Reproduce: `python3 experiments/fantasy_v1/extract.py` (needs psycopg), then `python3.13 experiments/fantasy_v1/run.py` and `write_report.py` (need numpy and scipy).
