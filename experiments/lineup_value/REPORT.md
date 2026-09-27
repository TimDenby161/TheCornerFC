# Lineup value: what lineup information adds to match prediction

**Recommendation: keep the lineup system and all production formulas unchanged. Do not prioritise improving lineup prediction as a route to materially better match forecasts.**

On 9,601 held-out fixtures the current predicted-XI adjustment improves log loss by **0.0024** per fixture. About 45% of that can be reproduced by a club-strength-only proxy with no lineup information, leaving about **0.0013** attributable to lineups specifically. Knowing the actual starting XI would add only a further **0.0005**. The existing system therefore captures most of the value available from XI knowledge under this formula, and that value is small. Goalkeeper weight zero is supported. Prospective timing, availability and market evidence are too sparse to evaluate.

## Answers

1. **How much value does the existing lineup system add?** 0.0024 log loss and 0.0014 Brier per fixture versus no lineup adjustment (95% CI -0.00344 to -0.00135). It passes the 0.002 practical threshold only against a naive baseline. Against a club-strength-only proxy the lineup-specific gain is 0.0013 (-0.00190 to -0.00082), below that threshold. Accuracy is unchanged (51.10% → 51.10%).
2. **How much more could perfect XI knowledge add?** 0.0005 log loss beyond the predicted XI (-0.00087 to -0.00018): 0.0009 in 2024-25 and 0.0002 from 2025, whose interval crosses zero. Rescaling the outfield weights for the actual XI does not change this materially (see sensitivity).
3. **Would better lineup prediction materially improve match prediction?** Unlikely. Even perfect prediction closes a gap of about 0.0005, a quarter of the practical threshold, and a realistic improvement would capture only part of it. The gap is concentrated in close matches (predicted strength gap below 0.086 goals), where lineup errors matter relatively more. Timely lineup/availability inputs near kickoff may matter more than XI selection accuracy itself, but the prospective sample cannot test that yet.

## Design and provenance

- Frozen read-only extracts taken 2026-09-27 12:03 UTC (prediction/lineup snapshots) and 12:10 UTC (fixture history and odds). No API calls, database writes or production changes. Input SHA-256 fingerprints are in results.json.
- **Historical fixed-formula ablation** (the main evidence): every fixture from July 2023 in the covered player-data competitions with complete predicted and actual line ratings for both teams. The no-lineup baseline is the current `predict_match` rebuilt chronologically from club ranks and prior form, without injury or lineup inputs. The predicted and actual XI line ratings are then added with production weights (GK 0, DEF/MID/FWD 0.005 per rating point) on identical fixtures.
- Actual-XI ratings use each starter's rating **going into** the fixture, not their performance in it. It is an information counterfactual (who started, in which line), not a guaranteed upper bound for a fixed imperfect formula.
- Validation: July 2023–June 2024 (4,629 fixtures). Test: July 2024 onward (9,601 fixtures, 112 weeks). Exclusions from 16,354 considered: 1,676 without eleven rated starters or a full predicted XI, 448 with a missing line rating.
- Uncertainty: paired UTC ISO-week cluster bootstrap, 2,000 draws; pointwise, not multiplicity-adjusted. Brier is summed over three classes; ECE is mean classwise ten-bin calibration error (bin-sensitive, not a selection criterion alone).
- **Club-strength proxy (circularity control):** player ratings contain club strength, so part of any lineup gain may be club information the baseline under-uses. The proxy predicts each fixture's predicted-line margin from Current and Baseline rank differences only, fitted on validation without outcomes, and adds that instead of lineups.

## Main held-out comparison (identical fixtures)

| Model | Log loss | Brier | ECE | Accuracy | GD MAE | Δ log loss vs none | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---|
| No lineup adjustment | 1.00252 | 0.59929 | 0.01164 | 51.10% | 1.2460 | +0.00000 | +0.00000 to +0.00000 |
| Club-strength proxy (no lineups) | 1.00144 | 0.59884 | 0.01147 | 51.05% | 1.2500 | -0.00108 | -0.00205 to -0.00017 |
| Current predicted XI | 1.00011 | 0.59791 | 0.01065 | 51.10% | 1.2476 | -0.00241 | -0.00344 to -0.00135 |
| Actual XI (retrospective) | 0.99957 | 0.59753 | 0.01049 | 51.15% | 1.2465 | -0.00295 | -0.00391 to -0.00190 |

Validation shows the same ordering: none 0.99356, proxy 0.99238, predicted 0.99108, actual 0.99084.

| Comparison | Δ log loss | 95% CI | Δ Brier |
|---|---:|---|---:|
| Predicted XI vs club proxy | -0.00133 | -0.00190 to -0.00082 | -0.00092 |
| Actual XI vs club proxy | -0.00187 | -0.00240 to -0.00134 | -0.00131 |
| Actual XI vs predicted XI | -0.00054 | -0.00087 to -0.00018 | -0.00038 |

Binned calibration error is mixed: on test ECE falls from 0.01164 to 0.01065, but on validation it rises from 0.01378 to 0.01603. ECE differences this small are within binning noise; log loss and Brier, which improve in both periods, are the primary evidence. Goal-difference MAE is essentially unchanged. Full calibration bins are in results.json.

| Period | n | None | Predicted | Actual | Predicted vs none | Actual vs predicted |
|---|---:|---:|---:|---:|---:|---:|
| 2024-25 | 4,508 | 0.99732 | 0.99528 | 0.99441 | -0.00204 | -0.00087 |
| 2025-onwards | 5,093 | 1.00712 | 1.00438 | 1.00414 | -0.00274 | -0.00024 |

## Breakdowns (held-out, exploratory)

Large versus small predicted strength difference splits at the validation median absolute predicted-line margin, 0.086 goals.

| Group | n | Weeks | None log loss | Predicted vs none | 95% CI | Actual vs predicted | 95% CI |
|---|---:|---:|---:|---:|---|---:|---|
| Large predicted strength gap | 4,530 | 110 | 0.9398 | -0.00478 | -0.00704 to -0.00277 | -0.00027 | -0.00075 to +0.00024 |
| Small predicted strength gap | 5,071 | 112 | 1.0586 | -0.00030 | -0.00098 to +0.00034 | -0.00078 | -0.00126 to -0.00031 |
| Championship (40) | 1,104 | 81 | 1.0420 | -0.00009 | -0.00295 to +0.00277 | -0.00023 | -0.00108 to +0.00058 |
| League One (41) | 1,079 | 91 | 1.0255 | -0.00228 | -0.00488 to +0.00044 | -0.00099 | -0.00212 to +0.00018 |
| League Two (42) | 1,058 | 91 | 1.0591 | -0.00012 | -0.00291 to +0.00271 | -0.00017 | -0.00119 to +0.00080 |
| Major League Soccer (253) | 982 | 83 | 1.0311 | -0.00153 | -0.00402 to +0.00092 | -0.00070 | -0.00203 to +0.00068 |
| Premier League (39) | 739 | 75 | 1.0113 | -0.00061 | -0.00386 to +0.00244 | -0.00029 | -0.00134 to +0.00072 |
| La Liga (140) | 715 | 79 | 0.9740 | -0.00301 | -0.00849 to +0.00217 | -0.00114 | -0.00274 to +0.00046 |
| Serie A (135) | 700 | 78 | 0.9819 | -0.00546 | -0.01051 to -0.00036 | -0.00021 | -0.00146 to +0.00099 |
| Eredivisie (88) | 597 | 78 | 0.9754 | -0.00161 | -0.00685 to +0.00362 | -0.00018 | -0.00113 to +0.00077 |
| Süper Lig (203) | 574 | 78 | 0.9690 | -0.00507 | -0.00907 to -0.00108 | +0.00010 | -0.00116 to +0.00131 |
| Pro League (307) | 560 | 64 | 0.9290 | -0.00693 | -0.01187 to -0.00195 | -0.00187 | -0.00367 to -0.00010 |
| Bundesliga (78) | 539 | 69 | 0.9641 | -0.00497 | -0.01088 to +0.00061 | -0.00034 | -0.00171 to +0.00097 |
| Ligue 1 (61) | 527 | 73 | 0.9836 | -0.00060 | -0.00546 to +0.00480 | -0.00056 | -0.00207 to +0.00091 |

Most of the predicted-XI gain comes from fixtures where the predicted lines differ a lot; that is where the adjustment moves probabilities. The remaining value of perfect XI knowledge is larger in close fixtures. Per-competition intervals are wide and mostly cross zero; competition-specific weights are not supported. All competitions are in results.json.

## Outfield weight sensitivity (post-result robustness check)

Multiplier on production DEF/MID/FWD weights (1.0 = production, 0 = no lineup), GK weight zero. Chosen on validation log loss.

| Multiplier | Predicted: validation | Predicted: test | Actual: validation | Actual: test |
|---:|---:|---:|---:|---:|
| 0 | 0.99356 | 1.00252 | 0.99356 | 1.00252 |
| 0.5 | 0.99183 | 1.00086 | 0.99173 | 1.00061 |
| 1 | 0.99108 | 1.00011 | 0.99084 | 0.99957 |
| 1.5 | 0.99127 | 1.00024 | 0.99086 | 0.99938 |
| 2 | 0.99236 | 1.00120 | 0.99175 | 0.99998 |
| 3 | 0.99711 | 1.00550 | 0.99600 | 1.00346 |
| 4 | 1.00497 | 1.01271 | 1.00327 | 1.00975 |

Validation selects the production scale (1.0) for both predicted and actual XI. The best test multiplier for the actual XI (1.5) beats production scaling by only 0.00019. The small perfect-XI gap is not caused by a mis-scaled weight.

## Goalkeeper contribution

The goalkeeper weight was selected on validation log loss from the grid below, with outfield weights fixed at production values. Negative weights are diagnostics, not football recommendations.

| GK weight | Predicted: validation | Predicted: test Δ vs GK 0 | 95% CI | Actual: validation | Actual: test Δ vs GK 0 | 95% CI |
|---:|---:|---:|---|---:|---:|---|
| -0.005 | 0.99112 | +0.00016 | -0.00026 to +0.00056 | 0.99088 | +0.00028 | -0.00013 to +0.00067 |
| 0 | 0.99108 | +0.00000 | +0.00000 to +0.00000 | 0.99084 | +0.00000 | +0.00000 to +0.00000 |
| 0.0025 | 0.99122 | +0.00008 | -0.00012 to +0.00029 | 0.99098 | +0.00002 | -0.00017 to +0.00023 |
| 0.005 | 0.99146 | +0.00027 | -0.00012 to +0.00070 | 0.99122 | +0.00016 | -0.00023 to +0.00056 |
| 0.01 | 0.99225 | +0.00097 | +0.00018 to +0.00182 | 0.99201 | +0.00073 | -0.00004 to +0.00154 |
| 0.02 | 0.99504 | +0.00362 | +0.00205 to +0.00532 | 0.99485 | +0.00312 | +0.00156 to +0.00474 |

Validation selects GK weight **0** for the predicted XI and **0** for the actual XI. Small positive weights (0.0025–0.005) are statistically indistinguishable from zero on test. Weights of 0.01 and above are clearly worse. This supports the current zero weight *for this goalkeeper rating*; it does not show goalkeepers are unimportant. A keeper rating built from shot-stopping evidence might behave differently and would be a separate experiment.

## Prospective captures: timing, XI accuracy, availability and market

Lineup-timing, predicted-player overlap and availability reports only exist in immutable prospective captures, which began on 2026-09-26. Only **12 finished fixtures** (one week) have a reproducible prospective prediction, a frozen predicted XI and an aligned official XI. A further 97 captured fixtures had no complete line adjustment. Mean correctly predicted starters: 18.2 of 22. **This sample cannot support any conclusion**; the rows below are shown only to document what the pipeline produces.

| Group | n | None | Predicted | Actual |
|---|---:|---:|---:|---:|
| All prospective | 12 | 1.1569 | 1.1796 | 1.1727 |
| XI overlap:high 20 to 22 | 3 | 1.2143 | 1.2749 | 1.2546 |
| XI overlap:low under 16 | 2 | 1.1852 | 1.1791 | 1.1741 |
| XI overlap:medium 16 to 19 | 7 | 1.1242 | 1.1389 | 1.1373 |
| availability:no reports not known healthy | 7 | 1.1891 | 1.2003 | 1.1969 |
| availability:reports present | 5 | 1.1119 | 1.1506 | 1.1389 |
| hours:1 to 6 | 4 | 1.0835 | 1.1155 | 1.0968 |
| hours:under 1 | 8 | 1.1936 | 1.2116 | 1.2107 |
| predicted strength gap:large | 3 | 1.4522 | 1.5249 | 1.5045 |
| predicted strength gap:small | 9 | 1.0585 | 1.0645 | 1.0621 |
| Captured ≥6h before kickoff | 5 | 1.0857 | 1.1166 | 1.1025 |
| Captured ≥24h before kickoff | 0 | — | — | — |
| Captured ≥48h before kickoff | 0 | — | — | — |

**Model versus market:** 12 fixtures have a complete same-bookmaker H/D/A price captured and inserted before the prediction cutoff. Market log loss 1.1522 versus model 1.1796 (predicted XI) and 1.1569 (no lineup). No historical timestamped odds exist before 2026-09-26, so no historical model-versus-market comparison is possible and nothing should be inferred from this sample.

## Limitations

- The historical baseline is a chronological rebuild of the current formula without injury inputs. Historical predicted XIs mostly lack injury exclusions, so the production system (which uses live availability) may perform somewhat differently from this reconstruction.
- Historical player ratings are rebuilt with current code and full-history percentile references. Player windows are pre-match, but reference scaling and model development used these years. This is not a pristine prospective test.
- The actual XI reveals roles and line assignment, not only identities. It is not a strict upper bound for a better formula that could use lineups differently (for example interactions or per-line weights); only the scale of the existing linear adjustment was tested.
- Competition and strength-gap groups are exploratory and overlapping; intervals are pointwise without multiplicity adjustment. The club proxy and weight sensitivity were added as robustness checks.
- Covered competitions are those with player data (the player-club frozen fixture set), not every competition the site predicts.

## Recommended next experiment

Let prospective captures accumulate for a pre-registered period (sized by a week-clustered power calculation; likely several months) and repeat the paired comparison on production snapshots only. Test: (a) value by capture time before kickoff, especially predictions refreshed after official lineups; (b) availability-report presence and injury uncertainty; (c) model versus the timestamped market on identical fixtures. Separately, if goalkeeper impact is of interest, test a keeper-specific rating rather than re-weighting the current one. Do not spend effort on lineup-selection accuracy until (a) shows timing matters.

## Reproduction

```bash
# Optional fresh read-only extraction (needs .env DATABASE_URL; enforced read-only transaction):
python3 experiments/lineup_value/extract.py && python3 experiments/lineup_value/extract_history.py
# Requires the frozen player-club input cache; no database access:
OPENBLAS_NUM_THREADS=1 /opt/anaconda3/bin/python experiments/lineup_value/run.py
/opt/anaconda3/bin/python experiments/lineup_value/weight_sensitivity.py
python3 experiments/lineup_value/write_report.py
/opt/anaconda3/bin/python -m unittest discover -s tests -p "test_lineup_value_experiment.py"
```

No production formulas, constants, ratings or database rows were changed.
