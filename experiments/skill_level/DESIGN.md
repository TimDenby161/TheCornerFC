# Skill scores pulled towards the level a player plays at

**Registered 2026-10-22, before `report.py` was run and before the model file was changed.** A
judgement, not a tested improvement. Owner, 2026-10-22: D. Markanday (Chesterfield, League Two)
still scores 97 in dribbling after the league adjustment (MC-0031), and "shouldn't have 97
dribbling if leagues are taken into account". The movers' data behind MC-0031 says lower-league
dribbling numbers are not inflated (League Two −0.08 standard deviations, 1,230 seasons of players
seen in another league), so no test on moves can support a further cut; the owner chose to pull
lower leagues down by level anyway, as Ability does through club strength, and to set how hard
by eye.

## The change

In `thecornerfc/models/player_ratings.py`, for the skill scores only (nothing in the ranks reads
them):

- **His level** is his minutes-weighted club strength over the rating window (the window's
  `club_mins / minutes`, the same club strength Ability starts from).
- **The reference level** is the minutes-weighted average of that over the listed outfield
  players with `SKILL_SAMPLE_MINUTES` or more whose window minutes are mostly in
  `config.RATING_REFERENCE_LEAGUES`.
- **Each skill's per-90 z** (after the league offsets of MC-0031) has
  `SKILL_LEVEL_PULL × (his level − reference level) / 100` added, before the pull towards the
  prior and the percentile, both as now. So a player at clubs 100 points below the reference
  average moves down by `SKILL_LEVEL_PULL` standard deviations in every skill, and one 100 points
  above moves up by as much.
- `SKILL_LEVEL_PULL` is the owner's to set by eye from the report, like `SKILL_MIX`.

## The report (`report.py`)

On production, read-only (the switch on `production`), no API calls. One run of
`compute_player_ratings` with the database write and the line-up capture replaced, keeping the
inputs to `skill_scores`; the scores are then worked out again at pulls of 0, 0.25, 0.5, 0.75 and
1.0. Reported for each: D. Markanday's seven scores; E. Haaland's, M. Salah's and V. van Dijk's;
the top ten in dribbling and in finishing with their leagues; each league's average score in
each skill.

**One check must hold before release:** a second run, as the file was at the base commit (read
from git and checked against its fingerprint), and every rank, season rank, position rank,
projection and predicted XI identical (the data outputs, compared by name).

## Cost

No new data, no API calls, nothing new stored. A few milliseconds in the nightly.
