# Rotation: do a side's line-up changes help predict its next match?

**Registered 2026-10-29, before any line-up was read for it.** An offline experiment on stored
projections (T-070). Production formulas, stored predictions and database records stay as they
are, and nothing is deployed by this experiment whatever it finds. It reads no odds and no
prospective snapshot; P6 and the live protocols are untouched.

## The question

The owner, 2026-10-29: "if you look at how many changes a side made the week before has any
statistical help for the next game?" A side that rotated heavily in its last match may have
rested players (fresher now), or may have been saving them for another competition. The live
model sees each side's predicted XI and the players' ranks, but not how much the side has been
changing its team.

## Definitions

Fixed here, from the frozen fixtures and one read of the starting XIs (`fixture_players.started`),
using nothing later than each kickoff.

- **A side's XI at a match**: the players it started, when exactly 11 are recorded.
- **Its previous match**: the side's latest finished match in the data (any competition) that
  kicked off before this one.
- **Changes in a match**: how many of the side's starters were not in its XI in its previous
  match (0 to 11). Defined only when both XIs are known and the previous match kicked off no more
  than 15 days earlier (a week, or an international break).
- **Prior changes** (the owner's question): the changes the side made **in its previous match**.
  Known as soon as that match has started, days before this one. Defined when the previous match
  kicked off no more than 15 days before this one and its own changes are defined.
- **Changes now** (secondary): the changes the side made **in this match**. Known only from the
  confirmed line-ups, about an hour before kickoff; the base model uses a predicted XI instead.

A match is **covered** for a measure when it is defined for both sides.

## Candidates

The expected margin d (home goals minus away goals) is moved, the product of the two projected
goals kept, as `predictions.project` solves it (`frame.moved`); the probabilities come from the
production step unchanged (`frame.outcome_probabilities`).

| Candidate | Change to d, in covered matches only | Grid |
|---|---|---|
| **A, prior changes** | β × (home prior changes − away prior changes) | β from −0.05 to 0.05 goals per change, steps of 0.005 |
| **B, changes now** | γ × (home changes now − away changes now) | the same |

β above zero means a side that rotated more last time does better than the model expects now.

## Periods

| Period | Kickoff (UTC) | Used for |
|---|---|---|
| Holdout | 2021-07-01 to 2023-06-30 | Scored once with the chosen value |
| Validation | 2023-07-01 to 2024-06-30 | β and γ are chosen here and nowhere else |
| Test | 2024-07-01 to 2026-10-11 | Scored once with the chosen value |

Scored matches: finished (FT, AET or PEN) with a regulation (90-minute) score and a stored
projection. Selection: the lowest validation log loss on covered matches; a tie goes to the value
nearest zero. The whole grid is reported. A value at the edge of the grid is reported as such and
the grid is not extended.

**What was already seen.** The test period was scored by 14 candidates in the 2026-10-12 research
and has been read since (lessons-learned: "a period of history can be spent"). None of those
split matches by line-up changes, and nothing about line-up changes has been looked at in any
period before this registration. So a pass here is a strong lead, not proof: the proof is a live
test, registered separately if this passes.

## Measures

Candidate against the stored projection on identical matches, over covered matches and over all
scored matches:

- mean three-outcome log loss (primary), Brier, top-pick accuracy, calibration error
  (`frame.compare`), by season, by competition (300 or more matches), leagues against cups;
- the five goal markets (guard);
- **the direct answer**, for each side-match with prior changes defined: the model's goal-
  difference error from that side's view, (goals for − against) − (projected for − against), by
  band of prior changes (0–1, 2–3, 4–5, 6 or more); the same for changes now. Descriptive.

Uncertainty: paired bootstrap over UTC ISO weeks, 2,000 draws, seed 20261012. Two candidates, so
each primary interval is given at 97.5% (Bonferroni) with the plain 95% beside it.

## Reading it

Fixed here. A candidate **helps** when all of:

1. test log loss on covered matches is better, its 97.5% interval excluding zero;
2. holdout log loss on covered matches is better (mean below zero);
3. test Brier on covered matches is no worse;
4. log loss is better in 2024/25 and in 2025/26;
5. no goal market is worse by more than 0.0005 on covered test matches.

A candidate whose test interval excludes zero but which misses another condition is **a real
effect, not shown to help**. Anything else is **no help shown**. The gain over all matches is
labelled against the old 0.002 bar for size only.

If A helps, the next step is a proposal to the owner for a live test of it (P15's method), not a
release. If only B helps, the gain needs confirmed line-ups an hour before kickoff, which the jobs
capture for very few matches today (22 of 2,981 at the 2026-10-12 audit): it joins research item
2 (confirmed line-ups) rather than the model.

## Cost

One read-only query of production: the starting XIs of finished matches before 2026-10-12,
grouped per side and match (about 200,000 rows), frozen in `inputs.json.gz` (gitignored). No
API-Football calls. Nothing runs on a schedule. If it were ever taken live, the line-ups are
already fetched and stored, so it would add no calls and no rows.

## Running it

```bash
python scripts/environment.py production         # read-only
python experiments/rotation/run.py --refresh     # reads the XIs once, then evaluates
python scripts/environment.py staging
```

Needs numpy, and the research frame's `inputs.json.gz`.

`run.py` SHA-256 at registration: `3dec81d5d959daeab1e82b45dbfef014736f110ca7cedbe35812046bf6ee840a`
