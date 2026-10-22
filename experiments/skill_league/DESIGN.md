# Skill scores adjusted for the league they are played in

**Registered 2026-10-22, before `run.py` was run on any data and before the model file was
changed.** Owner's question (2026-10-22): D. Markanday (Chesterfield, League Two) scores 90 in
finishing, 88 in creating and 96 in dribbling but is 70 overall, "do you think that maybe his
skills are too high?" The skill scores (MC-0030) are a player's output per 90 against every
listed regular in every league, with no allowance for the level: League Two numbers are set
against the Premier League's as they are. Owner's choice (2026-10-22): adjust each skill score
for the league it was played in, so the scores stay comparable across leagues.

## The change

In `thecornerfc/models/player_ratings.py`, for the skill scores only (nothing in the ranks reads
them, and the ranks must not move):

- **A unit** is one outfield player's season in one league with per-match data
  (`config.MATCH_PLAYER_LEAGUES`) and 900 or more minutes there. Its **skill z** is the skill's
  recipe over that season, per 90, against the skill norms (`_skill_norms`), with no pull towards
  the prior: `sum(w * (m - mean) / sd)` over the recipe's stats, as `skill_scores` does now.
  `skill_units(apps, norms)` returns `(player, season, league, minutes, {skill: z})`.
- **League offsets** (`skill_league_offsets(units)`): for each skill, `z = player + league` fitted
  by alternating means over the units (every unit counts once), until no offset moves by more than
  1e-6 or 200 rounds. Offsets are then shifted so the units in `config.RATING_REFERENCE_LEAGUES`
  average 0, and each league's offset is shrunk towards 0 by `n / (n + 30)`, where `n` is the
  number of its units whose player has a unit in another league (the movers that tell the leagues
  apart). Returns `{league: {skill: offset}}`.
- **The rating window keeps each league's minutes**, and a player's **skill score** takes off the
  minutes-weighted average of his leagues' offsets from the skill's per-90 z before the pull
  towards the prior and the percentile, both as now. The offsets are fitted on every unit the run
  has.

Keepers are untouched (they have no outfield skills). The percentile is still among the listed
outfield players with 900 or more window minutes, as the code has done since MC-0030.

## The evaluator (`run.py`)

On production, read-only (the switch on `production`), no API calls.

1. **Moves it hasn't seen.** Units of seasons up to 2024 fit the offsets. The test pairs are
   every player with a unit in league A in season t and a unit in another league B in season t+1,
   with t+1 in 2025 or later. For each skill, predict his z in B at t+1 from his z in A at t:
   **base**, the same z; **adjusted**, `z - offset[A] + offset[B]`. Metric: the squared error,
   averaged over the pairs for each skill, then over the seven skills.
2. **The ranks are untouched.** `compute_player_ratings` is run twice with the database write and
   the line-up capture replaced, once as changed and once as the file was at the base commit (read
   from git and checked against its fingerprint). Every current rank, season rank, position rank
   and predicted XI must be identical.

**It passes only if all of these hold:**

1. There are at least 200 test pairs (otherwise: no verdict).
2. The adjusted error, averaged over the seven skills, is lower than the base, and the 95%
   interval of the difference (players resampled, 2,000 draws, seed 20261022) lies wholly below 0.
3. The adjusted error is lower for at least 5 of the 7 skills.
4. The ranks and predicted XIs are identical, base against changed.

Reported alongside, without bearing on the verdict: each league's offsets, the skill scores of
D. Markanday before and after, and the average score of each league's listed regulars before and
after.

## Cost

No new data, no API calls, nothing new stored (`players.skills` keeps its shape). The fit runs
inside the nightly's player ratings: a few seconds.

## What it can't show

Players who move are not a random sample: some move up after a good season and fall back, which
makes a lower league look easier than it is. The test on later moves measures the fit as it will
be used, bias included; it can't separate the two.
