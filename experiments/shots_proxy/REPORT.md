# Shots as a stand-in for xG: results

Run on 2026-10-12 with the evaluator registered in `DESIGN.md` (hashes at its foot, unchanged
between registration and the final stage). Inputs: the research frame. Nothing was deployed
and no stored prediction was changed.

## Verdict

**It does not meet the bar. It is a real gain below it, in leagues, and it makes cups worse.
No change to production is supported by this experiment alone.**

Final period, 2024-07-01 to 2026-10-11, 44,383 matches. Replayed production 0.99360. Setting
chosen on development: goals weight 0.5, K 10, for matches with shots and no xG.

| | Log loss change | 99.6% interval (14 comparisons) | 95% interval |
|---|---|---|---|
| S, shots | **−0.00061** | −0.00114 to −0.00005 | −0.00100 to −0.00022 |

| Condition | |
|---|---|
| Log loss better by 0.002 | **No** |
| Adjusted interval excludes zero | Yes, narrowly |
| Brier agrees | Yes (−0.00044) |
| Better in 2024/25 and 2025/26 | Yes (−0.00057, −0.00072; −0.00032 in 2026/27 so far) |
| No goal market worse by 0.0005 | Yes (all within 0.0001) |
| 60% of competitions no worse | **No** (35 of 62) |

## Where the gain is

| Matches | n | Change |
|---|---|---|
| With shots and no xG (changed directly) | 10,619 | −0.00158 |
| With xG | 19,522 | −0.00047 |
| With neither | 14,242 | −0.00006 |
| Leagues | 38,538 | −0.00085 |
| Cups | 5,845 | **+0.00098** |

- As `DESIGN.md` expected, the development figure (−0.00153) overstated it. Real xG now covers
  44% of the final period's matches against 21% of the selection window's, and only 24% are
  left for the estimate to act on. On those the gain is −0.0016, against −0.0037 on development.
- Matches with real xG improve too (−0.0005): their clubs' opponents and past seasons are
  better placed.
- **Cups get worse**, the Champions League (+0.0022) and Europa League (+0.0028) most. Ties
  there are between clubs from leagues with real xG, with the estimate and with nothing, whose
  ranks now move at three different speeds. This fits the `rating_dynamics` finding that
  anything altering how leagues sit against each other needs care.

| Most improved | Matches | Change | | Most worsened | Matches | Change |
|---|---|---|---|---|---|---|
| A-League | 337 | −0.0084 | | Russia Premier League | 568 | +0.0062 |
| Ligue 2 | 689 | −0.0062 | | Serbia Super Liga | 670 | +0.0029 |
| Segunda División | 1,030 | −0.0060 | | Europa League | 603 | +0.0028 |
| Serie B | 839 | −0.0059 | | Champions League | 639 | +0.0022 |
| League Two | 1,227 | −0.0047 | | Egypt Premier League | 668 | +0.0009 |
| 2. Bundesliga | 678 | −0.0041 | | Jupiler Pro League | 706 | +0.0008 |

The second divisions of the big countries, which have shot counts and no xG, are where it
works. One figure each, no interval.

## Other measures

| | Production | S |
|---|---|---|
| Log loss | 0.99360 | 0.99299 |
| Brier | 0.59277 | 0.59233 |
| Top pick right | 51.58% | 51.72% |
| Calibration error | 0.0103 | 0.0123 |
| Sharpness power | 1.10 | 1.13 |

The ranks spread a little wider, the probabilities do not follow, and the predictions end up
flatter against what happens than before. A release with this in it would want the ends looked
at again.

## Stacked with the rating changes: description only

**Not a registered comparison.** The `rating_dynamics` combined setting (movers pull 0.5, new
club boost 0.5, tau 40) had already been scored on the final period when this was written, so
putting the two together is a choice made with hindsight and its figure flatters.

| | Log loss change | 95% interval |
|---|---|---|
| Rating changes alone | −0.00079 | −0.00117 to −0.00038 |
| Shots and rating changes | −0.00118 | −0.00176 to −0.00060 |

By season: −0.00079, −0.00136, −0.00199. The two overlap: their separate gains sum to −0.00140.
Even flattered, the stack is 59% of the bar.

## Limits

- The lead came from four weeks inside the final period (`DESIGN.md`).
- Only the rank term is swapped. Production also feeds xG into the twelve-month goal averages
  and the attack/defence split, and `results_only` suggests those matter: this is the lower end
  of what the estimate could give.
- K was chosen at the edge of its grid.
- The estimate leaves out blocked shots, which the research inputs do not hold.
- Reconstructions throughout.

## Leads, not tested

- **The estimate in every place production uses xG**, by a full production replay. This is the
  larger version of the same idea and the one most likely to be worth more.
- **Cups.** Either leave the estimate out of the rank change for cup ties, or find why the
  European competitions get worse. Not chosen here, because choosing it now would be choosing on
  the final period.
- **A better estimate.** Shots by body part, situation and distance are not in the feed; shots
  inside the box and on target are what there is.
