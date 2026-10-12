# Own-position rank: a player's rank in his own position is his Ability, and he has one in every position

**Registered 2026-10-12, before `run.py` was run on any data and before the model file was
changed.** A change to a published number, not to a forecast: no match prediction, line-up or
bet reads the position ranks, so there is no outcome to score it against. The evaluator checks
that the change does what the owner asked and moves nothing else.

## Why

A player has two numbers that read as the same thing. **Ability** is his rank for the current
season: his level on the age curve, then pulled towards this season's own evidence in proportion
to his minutes (`season_model` steps 4 and 5). His **position ranks** (step 6) are a level per
position with no pull from this season. So a player who has only ever played centre-back shows
one number in the header of his page, on the Players tab and on a match's pitch, and another on
his CB chip and in the Players tab once CB is picked (Thiaw, 2026-10-12: Ability 82, CB 84).

The owner's rule (2026-10-12): Ability is what the Players tab is ordered by, and a player's rank
in his own position must be that number.

The same day the owner asked that a match's pitch show each predicted starter's rank in the
position he is picked in, the number on his own page. A player has a position rank only where he
has started since 2020/21, so one picked somewhere new (Haaland on the left wing) had nothing to
show but his Ability. The owner's second rule: work out what he would be there.

## What was already seen

On staging's copy of `site.players`, before this was written: 2,277 outfield players have both
numbers; the best position rank is above Ability by more than half a point for 712 and below for
634, the average gap either way is 1.1 points, 161 are 3 or more apart and 23 are 5 or more.
Five players' pairs were read (Thiaw, Botman, Wissa, Mfuni, and Thiaw's season ranks).

Not looked at: any output of the changed model; how many players' own group differs from the
position the site shows for them; how far the other positions' ranks move; any rank in a position
a player has not started in.

## The change

In `season_model`, step 6 (`thecornerfc/models/player_ratings.py`):

- **Own position.** A player's own role group is the one his Ability is built on: the group he
  has played most minutes in over his seasons with evidence (step 4's `g`, whose age curve he
  follows). His position rank in that group is his current-season rank, the same rounded number.
- **Other positions.** Each keeps its own level, as now, and is then pulled towards this
  season's evidence scored as that position, as step 5 pulls Ability: by
  `w / (w + DEVIATION_MINUTES)`, where `w` is this season's minutes times how well the position
  he played fits it (`GROUP_FIT`, the weight the season already has in that position's level).
  The familiarity penalty comes off afterwards, as now.
- **Positions he has never started in.** Every outfield player with evidence gets a rank in all
  eight outfield groups, not only those he has started in. An unplayed one is built exactly as a
  played one: his seasons scored with that position's weights and counted by fit, the pull, then
  the penalty, which is whole because he has no starts there (8 points for a striker on the
  wing, 14 for an unrelated position).
- **A player with no starts in his last three seasons** was treated as familiar everywhere (no
  penalty). His usual position is now his own group, so his other positions pay the penalty.
- Nothing else changes: season ranks, projected ranks, current ranks, predicted line-ups and XI
  ratings are computed before step 6 and don't read it.

## The evaluator

`run.py` runs the player ratings once, read-only, with the database write and the line-up
capture replaced. It records what `season_model` was given, then gives the same inputs to the
model file as it was at the base commit (`07363e9c9`, loaded from git and checked against its
fingerprint) and compares the two answers. Population: every player the run rates. No sample is
drawn, so there are no intervals.

**It passes only if all four hold:**

1. **Season ranks are untouched.** Every (player, season) row is identical, base against new.
2. **Projected ranks are untouched.** Every (player, season) projection is identical.
3. **Every position is ranked, and none is lost.** Every (player, role group) rank the base
   gives is still given, and every player with any position rank has one in each of the eight
   outfield groups.
4. **Own position is Ability.** For every player with a position rank in his own group, that
   rank equals his current-season rank exactly. No exceptions.

**Reported, with no threshold:**

- how many outfield players with a current-season rank have no position rank in their own group
  (never started there in the per-match data), so nothing is anchored for them;
- how many players' own group differs from the group of the position the site shows for them
  (most started minutes over the last 12 months): for these the chip marked as their position
  can still differ from Ability;
- of the players the site lists, the share whose shown position's rank rounds to the same whole
  number as Ability, base and new;
- how far ranks move, base to new: own position and other positions separately (mean, 95th
  percentile, largest, and the share moving 2 or more points);
- for ranks in positions the base did not give (never started in): how many, and how far below
  Ability they sit (mean, 5th and 95th percentile, and how many are above Ability);
- per role group, how many of the top 10 by that group's rank (among listed players shown in a
  position of that group) are the same players, base and new.

## Evidence that starts again

`player_ratings.py` is fingerprinted, so the change registers new versions of every model whose
identity includes it, although only the position ranks change: `current-player-rating`,
`match-prediction`, `formation-minutes-lineup` and `national-recent-minutes-lineup`. The
prospective protocols select rows by what a snapshot reproduces, not by version id, and carry on.
