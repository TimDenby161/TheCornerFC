# Architectures: results

Run on 2026-10-12 with the evaluator registered in `DESIGN.md` (hashes at its foot, unchanged
between registration and the final stage). Inputs: the research frame. Nothing was deployed
and no stored prediction was changed.

## Verdict

**The boosted-tree correction meets the bar. The weekly-refitted Poisson model does not, and is
worse than production. Nothing here changes production: meeting the bar earns a proposal and a
prospective check (`REGISTER.md`).**

Final period, 2024-07-01 to 2026-10-11, 44,383 matches, 119 weeks. Replayed production scores
0.99360; the base rates 1.06710. Negative is better. The bar is −0.002.

| Candidate | Log loss | Change | 99.6% interval | 95% interval | Label |
|---|---|---|---|---|---|
| A1 `dc`, hierarchical time-weighted Poisson | 0.99897 | **+0.00538** | +0.00368 to +0.00687 | +0.00421 to +0.00643 | no gain shown (worse) |
| A2 `gb`, boosted correction to production | 0.99080 | **−0.00280** | −0.00410 to −0.00147 | −0.00370 to −0.00190 | **meets the bar** |
| A3 `pool2`, production 0.7 + dc 0.3 | 0.99337 | −0.00022 | −0.00077 to +0.00021 | −0.00057 to +0.00009 | no gain shown |
| A4 `pool3`, production 0.1 + gb 0.9 | 0.99078 | −0.00282 | −0.00400 to −0.00162 | −0.00364 to −0.00200 | meets the bar (it is `gb`) |

The intervals are at 1 − 0.05 / 13. `experiments/shots_proxy` later made the round fourteen
comparisons; at 1 − 0.05 / 14 nothing in this table changes label.

## A2: the boosted correction

| Condition | |
|---|---|
| Log loss better by 0.002 | Yes (−0.00280) |
| 99.6% interval excludes zero | Yes |
| Brier agrees | Yes (−0.00179, −0.00268 to −0.00085) |
| Better in 2024/25 and 2025/26 | Yes (−0.00258, −0.00262; −0.00428 in 2026/27 so far) |
| No goal market worse by 0.0005 | Yes: every one is better |
| 60% of competitions no worse | Yes (48 of 62) |

The development figure was −0.00320. The final period gave −0.00280.

| | Production | `gb` |
|---|---|---|
| Log loss | 0.99360 | 0.99080 |
| Brier | 0.59277 | 0.59097 |
| Ranked probability score | 0.20634 | 0.20549 |
| Top pick right | 51.58% | 51.76% |
| Calibration error | 0.0103 | 0.0109 |
| Sharpness power | 1.10 | 1.09 |

Goal markets, log-loss change:

| Over 1.5 | Over 2.5 | Over 3.5 | Over 4.5 | Both teams score |
|---|---|---|---|---|
| −0.00208 | −0.00193 | −0.00275 | −0.00215 | −0.00061 |

That is three times what the goal-level candidate of `goals_home_scores` gave on the same lines.

### Where it helps and where it does not

| | Matches | Change |
|---|---|---|
| Leagues | 38,538 | −0.00326 |
| Cups | 5,845 | +0.00023 |

| Most improved | Matches | Change | | Most worsened | Matches | Change |
|---|---|---|---|---|---|---|
| Gibraltar Premier Division | 300 | −0.0201 | | Europa Conference League | 991 | +0.0072 |
| Armenia Premier League | 348 | −0.0133 | | Albania Superliga | 403 | +0.0053 |
| Azerbaijan Premyer Liqa | 418 | −0.0122 | | Champions League | 639 | +0.0035 |
| Egypt Premier League | 668 | −0.0121 | | National League | 1,262 | +0.0029 |
| Ligue 2 | 689 | −0.0110 | | Russia Premier League | 568 | +0.0027 |
| Greece Super League 1 | 513 | −0.0088 | | Bosnia Premijer Liga | 423 | +0.0022 |

| | Premier League | La Liga | Serie A | Bundesliga | Ligue 1 | Championship | League One | League Two |
|---|---|---|---|---|---|---|---|---|
| `gb` | −0.0027 | −0.0045 | −0.0058 | +0.0003 | −0.0025 | −0.0040 | −0.0016 | −0.0038 |

- **It is a league improvement.** Seven of the eight leagues above are better.
- **All three European competitions are worse.** The same was true of `shots_proxy`. Ties between
  clubs from different leagues are the one place every candidate of this round struggles.

One figure each, no interval.

## A1: the Poisson model

Worse than production by 0.0054, in every season, in leagues (+0.0044) and far more in cups
(+0.0120), and in 51 of 62 competitions. Its sharpness power is 1.18: it is too flat. Its own
goal lines, with no calibration fitted, are slightly better than production's at 1.5, 3.5 and
4.5 (about −0.001) and no different at 2.5.

- It has results and xG only. Production also has line-ups, injuries, the current and long-term
  rank blend and a tuned draw boost, so the deficit is not evidence against the family.
- A gain would have been evidence for it, and there is none. Combined with production at the
  weight development chose, it adds nothing that the interval can see (−0.00022).
- **The Dixon-Coles low-score term was fitted at zero**, as in `goals_home_scores`.

## Checks run after the result (`after.py`): description, not tests

The result was larger than anything else in the round, so before it is believed:

| Check | Finding |
|---|---|
| Are the features built only from earlier matches? | 150 final-period fixtures recomputed straight from the fixtures before them: exact agreement. |
| Is it the injury lists, which were written in September 2026 and not at the time? | Without them: −0.00275. No. |
| Is it the manager history? | Without it: −0.00276. No. |
| Is it all shots and xG? | Without them: −0.00153. They are worth about 0.0013 of the 0.0028. |
| What is left with only the base features and shots and xG? | −0.00167. |

By the statistics a competition has (95% intervals):

| Competitions with | Matches | Change |
|---|---|---|
| xG | 10,483 | −0.00272 (−0.00418 to −0.00128) |
| Shots, no xG | 16,606 | −0.00405 (−0.00556 to −0.00252) |
| Partial statistics | 6,204 | −0.00026 (−0.00219 to +0.00167) |
| Neither | 11,090 | −0.00243 (−0.00392 to −0.00091) |

So the gain has two parts:

1. **Recent shots and xG**, about half of it, largest where there are shots and no xG.
2. **A correction that needs no statistics at all** (−0.0024 in competitions with none). The
   trees see production's own expected margin and total and the league's level, and are
   retrained every half-season. They can learn the errors the audit described (mismatches
   predicted too flat, the goal level stuck at 2.82: the average total correction is −0.05
   goals) and follow them as they move. `ends_and_draws` tried to fix the first with one fixed
   number and found the error was not constant; a correction that is relearned as it goes does
   not need it to be.

The corrections are modest: the margin moves by 0.15 goals (standard deviation), 90% of them
within ±0.24.

**A plain linear version, development only.** A ridge regression of the margin error on five
differences of the two sides' last-ten figures (xG, shots, on target, in the box, goals minus
xG), refitted each half-season, scores −0.00245 (−0.00319 to −0.00172) on the selection window,
against −0.00320 for the trees. It was not scored on the final period. Most of what the trees
found from shots can be written as a formula.

## Computational cost

| | Time |
|---|---|
| `dc`: one weekly fit (about 60,000 matches, 5,000 numbers) | 0.2 to 0.5 seconds |
| `dc`: 275 weekly fits, July 2021 to October 2026 | about a minute |
| `gb`: one half-season retrain (two models, up to 100,000 matches, 44 features) | a few seconds |
| The whole final stage | 88 seconds |

`gb` needs scikit-learn, which production does not have. A formula does not.

## Limits

- The final period had been looked at before this round (`REGISTER.md`). `gb`'s settings and
  features were chosen without it and the result reproduced, but it is not a blind test.
- `gb` corrects the stored projections, which are reconstructions with today's ranks.
- The feature groups were written before any `gb` result, but by someone who had read the
  development diagnostics.
- Boosted trees are hard to explain on the site. Production's margin is shown as named terms
  (`predictions.margin_terms`); a tree's correction has none.
- `dc` is one member of its family on a small grid.

## Leads

- **The shot terms as a formula inside production's margin**, with a full production replay,
  registered against the bar and confirmed prospectively. This is the direction `gb`, the linear
  check and `shots_proxy` all point in.
- **A relearned calibration of the margin and the total**, the part of `gb` that needs no
  statistics.
- **European ties.** Worse under `gb` and under `shots_proxy`. Find out why before either
  touches them, or leave them out.
- **`gb` as a shadow.** Captured beside the live predictions, read by nothing, and judged by a
  registered prospective protocol.
