# Forward squad information beyond club ratings: offline protocol

No production formulas, ratings, model inputs, migrations or database rows are changed. Reuse the frozen player-club experiment extract and replay. This is a historical reconstruction with known model-development/revision leakage, not prospective validation.

## Observations and chronology

One pre-match club observation every five observed league matches (global club match index, not outcome-selected). Require at least eleven eligible squad players, including a goalkeeper, with >=180 historical minutes and scores in the prior replay. Raw squad strength is the average production-formula rolling player rating weighted by each player's minutes in the club's previous five observed matches. Neutral squad strength fixes explicit club strength at 1000 in the otherwise unchanged player formula. Embedded club history is the similarly weighted mean and mean square of players' historical window club levels.

Targets: mean goal difference, points per game, and schedule-adjusted goal difference over the next 5/10/20 observed completed league matches, including the fixture immediately following the snapshot. Require a complete horizon within 365 days. For adjusted GD, freeze each future opponent's latest observed Current/Baseline blend at the anchor, add (opponent strength - 1000)/100, and subtract venue home advantage estimated from pre-2022 results. Future opponent results or updated ratings are never used as predictors or as opponent-strength adjustments. Adjusted targets use actual opponents subsequently faced: this is a retrospective performance target, not an assumption that the future schedule was known. Raw GD and points remain the direct forward outcomes.

Prediction training: 2022-01-01 through 2023-06-30, with **every training target ending before 2023-07-01**. Validation anchors: 2023-07-01 through 2024-06-30, with **every validation target ending before 2024-07-01**. Test anchors start 2024-07-01 and require all horizon outcomes observed. Freeze feature normalization/expectation fits on training only. Select augmentation shrinkage 0/.25/.5/.75/1 on validation MSE, refit downstream coefficients on training+validation, then evaluate test once. Do not retune cohorts or thresholds using test outcomes.

Club baselines: Baseline LT only; Current only; existing near-anchor .6 Current + .4 Baseline blend. Each uses the rank and its square plus common competition indicators, month sine/cosine, and early-season indicator. This tests information added to club-strength forecasts, not the deployed full match model and not the year-ahead interpolation curve.

For each baseline compare:
- club rating only;
- + raw squad strength;
- + squad residual against that same baseline design, fitted on training anchors only;
- + embedded player club history alone (circularity control);
- + embedded history + raw squad;
- + embedded history + neutral squad component.

Use ordinary least squares with stable standardized columns and SVD solves. Raw squad and its residual have the same augmented linear predictor space when residualization uses the complete baseline design. Their predictions should agree numerically; residualization by itself is not evidence of independent information. Hold the baseline controls and sample fixed within each comparison.

## Cohorts, all defined at the anchor

All eligible clubs (not all clubs worldwide); promoted; recently relegated; early season (<5 prior matches in that league/season); transfer-window calendar proxy (January/July/August in mapped European domestic tiers, not exact registration windows); large squad change (>=0.35 total-variation distance between prior-five and preceding-five match minutes shares). Promotion/relegation requires observed prior-season membership in explicitly mapped same-country tiers; missing membership is unknown, not a move. Previous-five-match turnover measures observed deployment/availability, not confirmed transfer transactions.

## Uncertainty, selection and practical meaning

1,000 paired whole-club cluster bootstrap draws preserve overlapping horizons within clubs. Report a 26-week moving-calendar-block bootstrap as dependence sensitivity for aggregate comparisons (limited effective blocks in this short holdout), and test metrics on nonoverlapping anchors every H club matches. Intervals are pointwise, not multiplicity-adjusted; neither method fully handles all shared opponents and model-fitting uncertainty. Report sample sizes/clubs and by-period stability. Practical review threshold: >=1% out-of-sample MSE reduction beyond embedded-club-history controls, directional support on direct GD and points plus adjusted GD, and temporal/cohort consistency. Subgroup exploration is hypothesis generation, not permission to deploy.

Frozen player normalization uses pre-2022 data; centre-back team_xga was absent then and omitted consistently. Current website season ratings are not historical predictors. Roster snapshots/registration dates are unavailable: stale/departed players can persist for up to five observed matches, injuries are not reconstructed, and new signings enter after observation. Coverage filtering selects recorded matches. No market-price or causal-talent claims.

A fourth conservative baseline keeps Current and Baseline separately (linear, squares and interaction). This prevents a squad feature from earning apparent independent value merely by reconstructing information lost in the fixed blend. Historical-club-only controls use unshrunk OLS; additions to that stronger baseline choose their shrinkage relative to that same baseline. Raw/residual additions choose shrinkage relative to the corresponding original club-only baseline.
