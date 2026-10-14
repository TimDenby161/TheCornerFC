# The club-rank release: movers, new clubs and shots (MC-0028, protocol P16)

**Registered 2026-10-14, before the model code it judges was written and before any fixture in
its population had kicked off.** The owner decided on 2026-10-14 to release two changes that the
research round proved better than production on the final period, at any size (the tracker's
green, `guide/admin-area.md`), as one new match-model version:

- **A16 (MC-0016), movers and new clubs.** A club that changes division in its own country,
  having played a league match there in the last 400 days, is moved halfway to the average rank of
  the division it joins (its whole history moves with it). A club's step after each match is
  multiplied by 1 + 0.5 × exp(−matches played / 40), so new clubs move faster. Settings from
  `experiments/rating_dynamics/chosen.json` (`combined`).
- **A24 (MC-0024), shots for xG.** A match with no xG but shot counts on both sides moves the
  rank on 0.5 × the capped goal difference + 0.5 × the difference in xG estimated from shots
  inside the box, outside it and on target, with K 10. Settings and the estimate from
  `experiments/shots_proxy/chosen.json`.

A18 (the boosted trees) is not in it: it learned production's errors and has to be refitted on
the new rank first, as a release of its own.

## The evidence so far, and what it is not

The two were chosen on 2022-07 to 2024-06 and scored on 2024-07 to 2026-10. Together, on the
final period (`experiments/shots_proxy/results.json`, `descriptive_stack`): log loss better by
0.00118, 95% interval 0.00060 to 0.00176, better in each season. That stack is descriptive, not a
registered comparison: both parts' own final results were known when it was run, and the final
period had been looked at before. The one test that has not been seen is the next one.

## P16: the release against the model it replaced, on live matches

- **Hypothesis.** The released version's predictions have lower result log loss than the
  version before it would have had, on the same live fixtures.
- **Population.** Finished fixtures with a 90-minute score kicking off from 2026-10-15 00:00 UTC
  (ties decided after 90 minutes count as the draws they were), whose latest prospective snapshot
  before kickoff was made by the released version: a match-model version whose source digests
  differ from the version before it in `ranking.py` and in no other file. A fixture whose latest
  snapshot came from the old version is left out and counted. The snapshot's stored probabilities
  must be reproduced by the registered probability step, as in P15.
- **The model it replaced.** Re-created per fixture from the released snapshot: its stored
  projected goals moved by the change in the match-rank gap between the two club ranks, both
  replayed by the research frame over every match before it (the old one by `frame.replay`, the
  released one by `shots_proxy/run.py`'s replay with the A24 setting and the A16 movement). This is
  how P15 applied every rank candidate, the other way round. Nothing else in the model changes, so
  the rest of the prediction is the same on both sides.
- **Comparison.** Mean paired log loss, released minus re-created old, per fixture.
- **The method.** P15's confidence sequence, imported from `live_p15.py` (`track`), with the
  whole 5% on this one comparison: tightest at 6,200 fixtures, widened by the week-cluster design
  effect, nothing called before 500 fixtures and 8 weeks, and a call stands once made.
- **What it costs.** Worked out before any fixture was scored, on the final period already seen:
  the per-fixture standard deviation of the difference is 0.0545 and the week design effect 1.30.
  At the stack's own 0.00118 a call is expected at about 27,000 fixtures, around seventeen
  months; at A16's 0.0008 alone, about 64,000. So this is a long confirmation, and a safeguard
  sooner: a release that is in fact worse is called worse as quickly as a better one is called
  better.
- **Reading it.** "Proven better": the whole interval of released minus old is below zero; the
  release stands. "Proven worse": the whole interval is above zero; the owner is told and decides
  whether to revert. Anything else is undecided, whatever its sign.
- **Checks recorded with every run.** How far the frame's replay of the released rank is from the
  match ranks the snapshots stored (the mean and largest gap, in rank points), so a production
  build that drifts from the experiment is seen, and the counts left out for each reason.
- **Evaluator.** `experiments/prospective/live_p16.py`: `--store` writes the administrator's
  document `live_tracking`, in P15's shape, which the Model Change Tracker already reads. The
  files that define both ranks are pinned by SHA-256.

## What the release does to P13, P14 and P15

All three compare their candidates with production's stored predictions, and production is
what this changes. P15 applies each rank candidate as a difference from the old rank, so after
the release it would add the movers and the shots a second time without failing any check. They
close on the day the release reaches `main`, by an amendment in `PROTOCOLS.md` written that day,
before any of their fixtures was read: none had reached its minimum sample.
