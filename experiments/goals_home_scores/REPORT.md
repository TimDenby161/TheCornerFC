# Goals, home advantage and scorelines: results

Run on 2026-10-12 with the evaluator registered in `DESIGN.md` (`run.py` SHA-256
`002490ff…d05d5e68`, `chosen.json` `7845718d…ebc18b98`, unchanged between registration and the
final stage). Inputs: the research frame. Nothing was deployed and no stored prediction changed.

## Verdict

**No candidate meets the bar. The goal level is a real gain below it. No change to production
is supported by this experiment alone.**

Final period, 2024-07-01 to 2026-10-11, 44,383 matches. Negative is better. The bar is −0.002
on each candidate's primary measure.

| Candidate | Setting chosen on development | Primary measure | Change | 99.6% interval | 95% interval | Label |
|---|---|---|---|---|---|---|
| G1 goal level | half-life 60 days, by competition, 100 pseudo-matches | mean log loss, five goal markets | **−0.00062** | −0.00104 to −0.00020 | −0.00090 to −0.00034 | a real gain below the bar |
| G2 league home | half-life 730 days, 300 pseudo-matches | result log loss | −0.00024 | −0.00065 to +0.00024 | −0.00053 to +0.00007 | no gain shown |
| G3 low score | nothing chosen | exact-score log loss | not scored | | | development chose no term |
| G4 bivariate | nothing chosen | exact-score log loss | not scored | | | development chose no term |

## G1: the goal level

| Condition | |
|---|---|
| Primary better by 0.002 | **No** (−0.00062) |
| 99.6% interval excludes zero | Yes |
| Better in 2024/25 and 2025/26 | Yes (−0.00068, −0.00062; −0.00041 in 2026/27 so far) |
| Result log loss not worse by 0.0005 | Yes (it improves by 0.00011) |
| 60% of competitions no worse | Yes (38 of 62, 61%) |

By market:

| Over 1.5 | Over 2.5 | Over 3.5 | Over 4.5 | Both teams score |
|---|---|---|---|---|
| −0.00061 | −0.00031 | −0.00112 | −0.00073 | −0.00035 |

Total goals a match, by season:

| Season | Actual | Production | With G1 |
|---|---|---|---|
| 2024/25 | 2.729 | 2.821 | 2.742 |
| 2025/26 | 2.777 | 2.828 | 2.788 |
| 2026/27 to 11 October | 2.926 | 2.890 | 2.870 |

- The development figure (−0.00064) was reproduced on the final period (−0.00062).
- It does what it was meant to in the two full seasons: the 0.09 and 0.05 goal overshoot falls
  to 0.01. In the opening weeks of 2026/27, when scoring jumped, it is no nearer than production,
  which is what a 60-day memory at the turn of a season would be expected to do.
- On development the gain came from the by-competition part (the overall figure alone was worth
  −0.0002). The audit found that a league's goal error does not carry from one season to the
  next. Both can be true: the error carries from one month to the next within a season, which a
  60-day half-life uses and a season-to-season comparison does not see.
- The largest gains are at 3.5 and 4.5, the lines the audit found leaning to overs.

## G2: home advantage by competition

Not shown to help. The change is −0.00024 with an interval that reaches +0.00024, fewer than
half the competitions are no worse (28 of 62), and the development gain (−0.00039) shrank on
the final period. By season: −0.00008, −0.00047, +0.00002. The overall correction alone (about
0.02 goals off every home side) was slightly worse than production on development.

The audit's finding stands as a description: a few leagues have a home advantage that differs
from the standard figure. It is too weak and too unstable to predict with.

## G3 and G4: low scores

Neither form found anything on development, so neither was scored on the final period.

| Dixon-Coles rho | −0.10 | −0.06 | −0.04 | −0.02 | 0 | +0.02 | +0.04 |
|---|---|---|---|---|---|---|---|
| Exact-score log loss change (draw boost 1.06) | +0.0033 | +0.0012 | +0.0005 | +0.0000 | −0.0002 | −0.0001 | +0.0003 |

| Bivariate shared share | 0 | 0.02 | 0.04 | 0.06 | 0.10 |
|---|---|---|---|---|---|
| Exact-score log loss change (draw boost 1.06) | −0.0002 | +0.0002 | +0.0008 | +0.0017 | +0.0042 |

- The standard Dixon-Coles term (negative rho) raises 0-0 and 1-1 and lowers 1-0 and 0-1. The
  audit found 0-0 **and** 1-0 both more common than predicted, so the shape is wrong for this
  model: what it gains at 0-0 it loses at 1-0.
- A bivariate Poisson adds draws at every score. The audit had already said a positive
  correlation was not indicated, and this confirms it.
- Both grids preferred a draw boost of 1.06 to production's 1.10, worth −0.00015. That is the
  `ends_and_draws` H2 result again, already tested and rejected, and is not taken forward.

## Computational cost

Seconds. Each running figure is one pass over the fixtures.

## Limits

- The final period is where these hypotheses came from (`DESIGN.md`).
- G1 keeps production's goal-line calibration, fitted on 2023/24. A calibration refitted on a
  rolling window was not tested and might add to it or overlap with it.
- G1's chosen setting is at the fast, lightly shrunk corner of its grid. The grid was not
  extended.
- Reconstructions throughout.

## Leads, not tested

- **G1 with the rating changes** (`experiments/rating_dynamics` R5) as one release candidate.
  They act on different things, the total and the margin, so their gains should add.
- **Low scores as a low-total excess.** The data wants more 0-0 and 1-0, which is fewer goals
  in tight games, not dependence between the two sides. A total-goals distribution slightly
  narrower than Poisson at low totals is the form to try, if this is pursued at all. It matters
  for under 1.5 and correct scores only.
