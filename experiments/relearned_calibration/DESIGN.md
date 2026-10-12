# Relearned calibration, and the formula candidates P14 tracks

**Written 2026-10-12, with the development stage run and nothing scored after 30 June 2024.**
An offline experiment with no `final` stage. Production stays as it is and nothing is deployed
whatever it finds. The shared periods, measures and intervals are in
`experiments/research_frame/REGISTER.md`.

## Why

The October research round left three improvements worth following, and one prospective
protocol (P13) that follows only part of them:

| Improvement | Tested in | Followed by P13? |
|---|---|---|
| Shot figures where there is no xG | `architectures` (the trees' ablation), `shots_proxy` | As the secondary candidate, a formula |
| A calibration of the margin and the goal total that is relearned as it goes | Only inside the boosted trees; the goal level alone in `goals_home_scores` | Only inside the trees |
| Clubs changing division, and new clubs | `rating_dynamics` | No |

This experiment builds the second as a candidate of its own, puts the three together, and
fixes every setting on matches up to June 2024, so that protocol P14 can follow each of them
on matches no one has seen. The period from July 2024 has been scored fourteen times already
(`REGISTER.md`) and is not scored again here.

## Candidates

All are corrections to production's projected goals, followed by production's probability
step, so a correction of zero is production. `run.py` holds each as a function that P14 calls.

| Name | What it does | Settings, and where they were fixed |
|---|---|---|
| `formula` | The margin error regressed on five differences between the two sides' last-ten figures: xG difference, shot difference, on-target difference, in-box shot difference, goals minus xG. Ridge penalty 50, a missing figure counts as zero. | P13's secondary candidate, unchanged |
| `calibration` | The goal total follows recent scoring, overall and by competition. A curve relearning the margin's error from the margin itself was to be added if it helped. | Goal level: half-life 60 days, 100 matches of shrinkage (`goals_home_scores/chosen.json`). Curve: chosen here |
| `movers` | A club changing division is moved halfway to its new division's average on arrival, and a club with little history moves faster. | `pull` 0.5, `boost` 0.5, `tau` 40 (`rating_dynamics/chosen.json`, the combined setting) |
| `combined` | The three in turn: `movers`, then the formula fitted on what is left, then the calibration fitted on what is left of that. | Nothing new |

The regressions are refitted every 1 January and 1 July on scored matches before that date. The
goal level and the ranks learn from earlier days only.

## What development chose

Selection window 2022-07-01 to 2024-06-30, 38,922 matches, production 0.99752.

**The margin curve was not chosen.** Twenty-four settings were tried (two or four years of
matches or all of them, three penalties, straight or curved, with or without a term for cups).
The rule, fixed in `run.py` before the grid ran, was that the best must improve the result log
loss by 0.0002 over the goal level alone. The best improved it by 0.00007. So `calibration` is
the goal level by itself.

This agrees with `experiments/ends_and_draws`: the flat ends the audit found are absent before
2024, so nothing fitted on these years can see them. If they persist, a formula of this kind
would need choosing on later matches, which P14's result would be the first clean look at.

| Candidate | Result log loss | Brier | Goal markets | 2021/22 | 2022/23 | 2023/24 |
|---|---|---|---|---|---|---|
| `formula` | −0.00245 | −0.00164 | −0.00003 | −0.0037 | −0.0029 | −0.0020 |
| `calibration` | −0.00013 | −0.00006 | −0.00064 | −0.0002 | −0.0000 | −0.0002 |
| `movers` | −0.00090 | −0.00064 | −0.00009 | −0.0006 | −0.0011 | −0.0007 |
| `combined` | **−0.00347** | −0.00235 | −0.00083 | −0.0043 | −0.0040 | −0.0030 |

Against production on the same matches; negative is better. 2021/22 is from January 2022, the
first refit.

- `formula` reproduces P13's registered development figure (−0.00245) exactly.
- The three add up: `combined` is within 0.0001 of their sum.
- These are figures on the years the settings were chosen on. `movers` and the trees each kept
  nearly nine tenths of their development gain on later matches; the formula has never been scored
  there.

**One exploratory check, development only, not a candidate.** Whether the model's own recent
errors predict its next one was tried as a formula (each side's mean error over its last 5 and
10 matches, its current rank against its long-term rank, its error at home or away). The best
was worth 0.0002 alone and nothing on top of the shot formula. So what the boosted trees gain
in competitions with no shot data is not recovered by a formula of this kind, and the trees
stay in P14 as the reference for it.

## What is not done here

- No candidate is scored on a match after 30 June 2024.
- Nothing is compared with the bookmakers, and no bet is simulated. Both are P14's.
- No production file is changed.

## Planning figures for P14

`combined`'s paired difference from production has a week-clustered standard deviation of 0.078
a fixture on the selection window. P14 plans for four fifths of its gain there (0.0028).

## Files

`run.py develop` rebuilds `chosen.json` from `experiments/research_frame/inputs.json.gz` in
about a minute. P14 pins `run.py` and `chosen.json` by hash: a changed file is a different
candidate.
