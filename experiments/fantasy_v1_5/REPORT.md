# Fantasy v1.5: result

Run 2026-09-30 (`results.json`) on `inputs.json.gz`: 1,620 Premier League team-matches from 2024-07, with 184 penalties. Fit on 2024-25, test on 2025-26 and 2026-27 to date, given actual minutes. v1.5 adds penalty takers, misses and FPL-only assists to v1.4 (DESIGN.md).

## Who takes the penalty (test: 101 penalties)

| Model | Log loss per penalty |
|---|---|
| **v1.5** (decayed record for this club + α × non-penalty goal rate) | **1.19** |
| Last taker on the pitch (smoothed the same way) | 1.33 |
| v1.4's implied share (goal share × minutes) | 1.81 |

Both checks pass. On the fit season α = 0.5 and δ = 0.05, the edge of the grid. The penalty backfill starts in 2024-07, so a 2024-25 record is at most a season old and the decay is barely identified. Refitted on everything, δ = 0.5 (a penalty a year ago counts half).

Calibration on the test seasons (player-matches grouped by predicted share):

| Predicted share | Player-matches | Expected attempts | Actual |
|---|---|---|---|
| 0–0.1 | 1,286 | 27.7 | 16 |
| 0.1–0.3 | 120 | 20.7 | 23 |
| 0.3–0.6 | 38 | 18.8 | 24 |
| 0.6–1.0 | 45 | 33.8 | 38 |

The shares are too flat: non-takers get about 12 attempts too many, and takers too few. The α term spreads more to first-time takers than happens.

## How many penalties

| Candidate | Test log-likelihood per team-match |
|---|---|
| (a) league rate | −0.3717 |
| (b) × (team λ / mean λ)^1.5 | −0.3726 |
| (c) team rate, shrunk | −0.3714, but only with the grid's largest shrinkage (1,000 matches): the league rate |

Chosen: **(a) the league rate**, 0.114 attempts per team-match. Conversion is 82.6%.

## Who scores (the pre-set check that matters for points)

The log-likelihood of each goal's scorer changes by **+0.0004 per goal** (95% CI −0.0030 to +0.0037) over 1,138 goals in 623 team-matches.
- In matches with a penalty goal: +0.0044.
- In matches without one: −0.0004.

**This check does not pass: the improvement is too small to tell from zero.** Penalties are about 7% of goals, so moving them to the right player barely changes who scores overall. The gain is concentrated on takers, which is where P11 looks.

## FPL-only assists (FPL results, GW1–5 of 2026-27)

- FPL gave **130 assists for 134 goals**. API-Football recorded 97 for the same goals.
- 5 of the 33 extra assists are for winning a penalty a teammate scored. In API-Football data, 16% of scored penalties were won by the taker himself, which earns no assist.
- The other 28 come to **0.219 per non-penalty goal**, from rebounds, deflections and similar.
- Per player, the extras correlate equally weakly with shots and key passes per 90 (0.18 each, 243 players). v1.5 shares them by shots, following FPL's rule that a saved or blocked shot's rebound credits the shooter. Five gameweeks can't tell the two apart.

## Frozen v1.5 (`thecornerfc/fantasy_params_v1_5.json`)

Refitted on all seasons:

| Parameter | Value |
|---|---|
| Rate | 0.114 attempts per team-match |
| Conversion | 82.6% |
| α | 0.5 |
| δ | 0.5 |
| Self-won | 0.158 |
| Penalties won per foul drawn | 0.0089 |
| FPL extra assists | 0.219 per non-penalty goal |

FPL's penalty order is blended in with weight 0.75 when FPL lists takers, and order k counts 0.15^(k−1). These values were set before any v1.5 prediction, because there is no history of FPL's order to fit them on.

Next gameweek, before FPL's order is captured:
- Palmer, Bruno Fernandes, Thiago and Haaland get 0.08–0.09 expected penalty goals each, about 0.3–0.4 points.
- FPL assists add 0.1–0.25 points to most regular attackers.

## Limits

- The scorer check is inconclusive, as above.
- Taker shares are too flat.
- FPL's order weights are judgment, not fitted.
- The FPL assist rate rests on 5 gameweeks.
- The penalty record starts in 2024-07.

Prospective snapshots (P11) are the real test.
