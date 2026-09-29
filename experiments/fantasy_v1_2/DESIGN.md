# Fantasy v1.2: bonus, cards, penalty saves and better goalkeepers

Written 2026-09-29, before any v1.2 output was looked at. It follows v1's method (`experiments/fantasy_v1/DESIGN.md`): read-only extract, chronological replay, fit on train, select on validation, refit on train + validation, test once. v1.1 is not changed: its parameters stay frozen, its code paths give identical numbers, and P8 keeps judging it alone.

## Why

v1.1 expects about 3–3.5 points a game from the best goalkeepers (Pickford 3.54 for GW6), well below what they score in FPL. The gap comes from what v1.1 leaves out, not from a bug:

1. **Bonus** is not modelled. It is the biggest missing part for goalkeepers.
2. **P(start) for an ever-present goalkeeper** tops out at about 0.92. One start logistic serves every position, and keepers are far steadier than outfielders.
3. **Saves** depend only on the opponent's expected goals, so a team that lets through more shots on target gets no more save points.
4. **Penalty saves and cards** are in the target but not in the model.

## Target

The primary target is the **full reconstructed total**: v1's `total` (appearance, goals, assists, clean sheet, goals conceded, saves, penalty saves, cards) **plus reconstructed bonus**. v1's `total` and `v1` targets are also reported.

**Reconstructed bonus.** Each player's match BPS is approximated from API-Football stats with FPL's published BPS values, using only the actions API-Football records:

| Action | BPS |
|---|---|
| 1–59 minutes / 60+ | 3 / 6 |
| Goal: GK/DEF, MID, FWD | 12, 18, 24 |
| Assist | 9 |
| Clean sheet (GK/DEF, 60+ minutes) | 12 |
| Save / penalty save | 2 / 15 |
| Key pass | 1 |
| Tackle (API-Football tackles) | 2 |
| Every 2 blocks + interceptions | 1 |
| Successful dribble | 1 |
| Pass completion with 30+ passes: 70–79%, 80–89%, 90%+ | 2, 4, 6 |
| Shot off target (shots − shots on target) | −1 |
| Foul conceded | −1 |
| Penalty conceded | −3 |
| Yellow / red card | −3 / −9 |

API-Football does not record clearances, recoveries, big chances, crosses, errors, offsides, being tackled, own goals, penalty misses or the winning goal, so those are left out. Within each match the three highest BPS among players who played get 3, 2 and 1, with FPL's tie rules (competition ranking: a tie for first gives both 3 and the next player 1). **This is an approximation of FPL's bonus, not FPL's bonus.** Checking it against FPL's own bonus would need captured FPL results, which is a new use of FPL data and is not done here.

## Model: v1.1 plus five parts

Everything v1.1 does is kept, with the same data, the same decay (0.85) and the same K (450).

1. **Goalkeeper minutes.** Keepers get their own start and sub logistics (same features, availability terms included), fitted on keeper rows only. Outfielders keep the shared ones.
2. **Team-adjusted saves.** Team saves ~ Poisson(m × (a + b × λ against)). The multiplier m is the team's actual saves over its league matches in the last 365 days, divided by the a + b × λ expected in those matches, shrunk toward 1 with M pseudo-matches. M is chosen on validation from {5, 10, 20} by GK points MAE.
3. **Penalty saves.** GK: expected minutes / 90 × league penalty saves per team-match × 5.
4. **Cards.** Every player: expected minutes / 90 × his yellow and red rates per 90 × −1 and −3. His rates are over his league appearances in the last 365 days, shrunk toward his position's rate with 900 pseudo-minutes.
5. **Bonus.** Expected bonus = max(0, x · β_position), with no intercept, where x is:
   - P(play), P(60+)
   - expected goals, expected assists
   - P(clean sheet) (GK/DEF only)
   - expected save points (GK only)
   - his base BPS per 90 × expected minutes / 90

   Base BPS is his BPS without minutes, goals, assists, clean sheets, saves, penalty saves or cards, over his league appearances in the last 365 days, shrunk toward his position's rate with 900 pseudo-minutes. β is fitted by least squares per position on the training rows' predicted components against reconstructed bonus. The predicted components come from the other parameters fitted on the same rows, so there is no look-ahead.

## Splits

These are v1's: 2020/21 history only; train 2021-07-01 to 2023-07-01; validation 2023/24; test 2024-07-01 onward. M is chosen on validation. Everything is then refitted on train + validation, frozen in `thecornerfc/fantasy_params_v1_2.json`, and applied once to test.

## Comparisons on test (same rows)

- v1.2 against v1.1 with its frozen parameters (`thecornerfc/fantasy_params.json`), on the full target: MAE and RMSE, paired round-cluster bootstrap (2,000 draws, 95%).
- Recent average and PPG, both recomputed on the full target.
- By position, with goalkeepers reported on their own.
- Bonus: mean predicted against mean reconstructed, overall and by position; share of each position's bonus.
- GK start calibration (10 bins, ECE).
- Save calibration by λ tercile, and by team-multiplier tercile.

## Success criteria (decided now)

v1.2 replaces v1.1 **on the site's FPL tab** only if, on test:

1. MAE **and** RMSE on the full target are lower than v1.1's, with 95% intervals excluding zero.
2. Mean prediction within ±5% of the mean full target overall and within ±10% for each position.
3. Goalkeepers' MAE on the full target is lower than v1.1's.
4. Start ECE ≤ 0.03, overall and for goalkeepers.

If any fails, v1.2 is not shown and the report says which failed. Either way v1.2 is captured prospectively beside v1.1 (P9), because a backtest built with 2026 knowledge of what was wrong with v1.1 is not independent evidence.
