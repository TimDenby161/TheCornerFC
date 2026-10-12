# Level gaps: are cup ties between sides from different levels predicted too flat?

**Registered 2026-10-12, before `run.py` was run on any data.** An offline experiment on stored
projections. Production formulas, stored predictions and database records stay as they are, and
nothing is deployed by this experiment whatever it finds. It reads no odds and no prospective
snapshot; protocol P6 is untouched.

It follows `experiments/ends_and_draws`, which found that sharpening every result probability
helped in cups and nowhere else. This asks whether the cause is narrower: how the model places
sides from different levels against each other.

## Why the levels could be wrong

A club's first rank is the `starting_rank` of the first league it plays in, or of the first cup
for a club that only ever appears in cups. Matches inside a league move rank between its own
clubs, so the gap *between* two leagues is corrected only by the few matches across them: cup
ties, European games, and clubs going up or down. Two ways that could leave cup ties too flat:

- **The gaps between leagues are too small.** Then a side from the higher league beats a side
  from the lower one by more than the ranks say.
- **Clubs with no league in the data are rated too high.** A non-league side in the FA Cup or FA
  Trophy, or a club from an uncovered league in a European qualifier, starts at the cup's own
  starting rank and plays few matches to correct it.

## What was already seen

- `experiments/ends_and_draws/REPORT.md`: on July 2024 onward a sharpening applied everywhere was
  worth about 0.003 of log loss in cups and nothing in leagues, with the FA Trophy, the Champions
  League and the Europa League among the most improved. On 2021 to 2023 it was worth nothing
  overall.
- Earlier the same day: the goal-difference error by expected margin over all matches, and that
  cups as a whole show no home-side bias.
- The leagues' starting ranks (settings, not results).

Not looked at before registration: any split of matches by whether the two sides come from
different leagues or whether a side has a league at all, in any period; the number of such
matches; and the 2021 to 2023 seasons by competition.

## Definitions

Fixed here, worked out from fixtures alone, using nothing later than each kickoff.

- **A side's league at a match**: the competition of its most recent finished match before that
  kickoff in a competition of type `League`, if that match was within 400 days. Otherwise the
  side has **no league**.
- Matches in a competition of type `League` are never changed. Promoted and relegated clubs are
  out of scope.
- In any other competition, a match is:
  - **cross-league** when both sides have a league, the two leagues differ, and both leagues
    have a starting rank;
  - **one-sided** when exactly one side has no league;
  - otherwise unchanged (same league, or neither side has one).

## Hypotheses

**H3, the gaps between leagues.** In cross-league matches the expected margin d becomes
d + β × (home league's starting rank − away league's starting rank) / 100. β above zero means the
real gaps are wider than the ranks say. Grid: β from −0.10 to 0.50 in steps of 0.05.

**H4, sides with no league.** In one-sided matches the expected margin moves by δ / 100 goals
against the side with no league. δ above zero means those sides are rated too high, by δ rank
points. Grid: δ from −50 to 200 in steps of 25.

**Together.** Both applied. The two act on different matches, so searching them jointly and
separately is the same thing, and there is one combined candidate.

The projected goals are re-solved for the new margin as `predictions.project` solves them
(product kept, difference set), and the probabilities come from
`predictions.outcome_probabilities` unchanged. The goal markets move with the goals and are
checked.

These are stand-ins. β is what wider spacing of the starting ranks would do to a cup tie, and δ
what a lower starting rank for cup-only clubs would do, without replaying the ranking. A positive
result here is a reason to run the ranking replay, not a model change in itself.

## Data and periods

Every finished fixture from 2020-02 with its stored projection where one exists, read once in a
read-only transaction from production and frozen in `inputs.json.gz` (gitignored). Scored matches
are those finished in 90 minutes (`FT`) with a regulation score and a stored projection.

| Period | Kickoff (UTC) | Used for |
|---|---|---|
| Holdout | 2021-07-01 to 2023-06-30 | Scored once with the chosen settings. |
| Validation | 2023-07-01 to 2024-06-30 | β and δ are chosen here and nowhere else. |
| Test | 2024-07-01 to 2026-10-11 | Scored once with the chosen settings. |

Selection: the lowest validation log loss. A tie goes to the value nearest zero. The whole grid
is reported. If a chosen value is at the edge of its grid, that is reported and the grid is not
extended.

## Measures

Candidate against baseline on identical matches, over **the changed matches** (cross-league for
H3, one-sided for H4, both for the combined candidate) and over **all matches**:

- mean three-outcome log loss (primary), Brier, top-pick accuracy;
- calibration error and the ends gap, as defined in `experiments/ends_and_draws/DESIGN.md`;
- the mean goal-difference error towards the side the change favours (the higher league's side,
  or the side with a league);
- the calibration tables;
- by season, and by competition with 100 or more changed test matches;
- the goal markets on the changed matches (guard).

Uncertainty: paired bootstrap over UTC ISO weeks, 2,000 draws, seed 20261012, 95%, pointwise.

## Acceptance

Fixed here. Neither bar deploys anything.

**Bar A, the standing gate:** over all test matches, log loss better by at least 0.002 with the
interval excluding zero, Brier agreeing, and the same direction in 2024/25 and 2025/26. Only a
share of matches is changed, so this is a high bar by construction; it is kept because it is the
bar every production change has been held to.

**Bar B, the case for the ranking replay.** All of, on the changed matches:

1. Test log loss better, interval excluding zero.
2. Test Brier no worse.
3. The ends gap falls by at least 30% on test, and the interval for the fall excludes zero.
4. Calibration error no worse on test.
5. Log loss better in 2024/25 and in 2025/26.
6. **Holdout log loss better, with its interval excluding zero.** Stricter than in
   `ends_and_draws`, where the holdout was the evidence that mattered.
7. No goal market worse by more than 0.0005.
8. At least 60% of the competitions with 100 or more changed test matches are no worse.

Each candidate is reported as meeting A, meeting B only, or meeting neither, with each condition.

## What this cannot show

- That the ranking itself should change: only that a replay is worth running.
- Anything against the bookmakers, or about a prospective record.

## Running it

```bash
python scripts/environment.py production         # read-only
python experiments/level_gaps/run.py --refresh   # reads the inputs once, then evaluates
python scripts/environment.py staging
python experiments/level_gaps/run.py             # later runs: from the frozen inputs
```

`run.py` takes its measures from `experiments/ends_and_draws/run.py`, which is not edited.
`results.json` holds aggregates only and records both files' SHA-256.

---

Evaluator as registered, before any run on data: `run.py` SHA-256 `8393afd0747fa8505e546e0e5643e914571663aff6ac5a95faf5bec45785e157` (2026-10-12).
