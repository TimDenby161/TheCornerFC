# A18 on the released club rank: do the boosted trees still help?

**Registered 2026-10-14, before `run.py` was run.** Step 2 of the owner's plan of 2026-10-14
(after P17): refit A18 (MC-0018, boosted trees correcting production's predictions) on the club
rank released that day (MC-0028), so that it can become the first challenger stored beside the
live model.

## Why it has to be refitted

A18's trees learn production's errors. About half of its gain on the old model came from recent
shot counts, and the release now uses shots in the club rank. So some of what the trees learned
is in the live model already, and a fit made on the old model's errors would correct mistakes
the live model no longer makes.

## What is run

- **Baseline: the live model.** The released club rank replayed by the research frame
  (`shots_proxy/run.py` with goals weight 0.5 and K 10, pull 0.5, boost 0.5 over 40 matches), and
  every stored projection moved onto it (`frame.reprojected`). Before the release went live this
  replay matched production's to 2e-13 rank points.
- **Candidate: A18's recipe on it.** Exactly the setting `experiments/architectures/chosen.json`
  fixed for `gb` (features, parameters, shrink), trained walking forward in the same half-season
  blocks from 1 July 2024 on the live model's own errors, with the features built from the
  released rank. Nothing is chosen or tuned here.
- **Primary.** Mean paired log loss, candidate minus baseline, over the final period (1 July 2024
  to the extract's cut, 11 October 2026), on **every** match with a 90-minute score: league
  matches, and cup ties settled after extra time or on penalties counted as the draws they were at
  90 minutes. 95% interval, clustered by week (one comparison). Brier, the goal markets and
  leagues and cups alongside.
- **Secondary.** The same on matches finished in 90 minutes only, the population A18's own test
  used (`frame.scored`), so the figure can be set beside its −0.0028 on the old model.
- **Reading it.** Proven better: the 95% interval is below zero. The owner's rule (2026-10-14) is
  that a proven gain, of any size, is ready to implement.

## What it is not

The final period has been looked at before, A18's recipe was chosen with it in view, and the
release's own settings were proven on it. So this answers "does A18 still add anything on top of
the release?", not "is it better on unseen matches". The unseen test is P17, which has been
scoring A18's recipe on the live model since 15 October, and then the stored challenger.
