# Skill scores only where the position uses them

**Registered 2026-10-22, before `report.py` was run and before the model file was changed.** A
change to how the skill scores are shown, not to any rank. Owner's look over the live site
(T-061, 2026-10-22): V. van Dijk's finishing of 84 is "mental", and wingers and attacking
midfielders score 88 to 99 in solidity (M. Salah, B. Saka, C. Palmer). Both come from scoring every
skill against every outfield regular: most defenders score almost no goals, so a centre-back who
heads a few in beats many of them, and an attacker is rarely in a position to be dribbled past.
Neither skill counts in those players' ranks (their position's mix gives it no weight). Owner's
choice (2026-10-22): score a skill only where the position uses it.

## The change

In `thecornerfc/models/player_ratings.py`, `skill_scores` only (nothing in the ranks reads it):

- **The positions that use a skill** are the role groups whose `SKILL_MIX` gives it a share above 0.
- A player is **scored** in a skill only if his role group uses it; otherwise the skill is left
  out of his scores (the site shows "–", and lists sorted by the skill put him after those scored).
- His score is a **percentile among the listed outfield players with `SKILL_SAMPLE_MINUTES` or
  more whose role group uses the skill**, not among everyone. Everything before the percentile (the
  recipe, the league offsets of MC-0031, the level pull of MC-0033, the pull towards the prior) is
  as now.

So with today's mixes: finishing is not scored for centre-backs; dribbling not for holding
midfielders or centre-backs; solidity only for centre-backs, full-backs, wing-backs and holding
midfielders; ball-winning not for attacking midfielders, wingers or strikers; creating not for
centre-backs. When the owner changes a mix, the positions that use each skill follow it.

## The report (`report.py`)

On production, read-only, no API calls. One run of `compute_player_ratings` as changed and one as
the file was at the base commit (read from git, checked against its fingerprint), with the
database write and the line-up capture replaced.

**It must hold before release:** every rank, season rank, position rank, projection and predicted
XI identical, base against changed (the data outputs, compared by name).

Reported alongside: the seven scores of V. van Dijk, M. Salah, B. Saka, C. Palmer, H. Kane and
E. Haaland before and after; the top ten in solidity and in finishing after, with their positions;
how many listed players are scored in each skill before and after.

## Cost

No new data, no API calls, nothing new stored (players.skills keeps its shape, with fewer keys).
