# Ends and draws: two calibration changes to the result probabilities

**Registered 2026-10-12, before `run.py` was run on any data.** An offline experiment. Production
formulas, stored predictions and database records stay as they are; nothing here is read by
production, and nothing is deployed by this experiment whatever it finds. The prospective protocol
P6 (`experiments/prospective/PROTOCOLS.md`) is untouched: this experiment reads no odds and no
prospective snapshot, and its result is not P6's.

## What was already seen (read this first)

These hypotheses were not thought up blind. They came from diagnostics run the same day on the
stored predictions for 1 July 2024 to 15 September 2026, which is most of the test period below.
What was looked at there:

- the result probabilities' calibration in ten bands per outcome (outsiders overrated, strong
  favourites underrated);
- the goal-difference error by expected margin;
- predicted and actual draw rates by season and by size of expected margin;
- one candidate of the kind tested here: every probability raised to the power 1.1 and rescaled,
  with 1.1 fitted on 2023/24, changed test log loss by −0.0007 (−0.0011 to −0.0003).

So a result on the test period confirms a pattern that was found there. It is not a blind test.
Two things in the design answer that:

- **Every setting is chosen on 2023/24 only**, by the rule below, and the test period is scored
  once with those settings.
- **A holdout that was not looked at**: 1 July 2021 to 30 June 2023. No diagnostic above touched
  it. It lies before the tuning year, so it is unseen rather than later, and the club ranks behind
  it were replayed with today's settings, like every reconstruction here. A change has to point
  the same way there.

The clean confirmation is prospective: the same comparison on snapshots captured from now on. It
is not registered here. If either change is taken forward, that is the next step to register.

## Hypotheses

**H1, the ends.** The model's step from expected margin to result probabilities is too flat for
mismatches: it gives outsiders too much and strong favourites too little. Stretching it improves
the result probabilities. Three one-number forms are tried, and the one with the lowest
validation log loss is the registered candidate for H1:

| Form | What changes | Grid |
|---|---|---|
| `quadratic` | expected margin d becomes d × (1 + c × \|d\|) | c from −0.02 to 0.20 in steps of 0.02 |
| `linear` | d becomes k × d | k from 0.96 to 1.20 in steps of 0.02 |
| `power` | each final probability is raised to the power a, then the three are rescaled | a from 0.96 to 1.20 in steps of 0.02 |

For the two margin forms the projected goals are re-solved as `predictions.project` solves them:
the product of the two sides' goals stays the same and their difference becomes the new margin.
That is what the production function would return for the stretched margin, so the goal markets
move with it and are checked. The `power` form leaves the projected goals alone.

**H2, the draws.** The draw boost (`DRAW_INFLATION` 1.1, fading to nothing at
`DRAW_FADE_MARGIN` 1.5 goals) puts too much on the draw. Refitting the two numbers improves the
result probabilities. Grid: inflation 1.00 to 1.12 in steps of 0.01; fade margin 0.75, 1.0, 1.25,
1.5, 2.0, 3.0.

**Together.** H1's chosen form and H2 searched jointly on validation (`joint`), and the two
separately chosen settings applied at once (`stacked`). `joint` is the registered combined
candidate; `stacked` is reported beside it.

## Data

Stored projections (`fixture_predictions.home_xg`, `away_xg`) joined to results, read once in a
read-only transaction from production and frozen in `inputs.json.gz` (gitignored feed data).
Finished in 90 minutes (`status_short = 'FT'`) with a regulation score; extra-time and penalty
matches are left out, not relabelled.

The baseline is `predictions.outcome_probabilities` and `predictions.goal_lines`, imported
unchanged, applied to the stored projected goals. The harness's own copy of the probability step
takes the two draw numbers as arguments and must return the production function's output at the
production values to within 1e-9 on every row; `run.py` checks this and stops if it does not.

| Period | Kickoff (UTC) | Used for |
|---|---|---|
| Holdout | 2021-07-01 to 2023-06-30 | An unseen check. Scored once with the chosen settings. |
| Validation | 2023-07-01 to 2024-06-30 | Every setting is chosen here and nowhere else. |
| Test | 2024-07-01 to 2026-10-11 | Scored once with the chosen settings. |

There is no training step: the changes have one or two numbers each, chosen on the validation
year. The rest of the model was itself tuned on 2023/24 and its ranks replay every year, so this
is a historical reconstruction, not a prospective record.

## Selection rule

The lowest mean three-outcome log loss on validation. A tie goes to the setting nearest
production. The whole grid is reported. Nothing is chosen on test or holdout.

## Measures

On identical matches, candidate against baseline:

- **Primary:** mean three-outcome log loss, candidate minus baseline.
- **Brier** (sum of the three squared errors) and top-pick accuracy.
- **Calibration error:** per outcome, the match-weighted absolute gap between mean predicted and
  observed rate over ten equal bands, averaged over the three outcomes.
- **Ends gap** (named for H1): the same gap over the home-win and away-win bands below 20% and
  from 70% up only.
- **Draw gap** (named for H2): the match-weighted absolute gap between predicted and observed
  draw rate over five bands of expected margin (under 0.25, 0.25 to 0.5, 0.5 to 1, 1 to 1.5,
  1.5 and over).
- The calibration tables themselves, baseline and candidate.
- **By season** (July to June) and **by competition** (those with 300 or more test matches): the
  log-loss and Brier change in each, and how many competitions are no worse.
- **Goal markets** (guard): log loss on over 1.5, 2.5, 3.5, 4.5 and both teams to score. Only the
  two margin forms can move these.

Uncertainty: paired bootstrap over UTC ISO weeks, 2,000 draws, seed 20261012. Intervals are 95%,
pointwise, not adjusted for the number of candidates. By-competition figures are descriptive.

## Acceptance

Both bars are fixed here. Neither deploys anything: the owner decides after the report.

**Bar A, the standing gate** (`experiments/STAGE_E_DECISION.md`): on test, log loss better by at
least 0.002 with the interval excluding zero, Brier agreeing, and the same direction in 2024/25
and 2025/26.

**Bar B, the calibration case.** New here, and weaker by design. The reasoning behind it: an error
in the ends matters to the betting rule far more than log loss weighs it. A change
meets Bar B when all of these hold:

1. Test log loss is better and its interval excludes zero, whatever the size.
2. Test Brier is no worse.
3. Its named gap (ends for H1, draw for H2, both for the combined candidates) falls by at least
   30% on test, and the interval for the fall excludes zero.
4. Overall calibration error is no worse on test.
5. Log loss moves the same way in 2024/25, in 2025/26 and on the holdout.
6. No goal market is worse by more than 0.0005.
7. At least 60% of the competitions with 300 or more test matches are no worse on log loss.

Each candidate is reported as meeting A, meeting B only, or meeting neither. Whether Bar B is
enough to change production is the owner's decision, to be taken knowing that it is a lower bar
than every earlier change was held to.

## What this cannot show

- That either change helps against the bookmakers. No odds are read.
- That either change makes the paper bets profitable.
- Anything about a prospective record.

## Running it

```bash
python scripts/environment.py production            # read-only
python experiments/ends_and_draws/run.py --refresh  # reads the inputs once, then evaluates
python scripts/environment.py staging
python experiments/ends_and_draws/run.py            # later runs: from the frozen inputs, no database
```

`results.json` holds aggregates only. `run.py` records its own SHA-256 in it; the digest of the
evaluator as registered is at the foot of this file.

---

Evaluator as registered, before any run on data: `run.py` SHA-256 `2b91a1d52bd6a29345c8c6c7133d34d881841028e4d2ba06384ded381616ea7b` (2026-10-12).
