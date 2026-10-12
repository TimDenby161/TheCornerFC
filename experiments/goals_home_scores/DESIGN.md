# Goals, home advantage and scorelines: the remaining single hypotheses

**Registered 2026-10-12, after the development stage and before `run.py final` was run.** An
offline experiment. Production stays as it is and nothing is deployed whatever it finds. Shared
rules, periods, intervals and the bar are in `experiments/research_frame/REGISTER.md`.

These are items 3, 4 and 5 of the 12 October audit's list, kept apart from the larger
experiments on the rank and on other architectures. Each acts on production's projected goals
for a match and nothing upstream of them.

## What was already seen

The audit's diagnostics on July 2024 to September 2026, which is most of the final period here:
the projected total stayed near 2.82 while the real figure moved between 2.73 and 2.93; home
advantage is predicted about 0.02 goals too high, and 10 of 61 leagues are off by more than two
standard errors with weak persistence (correlation 0.25); 0-0 happens 9% more often than
independent Poisson says and 1-0 5% more. So the final period is where these hypotheses came
from. The settings are chosen on development only, and the forms are ones that learn as they
go, with no number fitted to the final period.

## Hypotheses

**G1, goal level.** The projected total of a match is multiplied by 1 + e, where e is the running
excess of actual over projected goals in matches on earlier days: a decayed sum (half-life 60,
120, 240 or 480 days) over all competitions, starting from 2,000 matches of "no excess", and
optionally by competition with 100 or 300 pseudo-matches at the overall figure. The expected
margin is kept. Production's goal-line calibration is applied unchanged.
*Primary:* mean log loss over the five goal markets. *Guard:* result log loss.

**G2, league home advantage.** The expected margin is moved by the competition's running
home-side residual, in goals, from matches on earlier days: a decayed mean (half-life 180, 365
or 730 days) by competition with 100, 300 or 1,000 pseudo-matches at the overall figure, or the
overall figure alone. *Primary:* result log loss. *Guard:* the five goal markets.

**G3, low score.** A Dixon-Coles term on the score grid: 0-0 and 1-1 multiplied up and 1-0 and
0-1 down for negative rho, the other way for positive. Rho from −0.16 to +0.06; the draw boost
refitted alongside (1.00 to 1.10). *Primary:* log loss of the exact regulation score.
*Guards:* result log loss and the five goal markets.

**G4, bivariate.** A bivariate Poisson score grid: a shared goal component of `share` ×
min(home, away) goals with both sides' means kept. Share from 0 to 0.20; the draw boost refitted
alongside. Same primary and guards as G3.

For G3 and G4 the baseline score grid is production's independent Poisson grid with its diagonal
raised by the draw boost, so that it sums to production's result probabilities.

A candidate whose best setting improves the selection window by less than 0.0001 on its primary
is **nothing chosen** and is not scored on the final period. For G3 and G4 the hypothesis is the
structural term: a best setting with rho or share at zero is the draw boost alone, which
`experiments/ends_and_draws` already tested and rejected, so that too is nothing chosen.

## What development chose

Selection window 2022-07-01 to 2024-06-30, 38,922 matches.

| | Chosen | Change on its primary | Note |
|---|---|---|---|
| G1 goal level | half-life 60 days, by competition with 100 pseudo-matches | −0.00064 | The overall figure alone gives −0.0002 at best. The gain is in the by-competition part, and the fastest, least-shrunk corner of the grid is the best one. |
| G2 league home | half-life 730 days, 300 pseudo-matches | −0.00039 | The overall figure alone is slightly worse than production (+0.00005). |
| G3 low score | **nothing** | rho 0 is best | Every negative rho is worse (−0.04: +0.0005; −0.10: +0.0033). The standard Dixon-Coles shape lowers 1-0 and 0-1, which the data wants raised. |
| G4 bivariate | **nothing** | share 0 is best | Any shared component is worse (0.04: +0.0008; 0.10: +0.0042). It adds draws at every score, where the excess is at the low scores only. |

The refitted draw boost that both G3 and G4 found (1.06 in place of 1.10, −0.00015) is the
`ends_and_draws` H2 result again and is not taken forward.

G1 and G2 go to the final period. G3 and G4 do not.

## What this cannot show

Anything against the bookmakers, or a prospective record. And that the audit's low-score
finding is wrong: it says only that these two standard forms are not the fix.

## Running it

```bash
python experiments/goals_home_scores/run.py develop
python experiments/goals_home_scores/run.py final
```

---

Evaluator as registered, before the final stage was run (2026-10-12):

- `run.py` SHA-256 `002490ff967636765db2fda0982d47911cfdab43583d82414d62c571d05d5e68`
- `chosen.json` SHA-256 `7845718dd6d1deb1a3dde24d404477f7f3368565b34d9907069d3d49ebc18b98`
