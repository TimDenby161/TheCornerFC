# Rating dynamics: is the club rank structurally holding the predictions back?

**Registered 2026-10-12, after the development stage and before `run.py final` was run.** An
offline experiment. Production formulas, stored predictions and database records stay as they
are, and nothing is deployed whatever it finds. Shared rules, periods, measures and the bar are
in `experiments/research_frame/REGISTER.md`; this file has what is particular to this experiment.

It follows `experiments/level_gaps`, whose lead was that the model's error in ties between
leagues changed sign between 2021 to 2023 and 2024 to 2026: the levels of the leagues move.

## How the rank works, and where it could be wrong

The club rank (`thecornerfc/models/ranking.py`) is zero-sum inside a match: what one side gains
the other loses, by K 6 per goal of surprise (K 10 on the xG blend). So:

- a league's average can only move through matches against clubs outside it and through clubs
  joining and leaving;
- a club that changes division carries its rank with it unchanged;
- a club with five matches behind it moves at the same speed as one with five hundred;
- every club's first rank is a figure set by hand for its league in February 2020.

## What the development period showed (`diagnose.py`, `diagnose_flow.py`)

Development only, 57,992 matches. No error in the final period was read.

| Finding | Evidence |
|---|---|
| League levels converge slowly from their hand-set starts | The Premier League's average rank fell from 1,150 to 1,026 over four seasons, losing 20 to 25 points a club each season in European and cup ties. Scotland's rose from 706 to 750 the same way. |
| The level errors were fading by 2023/24 | A league's fitted error in cross-league ties predicted the next season's in 2021/22 to 2022/23 (slope 0.39, standard error 0.16) and not in 2022/23 to 2023/24 (−0.07, 0.21). |
| The higher-league side's error changed sign inside development | −0.22 goals (2021/22), −0.12 (2022/23), +0.10 (2023/24), each about ±0.06. |
| **Clubs that come down a division are overrated** | −0.47 goals a match against the prediction in their first five league matches (±0.08), −0.35 in the next five, −0.18 in matches 11 to 20, −0.06 after. Outside England's top two levels: −0.52, −0.41 and −0.35 in the three seasons, each ±0.10. |
| Clubs that come up are slightly underrated | +0.17 (±0.08) in the first five, +0.14 (±0.06) in matches 11 to 20. Weaker and less even. |
| The rank under-reacts where there is no xG | A side's mean error over its last five matches predicts its next (slope 0.050 ± 0.008) in leagues without xG, and not in leagues with it (0.00 ± 0.02). Larger in August and September (0.075 ± 0.018). |
| Clubs with little history are predicted too flat | Sharpness power 1.22 where a side has under 10 matches, 1.10 at 10 to 30, about 1.05 after. |
| No sign that cup results mislead the rank | A side's error in a cup tie predicts its next league match no worse than a league match does. |
| No case for pulling ranks to the league average each summer | Slope 0.02 ± 0.02 over 2,870 club-seasons. |
| No points pump from minnows | Covered leagues gain under 0.2 points a club a season from clubs with no league. |

## Hypotheses

Each is a change to the replay. All four start from production's settings.

**R1, levels.** Each league has a level, shared by all its clubs, that moves by `league_k` points
per goal of surprise whenever two clubs from different leagues meet (cups and European ties).
A club's effective rank is its own plus its league's level. A club that changes league keeps its
effective rank. This is the direct answer to slow level convergence.
Grid: `league_k` 0.25, 0.5, 1, 1.5, 2, 3, 4.

**R2, movers.** When a club plays its first league match in a different division of the same
country, its rank (and its history, so the long-term rank moves with it) is moved once. Two forms:
`pull`, a fraction of the way to the average rank of the clubs now in that division (0.1 to
0.6); or `shift`, a fixed number of points down for a club that came down (0 to 60) and up for
one that came up (0 to 30).

**R3, uncertainty.** A club's step is multiplied by 1 + `boost` × exp(−matches played / `tau`).
With `damp`, its opponent's step is divided by the same factor, so a result against a club the
model knows little about moves the established club less. With `reset`, a club that changes
division has its matches-played count cut to 10. Grid: boost 0.5, 1, 2, 3; tau 10, 20, 40; damp
off, on; reset off, on.

**R4, reaction.** K for matches without xG (5 to 10) and with it (8 to 14).

**R5, combined.** The chosen settings of R1 to R4 together, then one sweep that re-chooses each
part's setting on its own grid with the other parts in place.

A part whose best setting improves the selection window by less than 0.0002 is recorded as
**nothing chosen** and is not scored on the final period.

## How a changed rank becomes a prediction

The stored projection of each match is kept, and only the rank term of its expected margin is
swapped for the replayed one. Injuries, line-ups, home edges and the European bonus stay as
stored, and the projected goals are re-solved the way `predictions.project` solves them. The
attack/defence split and the home edges were themselves learned alongside the original ranks and
are not re-learned here, so this slightly understates what a full production replay would do
with a better rank. A candidate that meets the bar would need that full replay before a release.

## What development chose

Selection window 2022-07-01 to 2024-06-30, 38,922 matches, production 0.99752.

| Part | Chosen | Selection log loss change | Note |
|---|---|---|---|
| R1 levels | **nothing** | every setting worse: +0.00004 at 0.25 rising to +0.00080 at 4 | A league's results in Europe and the cups are its best few clubs' results. Sharing them with the whole league misplaces the rest. |
| R2 movers | pull 0.5 | −0.00070 | A smooth curve from 0.1 (−0.00021) to 0.5; 0.6 is the same. The best fixed shift (30 down, 15 up) gives −0.00033. |
| R3 uncertainty | boost 1, tau 10, no damping, reset on | −0.00026 | Damping the opponent's step made it worse at every setting. |
| R4 reaction | **nothing** | best −0.00012 at K 7 / 10 | Under the 0.0002 threshold. K 6 / 10 is close to the best there is. |
| R5 combined | pull 0.5, boost 0.5, tau 40 | −0.00090 | The sweep kept K at 6 / 10 and the levels off. |

By season for the chosen settings (2021/22 is outside the selection window): movers −0.00145,
−0.00095, −0.00044; uncertainty −0.00119, −0.00022, −0.00030. Both are largest in the season
nearest the cold start.

So before the final period is opened: **the development gains are a third to a half of the
0.002 bar.** R2, R3 and R5 go to the final period. R1 and R4 do not.

## Final stage

`run.py final` scores R2, R3 and R5 once on 2024-07-01 to 2026-10-11 against replayed
production, with the measures, the 99.6% intervals and the bar of the register. The guard is
the five goal markets, which move with the projected goals.

## What this cannot show

- Anything against the bookmakers. No odds are read.
- That a production replay with the change would score the same: the split and the home edges
  are not re-learned (above).
- A prospective record.

## Running it

```bash
python experiments/rating_dynamics/diagnose.py        # the diagnostics above
python experiments/rating_dynamics/diagnose_flow.py
python experiments/rating_dynamics/run.py develop     # writes chosen.json
python experiments/rating_dynamics/run.py final       # writes results.json
```

No database is read: the inputs are `experiments/research_frame/inputs.json.gz`. Needs numpy.

---

Evaluator as registered, before the final stage was run (2026-10-12):

- `run.py` SHA-256 `b06d25bf6f32a54aa1ab09cb3fa3021d189973f9bb84f033b94366db0671c8b7`
- `chosen.json` SHA-256 `83bac50319f1289218105488296c45f75380d646938ca7009c90e6d59d6d0112`
- `experiments/research_frame/frame.py` SHA-256 `dd5a3e1e2973f0574234e8d120b1a9c99187bb1b999a11eaca250fd698671fba`
