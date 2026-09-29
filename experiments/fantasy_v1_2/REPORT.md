# Fantasy v1.2: result

Run 2026-09-29 on `.cache/fantasy_v1_2_inputs.json.gz` (sha256 `bd399811…`). The pre-registered design is in `DESIGN.md`, and every number is in `results.json`. Test rows: 41,167 player-fixtures from 2024-07-01 on. Target: the full reconstructed total, which is v1's total plus reconstructed bonus.

## Verdict: not shown on the site

It fails criterion 1, so v1.1 stays on the FPL tab.

| Criterion | Result |
|---|---|
| 1. MAE and RMSE below v1.1, 95% CI excluding 0 | **Fail.** MAE +0.012 (0.010 to 0.013) worse; MSE −0.025 (−0.035 to −0.015) better |
| 2. Bias ±5% overall, ±10% by position | Pass: +0.6% overall; G −0.2%, D −0.8%, M +0.4%, F +3.3% |
| 3. Goalkeeper MAE below v1.1 | Pass: 1.251 vs 1.260, CI −0.017 to −0.0005 |
| 4. Start ECE ≤ 0.03, overall and goalkeepers | Pass: 0.010 overall, 0.012 GK (v1.1's GK ECE is 0.038) |

## What the numbers say

- **Goalkeepers and defenders get better on every measure.** Keeper bias goes from −4.2% to −0.2%. The keeper start logistic fixes v1.1's under-confidence: regular keepers' mean P(start) was 0.82 under v1.1 and 0.86 under v1.2, against 0.86 actual.
- **Midfielders and forwards get worse on MAE.** Adding expected bonus and cards moves every prediction toward the mean. Points are skewed (most games score 1–2), and MAE rewards predicting the median, so a more accurate mean can raise MAE. RMSE, which rewards the mean, improves for every position.
- **Bonus is calibrated but weak.** Mean predicted 0.124 against 0.125 reconstructed; correlation 0.29.
- **The team save multiplier (M = 20) does not earn its place.** By multiplier tercile, v1.2 under-predicts save points for low-multiplier teams (0.47 predicted vs 0.54 actual; v1.1 gave 0.55) and over-corrects in the middle tercile.
- **Regular starting keepers:** reconstructed full points average 2.89 per match, counting matches they didn't start. v1.1 predicts 2.68 and v1.2 2.88. **On this target, v1.1 is about 7% low for keepers, not a point low.**

## Limits

- Bonus is an approximation of FPL's BPS. It has no clearances, recoveries, big chances or errors, which FPL weights heavily for defenders and keepers. So real FPL bonus for keepers may well be higher than reconstructed. That would make the real gap bigger than 7%. It is **not checked**: that would need captured FPL results, a new use of FPL data.
- 14 of 99k rows differ from `player_features`' window by one appearance: a player who moved clubs and played elsewhere at the same kickoff. v1's replay counts that appearance; production does not.
- Everything after the design (this report included) was seen after the v1.2 test, so any v1.3 built from it needs prospective evidence.
