# Rotation: report

Run once on 2026-10-29 with the registered `run.py` (DESIGN.md), on the starting XIs read
read-only from production (64,378 XIs of matches before 2026-10-12) and the research frame's
stored projections. Full figures: `results.json`.

## Verdict

**No help shown, for either candidate.** How many changes a side made in its previous match tells
the model nothing useful about its next one, and neither do the changes in the match itself.

| | A: prior changes | B: changes now |
|---|---|---|
| Chosen on 2023/24 (goals per change) | 0.045 | 0 |
| Test, 2024-07 to 2026-10-11 | 7,203 matches: log loss 1.0107 → 1.0118, +0.0011 (97.5%: −0.0002 to +0.0024) | 8,541 matches: unchanged |
| Holdout, 2021-07 to 2023-06 | 6,941 matches: +0.0008 (worse) | unchanged |
| By season (test) | 2024/25 worse, 2025/26 slightly better | — |

A was fitted on 2023/24, where it helped a little, and did worse on both other periods.

## The direct answer

The model's goal-difference error from a side's point of view, by how many changes the side made
in its previous match (test period, 95% intervals; positive means the side did better than the
model expected):

| Changes | Side-matches | Error (goals) |
|---|---|---|
| 0–1 | 5,649 | +0.01 (−0.03 to +0.04) |
| 2–3 | 8,008 | −0.02 (−0.05 to +0.00) |
| 4–5 | 3,102 | +0.01 (−0.04 to +0.05) |
| 6 or more | 585 | +0.10 (−0.03 to +0.25) |

No pattern, and the holdout shows none either. Only sides that changed six or more lean towards
doing better than expected, on few matches, with an interval that includes zero.

## Limits

- XIs are recorded for about 16% of scored matches, both sides with the previous match within 15
  days: mostly the bigger leagues.
- The test period had been scored before by other candidates (never split this way), so even a
  pass would have been a lead for a live test, not proof.
- The model already uses each side's predicted XI and the players' ranks, which is probably why
  rotation adds nothing: a rotated side's weaker XI is already in the projection.
