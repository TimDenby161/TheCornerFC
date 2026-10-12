# Level gaps: results

Run on 2026-10-12 with the evaluator registered in `DESIGN.md` (`run.py` SHA-256
`8393afd0…85e157`, unchanged between registration and the run). Inputs read once from production
through the read-only role. Nothing was deployed and no stored prediction was changed.

## Verdict

**No candidate meets either bar. The ranking replay is not supported.**

| Candidate | Chosen on 2023/24 | Changed matches, test | Test log loss on them (95%) | Holdout log loss on them (95%) | Bar A | Bar B |
|---|---|---|---|---|---|---|
| H3, gaps between leagues | β = 0.10 | 2,195 | −0.0041 (−0.0069 to −0.0013) | **+0.0067 (+0.0029 to +0.0110)** | No | No |
| H4, sides with no league | δ = 25 points | 1,078 | −0.0074 (−0.0152 to +0.0003) | −0.0002 (−0.0099 to +0.0092) | No | No |
| Both | β = 0.10, δ = 25 | 3,273 | −0.0052 (−0.0084 to −0.0022) | **+0.0045 (+0.0001 to +0.0086)** | No | No |

Negative is better. Over all 44,383 test matches the three are worth −0.0002, −0.0002 and
−0.0004, against a bar of −0.002.

**The finding that matters is the sign change.** Widening the gaps between leagues helps from
2024 and hurts before 2023, and both intervals exclude zero. The gaps are not too small or too
large by a fixed amount: the error moves over time.

## Inputs

121,918 finished fixtures from February 2020. Scored matches, by kind:

| Period | Scored | Cross-league | One-sided | Unchanged |
|---|---|---|---|---|
| Holdout, 2021-07-01 to 2023-06-30 | 38,753 | 1,588 | 763 | 36,402 |
| Validation, 2023-07-01 to 2024-06-30 | 19,239 | 833 | 384 | 18,022 |
| Test, 2024-07-01 to 2026-10-11 | 44,383 | 2,195 | 1,078 | 41,110 |

About 7% of matches are changed by either hypothesis.

## What validation chose

| β | −0.10 | −0.05 | 0 | 0.05 | **0.10** | 0.15 | 0.20 | 0.30 | 0.50 |
|---|---|---|---|---|---|---|---|---|---|
| Log loss, 833 matches | 0.90305 | 0.89953 | 0.89719 | 0.89598 | **0.89582** | 0.89666 | 0.89847 | 0.90477 | 0.92693 |

| δ | −50 | −25 | 0 | **25** | 50 | 75 | 100 | 200 |
|---|---|---|---|---|---|---|---|---|
| Log loss, 384 matches | 0.87256 | 0.84535 | 0.83117 | **0.82984** | 0.84079 | 0.86296 | 0.89549 | 1.10789 |

Neither is at the edge of its grid. Both gains on validation itself are inside the noise
(−0.0014 with an interval of about ±0.005 for β, ±0.012 for δ).

## H3: the gaps between leagues

The cleanest measure is the goal-difference error towards the side from the higher league:
positive means that side did better than the model expected.

| Period | Matches | Baseline error (95%) | With β = 0.10 | Log loss change (95%) |
|---|---|---|---|---|
| Holdout | 1,588 | **−0.167 (−0.252 to −0.075)** | −0.293 | +0.0067 (+0.0029 to +0.0110) |
| Validation | 833 | +0.102 (−0.023 to +0.218) | −0.022 | −0.0014 (−0.0060 to +0.0040) |
| Test | 2,195 | **+0.100 (+0.026 to +0.176)** | −0.022 | −0.0041 (−0.0069 to −0.0013) |

- In 2021 to 2023 the higher-league side did 0.17 goals **worse** than predicted. From 2023 it
  did 0.10 **better**. The correction that fits one period is wrong for the other.
- By season: +0.0086 and +0.0048 (holdout), −0.0014 (validation), −0.0048, −0.0013 and −0.0103
  (test, the last on 333 matches).
- By competition, log-loss change on the changed matches:

| | Holdout | Test |
|---|---|---|
| Conference League | +0.0011 (518) | +0.0013 (574) |
| Europa League | +0.0091 (315) | −0.0064 (548) |
| Champions League | +0.0054 (339) | −0.0040 (540) |
| FA Cup | +0.0295 (185) | −0.0066 (174) |
| League Cup | | −0.0222 (132) |

- Against Bar B it fails three conditions: the ends gap falls 14% with an interval from −31% to
  +36%; the holdout is worse, not better; and over 3.5 and over 4.5 goals are worse by 0.0011 and
  0.0013 on the changed matches, outside the guard.

## H4: sides with no league in the data

Goal-difference error towards the side that has a league:

| Period | Matches | Baseline error (95%) | With δ = 25 | Log loss change (95%) |
|---|---|---|---|---|
| Holdout | 763 | +0.092 (−0.047 to +0.251) | −0.158 | −0.0002 (−0.0099 to +0.0092) |
| Validation | 384 | +0.071 (−0.087 to +0.250) | −0.179 | −0.0013 (−0.0141 to +0.0109) |
| Test | 1,078 | **+0.270 (+0.150 to +0.395)** | +0.020 | −0.0074 (−0.0152 to +0.0003) |

- The direction is the same in all three periods: sides with no league are rated too high. Only
  the test period's error is clear of zero, and it is three times the size of the other two.
- A 25-point correction fits the test period and overshoots the other two.
- No log-loss interval excludes zero. Brier on test does (−0.0060, −0.0113 to −0.0008).
- By competition on test: EFL Trophy −0.034 (101), Scottish League Cup −0.016 (135), Conference
  League −0.005 (321), FA Cup +0.002 (257). On the holdout the Conference League and the FA Cup
  are both worse (+0.010 and +0.008).
- It fails four Bar B conditions: log loss, the ends gap (which gets worse), the holdout, and
  the goal-market guard (over 1.5 is worse by 0.0011 on the changed matches).

## What this shows

- The cup effect found in `ends_and_draws` is real and is not a constant. In cross-league ties
  the model's error reversed between 2021 to 2023 and 2024 to 2026.
- A fixed respacing of the starting ranks would trade one period's error for the other's. That is
  what `ends_and_draws` saw from the other side: a gain from 2024 and nothing before.
- Sides with no league look overrated throughout, by an amount that is too uncertain to set.

## Leads, not tested

- **Do the gaps between leagues drift as the replay runs?** The sign change says they do. The
  direct check is to track each league's average rank season by season against how its clubs do
  in cross-league matches. If the gaps close over time, the cause is in how rank moves between
  leagues (promotion, relegation, the few cross-league matches), and the fix is there.
- **A lower starting rank for cup-only clubs** is the one direction that agreed across all three
  periods. It needs the ranking replay to test properly, and this experiment's evidence for it is
  not strong enough to register one on its own.

## Limits

- 7% of matches are changed, so intervals on them are wide: about ±0.003 for H3 and ±0.008 for H4.
- β and δ are stand-ins for a ranking change, applied to the stored margin without replaying ranks.
- A side's league comes from the fixtures in the data. A club from an uncovered league counts as
  having none.
- Every row but 725 is a reconstruction. Intervals are pointwise.
