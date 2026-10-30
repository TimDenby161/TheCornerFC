# GAP ratings: report

Run once on 2026-10-30 with the registered `run.py` (DESIGN.md), on the research frame's frozen
inputs, in 261 seconds. Full figures: `results.json`.

## Verdict

**A real gain that misses the screen.** Adding opponent-adjusted, venue-split shot ratings to A18's
trees made them better on both periods, on every secondary measure, and on every goal market. It
missed one condition: breadth across competitions (35 of 62 no worse; 60% was needed). The gain
comes from the shot ratings, **not from corners**.

The baseline reproduced A18's registered final result against production exactly (−0.00280 on
44,383 matches), so the comparison is valid.

## Results

| | A18 | A18 + GAP | Difference |
|---|---|---|---|
| Development window, 2022-07 to 2024-06 (38,922) | 0.99432 | 0.99342 | −0.00090 (95%: −0.00127 to −0.00053) |
| **Final, 2024-07 to 2026-10-11 (44,383)** | 0.99080 | 0.99023 | **−0.00056 (99%: −0.00109 to −0.00007)** |
| Final Brier | | | −0.00038 (95%: −0.00075 to −0.00005) |
| Final calibration error | 0.0109 | 0.0099 | better |
| Final top-pick accuracy | 51.76% | 51.82% | |
| 2024/25 · 2025/26 · 2026/27 so far | | | −0.00094 · −0.00027 · −0.00027 |
| Leagues (38,538) · cups (5,845) | | | −0.00055 · −0.00066 |
| Goal markets (over 1.5 to 4.5, both score) | | | −0.00034 to −0.00011, all better |
| Against production | −0.00280 | −0.00336 | |

| Screen condition | Held? |
|---|---|
| Final 99% interval below zero | yes |
| Development better | yes |
| Final Brier better | yes |
| Better in 2024/25 and 2025/26 | yes |
| No goal market worse by more than 0.0005 | yes |
| 60% of competitions (300+ matches) no worse | **no: 35 of 62 (56%)** |

## Where it helps

| Segment (final) | Matches | Difference (95%) |
|---|---|---|
| Both sides have shot ratings | 32,423 | −0.00099 (−0.00145 to −0.00050) |
| A side has no shot rating yet | 11,960 | **+0.00058 (+0.00008 to +0.00105)**, worse |
| European competitions | 2,233 | −0.00267 (−0.00470 to −0.00050) |
| Match has xG | 19,522 | −0.00077 (−0.00133 to −0.00020) |
| Match has no xG | 24,861 | −0.00041 (−0.00097 to +0.00015) |
| Without the corner ratings (descriptive) | 44,383 | −0.00054 (−0.00089 to −0.00018) |

- **Corners add nothing.** Dropping them leaves the gain unchanged. Shots and shots on target,
  adjusted for the opponent and split by venue, carry it.
- **It hurts where the ratings are missing.** In matches where a side has no shot rating (cups
  against sides from uncovered leagues, the first matches of sides new to the data), the
  candidate is worse. Found after the result, so any fix (for example, falling back to A18 there)
  is a new candidate and needs fresh evidence.
- **It helps in Europe**, where A18 alone was worse than production in the October round.

The rating settings chosen on 2021/22 counts (no results looked at): shots λ 0.2, φ1 0.7, φ2 0.5;
shots on target λ 0.15, φ1 0.7, φ2 0.5; corners λ 0.1, φ1 0.5, φ2 0.7.

## Limits

- The final period had been scored by 14 earlier candidates. A pass would only have been a lead;
  this result is a lead too.
- The tree settings were A18's and not re-tuned, which favours neither side.
- It improves A18, which is not the live model. Production would gain only through A18 or a
  formula carrying the shot ratings.

## Next

A prospective test of A18 + GAP against A18 (P15's method), registered before any live match is
read, with the missing-rating fall-back decided in its design. The owner's decision.
