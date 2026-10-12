# Shots as a stand-in for xG

**Registered 2026-10-12, after the development stage and before `run.py final` was run.** An
offline experiment. Production stays as it is and nothing is deployed whatever it finds. The
periods, measures, intervals and the bar are those of `experiments/research_frame/REGISTER.md`.

## Why

- xG is the most valuable single input the model has: taking it away costs 0.0063 of log loss on
  the matches that have it (`experiments/results_only/REPORT.md`).
- Only 23% of fixtures have xG (none before 2022/23, 35 to 52% a season since). Another 40%
  have shot counts and no xG. They move the rank on the goal difference alone, at K 6.
- The site already estimates xG from shots for its club pages (`XG_FROM_SHOTS`, R² 0.62). The
  model does not use it.

## What was already seen

This is the fourteenth comparison of the round, added after the first thirteen were scored. The
lead came from an exploratory comparison with bookmaker prices (not published, and nothing in
it is a test) on about 1,100 matches from 16 September to 11 October 2026, inside the final
period: the model was much further behind the prices in leagues without xG than in leagues
with it, and the prices' disagreement with the model followed each side's recent shot
difference more closely than anything else tried. So the hypothesis came from 2.5% of the final
period. Nothing below was fitted to it.

## Hypothesis

**S, shots.** In a match with no xG and with shot counts for both sides, the rank moves on
`goals_weight` × the capped goal difference + (1 − `goals_weight`) × the estimated xG
difference, with step `k`. Matches with xG, and matches with neither, are as in production.

The estimate is a least-squares fit of a side's xG on its shots inside the box, outside the box
and on target, over development matches that have both (kickoffs before 2024-07-01). Blocked
shots, which the site's own fit uses, are not in the research inputs.

Grid: `goals_weight` 0.3, 0.5, 0.7; `k` 6, 7, 8, 9, 10. Chosen by the lowest log loss on the
selection window, 2022-07-01 to 2024-06-30.

As in `experiments/rating_dynamics`, only the rank term of each stored projection is swapped.
Production also uses xG in the twelve-month goal averages and the attack/defence split; those
are not re-learned here, so this measures the rank's share of what the estimate could give.

## What development chose

The estimate, from 8,210 matches: 0.108 a shot inside the box − 0.005 a shot outside + 0.109 a
shot on target + 0.028. R² 0.61. Close to the site's own figures.

Selection window, 38,922 matches: 21% have xG, 41% shots and no xG, 38% neither.

| goals weight \ K | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|
| 0.3 | −0.00046 | −0.00085 | −0.00111 | −0.00129 | −0.00140 |
| 0.5 | −0.00085 | −0.00117 | −0.00138 | −0.00149 | **−0.00153** |
| 0.7 | −0.00081 | −0.00103 | −0.00112 | −0.00111 | −0.00103 |

- **Chosen: goals weight 0.5, K 10.** K is at the edge of its grid, which is production's K for
  real xG; the grid is not extended.
- On the matches it changes directly (shots, no xG) the gain is −0.0037. On the others it is
  +0.0001 and −0.0001.
- By season: −0.0034 (2021/22, outside the selection window), −0.0025 (2022/23), −0.0006
  (2023/24). **The gain falls sharply as real xG arrives.** The final period has more xG still,
  so the development figure is likely to overstate what the final period shows.

## Final stage

`run.py final` scores S once on 2024-07-01 to 2026-10-11 against replayed production, with the
interval at 1 − 0.05 / 14 and the bar of the register. It also prints, as description only and
not as a registered comparison, S stacked on the `rating_dynamics` combined setting: that
setting's own final result was already known, so a stack chosen now is chosen with hindsight.

## What this cannot show

Anything against the bookmakers, a prospective record, or what a full production replay would
give with the estimate in the goal averages and the split as well.

## Running it

```bash
python experiments/shots_proxy/run.py develop
python experiments/shots_proxy/run.py final
```

---

Evaluator as registered, before the final stage was run (2026-10-12):

- `run.py` SHA-256 `c1d96bd6878fda803bc7eed6cb6c7ef34c2d927d89a7eac1889036e10ec378bc`
- `chosen.json` SHA-256 `2b3db2eec481ad7b0193aa3f4915bb1c5e0f1a2de53edc0ed7b51426f9f7114d`
