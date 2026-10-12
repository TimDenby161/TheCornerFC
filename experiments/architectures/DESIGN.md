# Architectures: other ways of building the prediction

**Registered 2026-10-12, after the development stage and before `run.py final` was run.** An
offline experiment. Production stays as it is and nothing is deployed whatever it finds. Shared
rules, periods, intervals and the bar are in `experiments/research_frame/REGISTER.md`.

Production is an Elo-like club rank with an attack/defence split learned beside it, turned into
goals and then into independent Poisson probabilities. This asks whether a different kind of
model, or a different way of combining what is known before a match, does better.

## Candidates

**A1, `dc`: a hierarchical, time-weighted Poisson model, refitted every week.** The Dixon-Coles
family. Every club has its own attack and defence; every league has a level for each, which its
clubs are shrunk towards; every competition has its own goal level and home advantage, shrunk
towards the overall figures. One fit covers every competition at once, so cups and European
ties connect the leagues. Matches count less the older they are (a half-life in days). The
goals fitted are the regulation score, blended 30/70 with xG where there is xG, as production's
rank does. Every seven days the model is refitted on all matches before that day, and predicts
the next seven. A Dixon-Coles low-score term (rho) is fitted on top.

It uses results and xG only: no line-ups, injuries or player ranks. It stands for three of the
families asked about (Dixon-Coles, dynamic attack and defence, hierarchical league and club).
Bivariate Poisson is tested on production's own goals in `experiments/goals_home_scores`.

Settings, by coordinate search: club shrinkage 1, 3, 10, 25; half-life 250, 500, 1,000 days; xG
blend on or off; then rho from −0.20 to +0.10.

**A2, `gb`: gradient-boosted trees correcting production.** Two boosted regressions, one for the
expected margin's error and one for the expected total's, from pre-match features. Their
corrections are added to production's projected goals and the usual probability step follows,
so a correction of zero is production. Retrained every half-season on every scored match
before it. Features, each using only earlier matches (`research_frame/features.py`):

| Group | What |
|---|---|
| base | production's expected margin and total, the rank gap, matches played, league or cup, European tie, the league's starting rank, month |
| form | each side's mean error against the model over its last 5 and 10 matches, its total-goals error, its current rank against its long-term rank |
| shots and xG | over each side's last 10 matches with statistics: xG difference, goals minus xG, shot, on-target and in-box shot differences |
| schedule | days since each side's last match, its matches in the last 14 and 30 days |
| movers | whether each side changed division, which way, and its league matches since |
| manager | matches since each side's manager last changed, from earlier line-ups |
| injuries | the stored missing-player strength |
| venue | the home side's recent error at home, the away side's away |
| dc | A1's margin and total, against production's |

Settings: tree depth 2 or 3, 150 or 300 trees, and how much of the correction to apply (0.5,
0.75, 1). Learning rate 0.03, 200 matches a leaf, fixed.

**A3, `pool2`:** production and `dc` combined (log-linear pool, weights in steps of 0.1).

**A4, `pool3`:** production, `dc` and `gb` combined the same way.

## What development chose

Selection window 2022-07-01 to 2024-06-30, 38,922 matches. Production 0.99752. Base rates
1.06847.

| Candidate | Chosen | Selection log loss | Against production |
|---|---|---|---|
| A1 dc | club shrinkage 10, half-life 250 days, xG blend on, rho 0 | 1.00131 | **+0.00379 (worse)** |
| A2 gb | depth 3, 300 trees, full correction | 0.99432 | **−0.00320** |
| A3 pool2 | 0.7 production, 0.3 dc | 0.99686 | −0.00066 |
| A4 pool3 | 0.1 production, 0 dc, 0.9 gb | 0.99431 | −0.00321 |

- **`dc` is clearly worse than production by itself**, in each development season (1.0081,
  1.0035, 0.9990 against 1.0071, 1.0002, 0.9947). It still adds something in a pool.
- **The Dixon-Coles low-score term is not wanted here either:** rho 0 is the best value
  (−0.05: +0.0003; +0.05: +0.0004), as in `goals_home_scores`.
- **`gb` is the first candidate of the round to clear 0.002 on development.** What carries it,
  measured by refitting the chosen model without each group:

| Group left out | Selection log loss gets worse by |
|---|---|
| shots and xG | **0.00181** |
| dc | 0.00038 |
| movers | 0.00017 |
| manager | 0.00014 |
| schedule | 0.00007 |
| injuries | 0.00004 |
| venue | 0.00000 |
| form | −0.00016 (better without it) |

  More than half of its gain is each side's recent shots and xG. Rest days, congestion and
  home-and-away form carry nothing, as the audit found. This agrees with
  `experiments/shots_proxy`: the model is short of shot information in the matches that have no
  xG.
- `pool3` is `gb` with a tenth of production mixed in. It is all but the same candidate.
- A caution before the final period: `gb`'s development figure includes the choice of the best
  of nine settings and of the features themselves, and boosted trees have many ways to fit a
  period. The final period is the test.

All four go to the final period.

## Final stage

`run.py final` refits `dc` weekly through the final period with the chosen settings, retrains
`gb` at 2024-07-01, 2025-01-01, 2025-07-01, 2026-01-01 and 2026-07-01 on everything before each
date, applies the frozen pool weights, and scores each against replayed production. Guards: the
five goal markets (for `gb`, from its corrected goals through production's calibration; for
`dc`, the model's own lines with no calibration, since none was fitted; the pools change the
result probabilities only).

## What this cannot show

- Anything against the bookmakers, or a prospective record.
- That `dc` is the best such model. It is one reasonable member of its family, tuned on a small
  grid. A deficit of 0.004 to a production model that also has line-ups, injuries and a tuned
  blend is not evidence against the family; a gain would have been evidence for it.

## Running it

```bash
python experiments/architectures/run.py develop     # about ten minutes
python experiments/architectures/run.py final
```

`develop` also writes `development.npz` (per-match rates derived from feed data): don't commit it.

---

Evaluator as registered, before the final stage was run (2026-10-12):

- `run.py` SHA-256 `6d971182346bcace45b0d3504daf35fac089e26f60bef5da54255c192b9342da`
- `chosen.json` SHA-256 `7b6a4b0fc51b78c3cbddc4aa620b417fb88e278170b65b29236dfe9dbd259502`
- `features.py` SHA-256 `3d850304212cd88146df88b3497e8d491e8c9bb507bdc4af1e90354904bb6ab6`
