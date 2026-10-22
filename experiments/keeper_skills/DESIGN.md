# Keeper skills

**Registered 2026-10-22, before `report.py` was run and before the model file was changed.** A new
output for the site, not a change to any rank. Owner's look over the live site (T-061,
2026-10-22): Alisson "should have ... a saves skill? Saves vs xG prevented?" Keepers have had no
skill scores: the eight-skill model (MC-0030) scores outfield players only. Owner's choice
(2026-10-22): three keeper skills, on keepers' pages and as Players-list sorts.

## The change

In `thecornerfc/models/player_ratings.py`, `skill_scores` (nothing in the ranks reads it):

- **Shot-stopping**: save % over the rating window (saves / (saves + goals conceded)).
- **Goals prevented**: his team's xG conceded per match while he played, minus the goals he
  conceded per 90, over the rating window. The data has no post-shot xG, so this credits the
  defence in front of him as well as the keeper; the site says so.
- **Distribution**: pass accuracy over the rating window.

Each is standardised against the keepers with `SKILL_SAMPLE_MINUTES` or more in the window, moved
by the same one-way level pull as the outfield skills (MC-0033), pulled towards the prior with few
minutes as the outfield skills are, then a percentile among those keepers: 0 to 100. A keeper has
these three and no outfield skills; an outfield player has none of these.

On the site: a keeper's page shows the three, with the share of his rank where one counts
(save % 50%, pass accuracy 25%; his rank uses goals conceded per 90, not goals prevented); the
Players list can sort by each (a migration adds the three sort keys to `site_players`).

## The report (`report.py`)

On production, read-only, no API calls. One run as changed and one as the file was at the base
commit (read from git, checked against its fingerprint).

**It must hold before release:** every rank, season rank, position rank, projection and predicted
XI identical, base against changed (the data outputs, compared by name).

Reported alongside: the three scores of Alisson, D. Raya, T. Courtois, J. Pickford and G. Donnarumma;
the top ten keepers in each skill; how many keepers are scored.

## Cost

No new data, no API calls; three more keys in players.skills for about 1,000 keepers (a few
kilobytes).
