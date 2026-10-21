# Skill ranks: players ranked on single skills, and each position's rank a mix of skills

**Registered 2026-10-21, before `run.py` was run on any data and before the model file was
changed.** Owner's request (2026-10-16): "can we rank players by certain skills by the stats and
then assign each position a combination of different skills?" Owner's choice (2026-10-21):
start from today's weights, so the ranks start where they are, then tune each position's skill
mix by eye.

## The skills

Eight skills, from the counted stats the model already uses (no new data, no API calls). The data
has no aerial duels, crosses or per-player xG, so there is no aerial skill: duels are all duels.

| Skill | Stats (direction) |
|---|---|
| Finishing | goals, shots on target |
| Creating | key passes, assists |
| Passing | passes, pass accuracy |
| Dribbling | dribbles won, failed dribbles (lower is better) |
| Ball-winning | tackles + interceptions, blocks |
| Duels | duels won % |
| Defensive solidity | times dribbled past, team xG conceded while he played (both lower is better) |
| Goalkeeping | save %, pass accuracy, goals conceded (lower is better): keepers only |

## The change

In `thecornerfc/models/player_ratings.py`:

- **A skill's recipe** is one set of stat weights for every position. It is fixed by a rule, not
  by looking at results: each stat's share of the skill is its total weight across the eight
  outfield role groups in today's `WEIGHTS`, divided by the skill's total (sign kept).
- **A position's skill mix** is, for each skill, the total of that group's weights today on the
  skill's stats (`SKILL_MIX`). The position's stat weights are then mix × recipe, so every group
  gives each skill the same share it gives today, and only the balance of stats inside a skill can
  move. `WEIGHTS` is worked out from `SKILLS` and `SKILL_MIX` when the module loads, and
  everything that read it reads it as before.
- **Keepers are untouched**: Goalkeeping is their whole mix with today's weights as its recipe.
- **Skill scores for the lists.** For every outfield player with a current rating window, each
  outfield skill's score over that window (per 90, standardised against all outfield regulars of
  the reference leagues, pulled towards below-average with few minutes, as a position score is),
  as a percentile among those regulars: 0 to 100. These are new outputs for the site; nothing in
  the ranks reads them.

## The evaluator

`run.py` runs `compute_player_ratings` twice on a read-only connection, with the database write
and the line-up capture replaced: once as changed, and once with `WEIGHTS` put back to the base
file's (`player_ratings.py` at `65703faa1`, read from git and checked against its fingerprint).
Everything else is the same code on the same data. Population: every player and team-match the
run rates; no sample is drawn, so there are no intervals.

**It passes only if all four hold:**

1. **Keepers are untouched.** Every goalkeeper's current rank, season ranks and position rank is
   identical, base against changed.
2. **The ranks start where they are.** Within each outfield role group (of the position the run
   lists the player in), the Spearman correlation of current rank, base against changed, is at
   least 0.98.
3. **No less repeatable.** The Spearman correlation of season rank from one season to the next
   (consecutive seasons, 1,500+ minutes in both) is no more than 0.01 lower than the base's, for
   all such players and for those who changed club between the two seasons.
4. **Match inputs barely move.** The mean absolute change in predicted-XI rating over every
   team-match is at most 0.5 points (0.0025 goals of expected margin at 0.005 a point).

**Reported, with no threshold:** the recipes and mixes; how far current ranks move (mean, 95th
percentile, largest, share 2+ points), overall and per group; how many of each group's top 10
are the same players; how many predicted XIs pick a different player; the season-to-season
correlations themselves; and each skill's top 10 among listed players with 900+ minutes.

If a check fails, nothing is released: the owner sees the numbers and decides (for example,
recipes per position, which keeps the ranks exactly but gives no single list per skill).

## Evidence that starts again

`player_ratings.py` is fingerprinted, so a release registers new versions of
`current-player-rating`, `match-prediction`, `formation-minutes-lineup` and
`national-recent-minutes-lineup`. The prospective protocols select rows by what a snapshot
reproduces, not by version id, and carry on.

## What it costs

No API calls. One read-only run of the player ratings on production for the evaluation (twice
from the local cache). On release: one small stored set of skill scores for the listed players
(about 8,000 players × 7 skills), written only where it changed, and a column on the site's
players table: a migration for the owner. No extra job time worth counting.
