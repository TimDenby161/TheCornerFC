# Lineup value: fixed-model paired ablation

Production formulas and database records must remain unchanged. Database extraction runs in a read-only repeatable-read transaction. Frozen inputs are cached locally; reports contain aggregate results only.

Compare no lineup contribution, the current predicted-line contribution and retrospective actual-XI contribution on exactly the same eligible fixtures. All non-lineup inputs remain fixed. Remove the original contribution using immutable snapshot inputs and that snapshot's model-version weights. Recompute probabilities with the current formula only after checking reproduction against the snapshot. Never subtract freshly rebuilt line ratings from an old stored prediction.

Validation: July 2023 through June 2024. Test: July 2024 onwards. Select goalkeeper weight on validation log loss from [-0.005, 0, 0.0025, 0.005, 0.01, 0.02] with outfield weights fixed at 0.005. Negative weight is a diagnostic, not a football recommendation. Report the whole grid and paired uncertainty; do not select on test accuracy. A log-loss improvement of 0.002 per fixture is a provisional practical threshold, not a business-value guarantee.

Primary outcomes: mean three-class log loss, sum-of-three-class Brier and ten-bin classwise calibration error. Secondary: top-probability accuracy and goal-margin MAE. Bootstrap paired fixture losses by UTC ISO week, 2,000 draws; intervals are pointwise and not multiplicity-adjusted. Segment findings are exploratory.

Historical line ratings are rebuilt with full-history player normalizations and current code. Even pre-match player windows do not make these prospective or fully development-independent. Actual XI means use player strength going into the fixture, not that fixture's player performance. Perfect XI is an information counterfactual, not a guaranteed upper bound on a fixed imperfect prediction formula's performance. Also it reveals actual tactical roles, which must be disclosed.

Historical predicted player IDs and availability observation times may be absent. Do not fabricate XI overlap, hours-before-kickoff or availability uncertainty from current injuries or reconstruction timestamps. Audit immutable prospective captures separately. Market comparison requires complete same-bookmaker H/D/A prices actually captured and inserted before the prediction cutoff. Missing evidence is a result, not permission to use future odds.

Post-result robustness check (added after the main ablation, not preregistered): scale all three outfield line weights by 0, .5, 1, 1.5, 2, 3, 4 with goalkeeper weight zero, choose the multiplier on validation log loss separately for predicted and actual XI, and report test once (`weight_sensitivity.py`). This checks that the perfect-XI gap is not an artefact of a mis-scaled fixed weight.
