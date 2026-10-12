# Rating dynamics: results

Run on 2026-10-12 with the evaluator registered in `DESIGN.md` (`run.py` SHA-256
`b06d25bf…0671c8b7`, `chosen.json` `83bac503…59d6d0112`, both unchanged between registration
and the final stage). Inputs: the research frame, read once from production through the
read-only role. Nothing was deployed and no stored prediction was changed.

## Verdict

**No candidate meets the bar. Three are real gains below it. No change to production is
supported by this experiment alone.**

Final period, 2024-07-01 to 2026-10-11, 44,383 matches, 119 weeks. Replayed production scores
0.99360. Negative is better. The bar is −0.002.

| Candidate | Setting chosen on development | Log loss change | 99.6% interval (13 comparisons) | 95% interval | Label |
|---|---|---|---|---|---|
| R1 levels | nothing chosen | not scored | | | development made it worse |
| R2 movers | pull 0.5 | −0.00055 | −0.00107 to −0.00007 | −0.00089 to −0.00020 | a real gain below the bar |
| R3 uncertainty | boost 1, tau 10, reset on | −0.00037 | −0.00067 to −0.00007 | −0.00058 to −0.00018 | a real gain below the bar |
| R4 reaction | nothing chosen | not scored | | | under the selection threshold |
| R5 combined | pull 0.5, boost 0.5, tau 40 | **−0.00079** | −0.00138 to −0.00022 | −0.00117 to −0.00038 | a real gain below the bar |

Three things to take from it:

1. **The gains are real and hold out of sample.** All three intervals exclude zero after the
   correction for thirteen comparisons. The development figures (−0.00070, −0.00026, −0.00090)
   were reproduced closely on matches the settings never saw (−0.00055, −0.00037, −0.00079).
2. **They are small.** The best is 40% of the bar. The club rank is not what is holding the
   predictions back by any large amount.
3. **The leading idea from the last experiment, learning league levels, does not work in its
   direct form.** It made development worse at every strength.

## Against the bar

| Condition | R2 movers | R3 uncertainty | R5 combined |
|---|---|---|---|
| Log loss better by 0.002 | **No** | **No** | **No** |
| 99.6% interval excludes zero | Yes | Yes | Yes |
| Brier agrees | Yes (−0.00037) | Yes (−0.00027) | Yes (−0.00054) |
| Better in 2024/25 and 2025/26 | Yes | Yes | Yes |
| No goal market worse by 0.0005 | Yes (all within 0.0001) | Yes | Yes |
| 60% of competitions no worse | Yes (45 of 62) | **No** (32 of 62) | Yes (42 of 62) |

## By season

Log-loss change, candidate minus replayed production.

| Season | Matches | Role | R2 movers | R3 uncertainty | R5 combined |
|---|---|---|---|---|---|
| 2021/22 | 19,070 | development, before the selection window | −0.00145 | −0.00119 | −0.00228 |
| 2022/23 | 19,683 | settings chosen here | −0.00095 | −0.00022 | −0.00112 |
| 2023/24 | 19,239 | settings chosen here | −0.00044 | −0.00030 | −0.00068 |
| 2024/25 | 19,662 | final | −0.00014 | −0.00038 | −0.00040 |
| 2025/26 | 19,515 | final | −0.00059 | −0.00049 | −0.00085 |
| 2026/27 to 11 October | 5,206 | final | −0.00192 | +0.00014 | −0.00200 |

The large 2021/22 figures are the cold start: ranks were 17 months from their hand-set values,
and both changes help a rank that is wrong to correct itself. That is why the selection window
leaves that season out. The movers' gain is largest early in a season (the 2026/27 figure is
August to mid-October only), which is when clubs that changed division are playing their first
matches there.

## Leagues, cups and competitions

| | Matches | R2 movers | R3 uncertainty | R5 combined |
|---|---|---|---|---|
| Leagues | 38,538 | −0.00054 | −0.00025 | −0.00069 |
| Cups | 5,845 | −0.00061 | −0.00119 | −0.00144 |

Under R5, by competition (300 or more final matches; one figure each, no interval):

| Most improved | Matches | Change | | Most worsened | Matches | Change |
|---|---|---|---|---|---|---|
| Serie B | 839 | −0.0074 | | League One | 1,215 | +0.0025 |
| Ligue 2 | 689 | −0.0059 | | Bundesliga | 660 | +0.0017 |
| Segunda División | 1,030 | −0.0054 | | National League North | 1,241 | +0.0016 |
| Gibraltar Premier Division | 300 | −0.0043 | | National League | 1,262 | +0.0013 |
| FA Trophy | 690 | −0.0039 | | Ekstraklasa | 698 | +0.0012 |
| Premier League | 819 | −0.0038 | | Slovenia 1. SNL | 399 | +0.0006 |

| | Premier League | La Liga | Serie A | Bundesliga | Ligue 1 | Championship | League One | League Two |
|---|---|---|---|---|---|---|---|---|
| R5 | −0.0038 | +0.0004 | −0.0012 | +0.0017 | −0.0010 | −0.0002 | +0.0025 | −0.0011 |

The pattern makes sense for the movers' part: second divisions, which take clubs from above and
below every year, and the Premier League, which takes three promoted clubs, gain most. League
One getting worse is the exception and is not explained.

## Other measures, R5 against production

| | Production | R5 combined |
|---|---|---|
| Log loss | 0.99360 | 0.99281 |
| Brier | 0.59277 | 0.59223 |
| Ranked probability score | 0.20634 | 0.20611 |
| Top pick right | 51.58% | 51.59% |
| Calibration error | 0.0103 | 0.0107 |
| Sharpness power (1 is right; above 1 is too flat) | 1.10 | 1.11 |

Calibration does not improve: the ranks are better but the too-flat ends that
`experiments/ends_and_draws` measured are untouched, as expected.

## What each hypothesis showed

- **R1, league levels: rejected on development.** Sharing what a league's clubs do in Europe and
  the cups with every club in that league made the selection window worse, by more the faster
  the level moved. The clubs that play those ties are a league's best few, and their results
  say little about the other sixteen. The slow convergence of levels is real (`DESIGN.md`), but
  the levels had largely settled by 2023/24, and this is not the way to speed them up.
- **R2, movers: the clearest single finding.** A club arriving in a new division should be moved
  halfway to that division's average. It is consistent with the diagnostics (clubs that come
  down are overrated by nearly half a goal for their first five matches) and it held on the
  final period.
- **R3, uncertainty: small, and mostly a cup effect.** Letting clubs with little history move
  faster helps cups (−0.0012) four times as much as leagues, and helps fewer than 60% of
  competitions. Damping the established opponent's step, the part that would have made it a
  proper uncertainty model, made things worse.
- **R4, reaction: K is already about right.** The best alternative (K 7 without xG) was worth
  −0.00012 on development. The under-reaction in the diagnostics is real but too small to be
  worth a different K.

## Computational cost

One replay of all 121,918 fixtures takes about one second in plain Python. The development
stage (about 150 replays) took under ten minutes; the final stage under a minute. In production
the change would add nothing measurable to the nightly rank rebuild.

## Limits

- The final period had been looked at before this round (`REGISTER.md`). The settings were
  chosen without it, and the result reproduced, but it is not a blind test.
- Only the rank term of each stored projection is swapped. The attack/defence split and home
  edges are not re-learned from the changed ranks, and line-ups and injuries are as stored.
- Every row but 725 is a reconstruction.
- A club's division is taken from its league fixtures in the data. A club relegated out of the
  covered leagues is not seen arriving anywhere.

## Leads, not tested

- **R5 as one part of a larger release.** On its own it is 40% of the bar. With the goal-level
  result in `experiments/goals_home_scores` and whatever else is found, a combined candidate
  could be registered against the bar once, on a prospective record.
- **Why promoted and relegated clubs are misrated.** Squads change most on changing division, so
  squad strength at the start of a season is the natural thing to look at. `squad_forward` found
  little for clubs in general; it did not look at movers specifically.
- **League One.** Worse under every candidate here.
