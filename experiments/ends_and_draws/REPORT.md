# Ends and draws: results

Run on 2026-10-12 with the evaluator registered in `DESIGN.md` (`run.py` SHA-256
`2b91a1d5…16ea7b`, unchanged between registration and the run). Inputs read once from production
through the read-only role. Nothing was deployed and no stored prediction was changed.

## Verdict

**No candidate meets either bar. No change to production is supported.**

| Candidate | Setting chosen on 2023/24 | Test log loss (95%) | Holdout log loss (95%) | Bar A | Bar B |
|---|---|---|---|---|---|
| H1, the ends | every probability to the power 1.10 | −0.00076 (−0.00115 to −0.00039) | −0.00001 (−0.00047 to +0.00045) | No | No |
| H2, the draws | draw boost 1.07, fading at 1.0 goals | −0.00018 (−0.00034 to −0.00002) | −0.00007 (−0.00027 to +0.00011) | No | No |
| Joint | power 1.08, draw boost 1.09, fade 1.5 | −0.00075 (−0.00108 to −0.00044) | −0.00013 (−0.00052 to +0.00026) | No | No |
| Stacked | power 1.10, draw boost 1.07, fade 1.0 | −0.00064 (−0.00112 to −0.00018) | +0.00021 (−0.00036 to +0.00079) | No | No |

Negative is better. Bar A needs −0.002; the best here is a third of that.

Three things stand out:

1. **The effects are real on the test period and small.** Every interval there excludes zero, and
   calibration improves. The largest gain is 0.0008.
2. **They do not show up on the holdout.** On the two seasons that were never looked at, every
   interval straddles zero and H1 is flat. The ends were already well calibrated there: the ends
   gap is 0.0085 on the holdout against 0.0204 on test.
3. **The gain is a cup effect.** In the listed leagues the changes are worth nothing or slightly
   harmful; in the cups they are worth about 0.003. Fewer than half of the competitions are no
   worse under any candidate, which is the condition that fails Bar B for all four.

## Inputs

| Period | Matches | Weeks | Source |
|---|---|---|---|
| Holdout, 2021-07-01 to 2023-06-30 | 38,753 | 105 | reconstructed |
| Validation, 2023-07-01 to 2024-06-30 | 19,239 | 53 | reconstructed |
| Test, 2024-07-01 to 2026-10-11 | 44,383 | 119 | 43,658 reconstructed, 725 live |

The harness's copy of the probability step matched `predictions.outcome_probabilities` to within
6e-16 on all 102,375 rows. The stored probabilities were reproduced from the stored projected
goals on all 102,375 rows, so the stored history carries the current probability step.

## What validation chose

Baseline validation log loss 0.99474.

| Hypothesis | Chosen | Validation log loss | Note |
|---|---|---|---|
| H1 `power` | a = 1.10 | 0.99409 | The form chosen. 1.08 scores the same to five places. |
| H1 `quadratic` | c = 0.08 | 0.99411 | Not chosen |
| H1 `linear` | k = 1.08 | 0.99426 | Not chosen |
| H2 | inflation 1.07, fade 1.0 | 0.99458 | A flat surface: 1.05 to 1.08 with a fade of 0.75 to 1.25 are within 0.00004 |
| Joint | a = 1.08, inflation 1.09, fade 1.5 | 0.99407 | With the ends stretched, the draw boost wants to stay near where it is |
| Stacked | a = 1.10, inflation 1.07, fade 1.0 | 0.99422 | Worse than either part's best: the two overlap |

The joint search is the informative one. Sharpening the probabilities already takes weight off the
draw, so applying both chosen settings at once removes it twice. That is why `stacked` is the
worst of the four on test and the only one that is worse on the holdout.

## Test period, 44,383 matches

| | Baseline | H1 | H2 | Joint | Stacked |
|---|---|---|---|---|---|
| Log loss | 0.99360 | 0.99284 | 0.99342 | 0.99285 | 0.99296 |
| Brier change (95%) | 0.5928 | −0.00043 (−0.00069 to −0.00019) | −0.00012 (−0.00022 to −0.00003) | −0.00043 (−0.00065 to −0.00023) | −0.00033 (−0.00067 to −0.00003) |
| Top pick right | 51.59% | 51.59% | 51.60% | 51.58% | 51.60% |
| Calibration error | 0.0103 | 0.0058 | 0.0070 | 0.0051 | 0.0080 |
| Ends gap | 0.0204 | 0.0095 | 0.0211 | 0.0079 | 0.0090 |
| Fall in ends gap (95%) | | 54% (−5% to 74%) | −4% | 61% (10% to 72%) | 56% (−1% to 76%) |
| Draw gap | 0.0103 | 0.0053 | 0.0038 | 0.0044 | 0.0079 |
| Fall in draw gap (95%) | | 48% | 63% (7% to 65%) | 57% (6% to 71%) | 24% (−76% to 66%) |
| Competitions no worse | | 29 of 62 | 24 of 62 | 31 of 62 | 26 of 62 |

The chosen H1 form leaves the projected goals alone, so the goal markets do not move for any
registered candidate. For the record, the two margin forms moved every goal market by less than
0.0004, inside the guard.

### Against Bar B

| Condition | H1 | H2 | Joint | Stacked |
|---|---|---|---|---|
| 1. Log loss better, interval excludes zero | Yes | Yes | Yes | Yes |
| 2. Brier no worse | Yes | Yes | Yes | Yes |
| 3. Named gap falls 30%, interval excludes zero | **No** (ends interval reaches −5%) | Yes | Yes | **No** |
| 4. Calibration error no worse | Yes | Yes | Yes | Yes |
| 5. Same direction in 2024/25, 2025/26 and holdout | Yes, barely (holdout −0.00001) | Yes | Yes | **No** |
| 6. No goal market worse by 0.0005 | Yes | Yes | Yes | Yes |
| 7. 60% of competitions no worse | **No** (47%) | **No** (39%) | **No** (50%) | **No** (42%) |

`joint` comes nearest: it fails only condition 7.

### Calibration at the ends, test period

| The model said | Baseline: matches, said, happened | Joint: matches, said, happened |
|---|---|---|
| Home win under 10% | 256, 7.7%, **5.9%** | 391, 7.6%, 7.9% |
| Home win 10 to 20% | 2,107, 16.0%, **13.1%** | 2,345, 15.9%, 14.3% |
| Home win 70 to 80% | 1,974, 74.2%, **78.4%** | 2,351, 74.5%, 74.8% |
| Home win 80 to 90% | 557, 83.5%, **88.3%** | 841, 83.8%, 87.8% |
| Away win under 10% | 1,689, 7.4%, **5.5%** | 2,180, 7.0%, 6.9% |
| Away win 10 to 20% | 7,755, 15.9%, 15.0% | 8,350, 15.7%, 16.1% |
| Away win 70 to 80% | 433, 74.0%, **78.8%** | 551, 74.2%, 75.9% |

The same bands on the holdout, baseline: home win 10 to 20% said 16.0%, happened 15.2%; home win
70 to 80% said 74.2%, happened 74.8%; away win under 10% said 7.2%, happened 7.4%. There was
little to fix there, and `joint` overshoots (home win 70 to 80%: said 74.3%, happened 72.2%).

### Draws by expected margin, test period

| Expected margin | Matches | Happened | Baseline | H2 | Joint |
|---|---|---|---|---|---|
| Under 0.25 | 11,839 | 27.4% | 28.3% | 27.5% | 27.7% |
| 0.25 to 0.5 | 10,614 | 26.0% | 27.2% | 26.4% | 26.5% |
| 0.5 to 1 | 13,629 | 24.0% | 24.7% | 24.0% | 23.8% |
| 1 to 1.5 | 5,515 | 19.7% | 20.3% | 19.9% | 19.1% |
| 1.5 and over | 2,786 | 10.7% | 14.3% | 14.3% | 13.0% |

H2 fixes the close games. It cannot touch the mismatches, where the boost is already nil and the
excess comes from the Poisson step itself.

## By season

Log-loss change, candidate minus baseline.

| Season | Matches | Role | H1 | H2 | Joint | Stacked |
|---|---|---|---|---|---|---|
| 2021/22 | 19,070 | holdout | +0.00010 | +0.00002 | −0.00001 | +0.00042 |
| 2022/23 | 19,683 | holdout | −0.00013 | −0.00016 | −0.00025 | −0.00001 |
| 2023/24 | 19,239 | settings chosen here | −0.00065 | −0.00016 | −0.00066 | −0.00052 |
| 2024/25 | 19,662 | test | −0.00081 | −0.00011 | −0.00078 | −0.00062 |
| 2025/26 | 19,515 | test | −0.00052 | −0.00014 | −0.00054 | −0.00036 |
| 2026/27 to 11 October | 5,206 | test | −0.00145 | −0.00055 | −0.00140 | −0.00174 |

Brier moves the same way in every cell: between −0.0001 and −0.0010 on the test seasons, and
within ±0.0003 of nothing on the holdout seasons.

Draw rate, predicted against actual: the baseline says 25.1%, 25.2% and 24.6% in the three test
seasons; 24.2%, 24.2% and 22.8% happened. H2 says 24.4%, 24.5% and 24.0%; `joint` says 24.3%,
24.3% and 23.7%.

The gain grows from nothing in 2021/22 to its largest in the current season. The experiment does
not say why.

## By competition

62 competitions have 300 or more test matches. Log-loss change, match-weighted:

| | Matches | H1 | H2 | Joint | Stacked |
|---|---|---|---|---|---|
| Leagues | 38,270 | −0.00014 | +0.00028 | −0.00014 | +0.00047 |
| Cups | 4,824 | −0.00284 | −0.00248 | −0.00298 | −0.00523 |

Under `joint`, by competition:

| Most improved | Matches | Change | | Most worsened | Matches | Change |
|---|---|---|---|---|---|---|
| FA Trophy | 690 | −0.0059 | | A-League | 337 | +0.0046 |
| Gibraltar Premier Division | 300 | −0.0057 | | Serie B | 839 | +0.0043 |
| Bosnia Premijer Liga | 423 | −0.0053 | | Ligue 2 | 689 | +0.0028 |
| Champions League | 639 | −0.0051 | | 2. Bundesliga | 678 | +0.0027 |
| Armenia Premier League | 348 | −0.0051 | | Albania Superliga | 403 | +0.0020 |
| Europa League | 603 | −0.0032 | | Hungary NB I | 449 | +0.0016 |

| | Premier League | La Liga | Serie A | Bundesliga | Ligue 1 | Championship | League One | League Two |
|---|---|---|---|---|---|---|---|---|
| Matches | 819 | 837 | 818 | 660 | 668 | 1,219 | 1,215 | 1,227 |
| Joint | +0.0008 | −0.0016 | +0.0003 | +0.0002 | +0.0005 | +0.0006 | −0.0004 | +0.0008 |

These are descriptive, one figure each with no interval. The pattern they make is the point: the
competitions that improve are the ones with the widest gaps between sides (cups across divisions,
European group stages, small leagues with one dominant club), and the evenly matched second
divisions get worse. A single number applied everywhere is the wrong shape for that.

## What this does and does not show

- The pattern found in the diagnostics is real in 2023 to 2026: outsiders overrated, strong
  favourites underrated, a point too many draws.
- A one- or two-number correction recovers 0.0008 of log loss there, a third of the standing bar,
  and none on 2021 to 2023.
- The error sits in mismatches, mostly in cups. It is not spread across the model.
- Nothing here bears on the bookmakers. No odds were read, and P6 is as it was.

## Leads, not tested

- **The gap between divisions.** If cup ties between sides from different levels are where the
  model is too flat, the thing to look at is how far apart the levels' ranks sit, not the
  probability step. That would be a change to the ranking, with its own experiment.
- **Why the error has grown since 2021/22.** One candidate is the xG blend, whose coverage rose
  over the same seasons. Untested.
- **Draws in mismatches.** The 1.5-and-over band predicts 14.3% and 10.7% happen, and neither
  hypothesis reaches it.
- **A prospective check** of `joint` on snapshots from now on would be the clean test if any of
  this is taken further. It would need registering as its own protocol.

## Limits

- The test period is where the hypotheses came from (`DESIGN.md`). The holdout is the only
  period here that was not looked at first, and it is the one that shows nothing.
- The holdout is earlier than the tuning year, not later.
- Every row but 725 is a reconstruction: today's ranks replayed over past matches.
- Intervals are pointwise. Four registered candidates and three forms were scored.
