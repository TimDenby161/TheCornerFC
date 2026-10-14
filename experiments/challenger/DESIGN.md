# Two match models side by side, with a switch (MC-0029, protocol P18)

**Registered 2026-10-14, before the model code it judges was written.** Step 3 of the owner's
plan of 2026-10-14. The owner chose (a): A18 built into the production code, not the research
code run before kickoffs.

## What runs

- **`base`**: the match model as released on 2026-10-14 (the club-rank release, MC-0028).
- **`a18`**: `base` with A18's boosted trees correcting its projected goals, the recipe fixed in
  `experiments/architectures/chosen.json` (`gb`: 44 features, two of them from the weekly Poisson
  model, depth 3, 300 iterations, shrink 1.0), retrained each half-season (1 January, 1 July) on
  `base`'s own errors, as `experiments/a18_on_release` measured it: log loss 0.0019 better on the
  final period (95% 0.0012 to 0.0025), a seen period.

Every run of the jobs works out both for every upcoming fixture. The switch
(`match_model_switch`, set from the Admin area) names the live one, which writes
`fixture_predictions` and its prospective snapshots as now, so the site, the paper bets, the
fantasy models and the records all follow it. The other's prediction goes to
`challenger_predictions`, rewritten by each run until kickoff and never after. Each snapshot's
inputs say which model made it (`match_model`). Migration `20261014_challenger_model.sql`.

## Built into production, checked against the experiment

A18's three parts (the features, the weekly Poisson model and the trees) are ported into
`thecornerfc/models/` and checked on every fixture of the research inputs against
`research_frame/features.py` and `architectures/run.py` before release, as the club rank was.

## P18: the challenger against the live model, both stored before kickoff

- **Hypothesis.** `a18`'s predictions have lower result log loss than `base`'s on the same live
  fixtures.
- **Population.** Finished fixtures with a 90-minute score (ties after extra time count as the
  draws they were) kicking off from the first day after the release reaches `main`, whose latest
  prospective snapshot before kickoff says which model made it, and whose other model's row in
  `challenger_predictions` was written before kickoff. Whichever model was live, both
  predictions were made before the match.
- **Comparison.** Mean paired log loss, `a18` minus `base`.
- **The method.** P15's confidence sequence (`live_p15.track`, imported), the whole 5% on this
  one comparison, nothing called before 500 fixtures and 8 weeks, a call standing once made.
- **What it costs.** Worked out before any fixture: with the trees' per-fixture standard
  deviation (0.097, P15) and the refit's 0.0019, a call is expected at about 26,000 fixtures
  (34,000 with a week design effect of 1.3), around a year and a half to two years. P17 has been
  scoring the same recipe on paper since 15 October and may call it sooner; P18 is the clean
  confirmation, made from predictions that existed before each match.
- **Reading it.** Proven better: green, and the owner may switch to `a18` (the switch is theirs;
  nothing switches by itself). Proven worse: the owner is told. Anything else is undecided.
- **Evaluator.** `experiments/prospective/live_p18.py`, run with P16 and P17 by
  `live_tracking.py`, which stores the one document `live_tracking`.
