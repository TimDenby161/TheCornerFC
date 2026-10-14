# Club ranking

This is based on the Club Ranking Google Sheet. Every finished fixture is replayed oldest first, ordered by kickoff time, with the fixture ID breaking ties. For each fixture:

- Expected goal difference = (home rank − away rank + 30) / 100
- Result = actual goal difference, capped at ±3. When both teams have **xG** for the match, result = 30% capped goal difference + 70% xG difference. When neither has xG but both have **shot counts** (shots inside the box, all shots, shots on target), result = 50% capped goal difference + 50% of the difference in xG estimated from the shots (`SHOTS_XG`).
- Rank change = (result − expected goal difference) × K × the club's **new-club factor**, where K is 6, 10 for matches with xG and 10 for matches with shots only. The factor is 1 + 0.5 × e^(−matches the club has played / 40): 1.5 for a club's first match, 1.18 after 40, close to 1 after 120.
- One-off curtain-raisers count for a third: the rank change is × 1/3 for the **Community Shield** and the **UEFA Super Cup** (`COMPETITION_WEIGHT`). Sides treat them as pre-season, so a result says less than a league match. The 1/3 is World Football Elo's friendly-to-World-Cup ratio. Only two or three of these games are played a year, too few to backtest a value.
- The home team gains its rank change and the away team loses its own. Each side's change uses its own new-club factor, so a new club meeting an established one moves further than the other side does.
- **Movers.** Before a league match in a different division of its own country, a club whose last league match in its old division was within 400 days is moved halfway to the average rank of the clubs now in the division it joins, and its whole history moves with it (so its 30 and 100 Ranking and LT ALGO move too).

This differs from the sheet, which uses (home × 1.09 − away) / 100, × 10 and no cap. Backtesting 2023–26 showed the ×1.09 gave 0.4–1.1 goals of home advantage, when the real figure is about 0.3 for every team. A smaller K and the goal cap also stop one freak result from swinging a rank. Prediction error fell from 1.77 to 1.68 goals per match. The settings are at the top of `thecornerfc/models/ranking.py`.

**Why xG is blended in.** xG exists from 2022/23, for about 35–50% of matches (the bigger leagues). Replaying the rankings and projections from 2024/25 onwards:

| Result used | Log loss, all matches | Log loss, matches with xG |
|---|---|---|
| Goals only (before) | 1.00046 | 1.00446 |
| xG only, K 10 | 0.99889 | 1.00085 |
| 30% goals + 70% xG, K 10 | 0.99834 | 0.99993 |

- The blend was better in 2023/24, 2024/25 and 2025/26 taken separately.
- Anything from 25–35% goals with K 10–11 scored about the same.
- An xG difference is much less noisy than a goal difference, so those matches take a bigger K.
- Capping the xG difference made it worse, and home advantage and K for matches without xG were best left as they were.

`team_rank_history.act_diff` still holds the actual goal difference.

**Tables and xG on the pages are the site's own (since October 2026).**
- **League tables** are worked out from the finished fixtures (`thecornerfc/publish/tables.py`). API-Football's standings supply only the shape: which clubs are in which group, and what a finishing place leads to. Which matches count for a group comes from the round names (the regular season, a cup's league or group stage, the Apertura or Clausura a group is named after). Level clubs are ordered by goal difference and goals scored, except in the competitions listed in `tables.ORDER` (wins first in Belgium and MLS; the matches between the level clubs in Italy, Russia, Ukraine, Andorra and Azerbaijan).
- **What results can't show is kept by hand** in `thecornerfc/publish/table_adjustments.json`, keyed `"<league id>:<season>"`: `{"points": {"<team id>": -4}}` for a deduction and `{"void": [<team id>]}` for a club whose results were annulled. The export logs a warning naming any club whose computed line differs from API-Football's, which is how a new deduction shows up. Checked against all 1,129 standings rows on 6 October 2026: played, won, drawn, lost, goals and points agreed everywhere except where API-Football's own table was behind the results (Kazakhstan, the Conference League).
- **xG on club pages and league tables** is `export.XG_FROM_SHOTS`, an estimate from each side's shot counts, shown with "≈". API-Football's xG still goes into the ratings and projections but is not published.

**On results alone.** The whole match model was replayed with nothing but dates, competitions, clubs and scores: no xG, no predicted line-ups, no injury lists (`experiments/results_only`, October 2026; 44,632 matches from 2024/25 onwards).

| Model | W/D/L log loss | Right result |
|---|---|---|
| As it runs | 0.99744 | 51.0% |
| Results only | 1.00046 | 50.8% |
| Always the base rates | 1.07016 | |

- Results alone keep 96% of the gain over the base rates. Nearly all of the loss is the xG (0.0026 of 0.0030); line-ups and injury lists together are worth 0.0006.
- The loss is about 0.006 to 0.009 in the biggest leagues, where xG, line-ups and injury lists exist, and close to nothing in cups and the leagues without xG.
- The club ratings keep their order (rank correlation 0.992) and move 9 points on average, 60 at most.
- K 6 is still the best K for goals alone: 4 to 10 were tried.
- The full tables are in `experiments/results_only/REPORT.md`.

**Attack, defence, home and away.** These are worked out alongside the rank from the same replay (`side_ratings` in `thecornerfc/models/ranking.py`). They don't change the rank.
- **Attack and defence** average to the rank (Form), on the same scale. Expected home goals = the competition's average home goals + ((home attack − away defence) / 2 + 15) / 100, and the same the other way round for away goals. So 200 points of attack over the other side's defence is about one more goal. After each match, both sides move by 1.0 × (actual total goals − expected total) / 2: a club in high-scoring games drifts towards attack, one in low-scoring games towards defence. Goals are capped at 5 a side and blended with xG like the rank. Replaying 2024/25 onwards, this cut the error on total goals from 1.4205 to 1.4083. On its own, learning rates from 0.5 to 1 scored about the same; 1.0 was best for the projections. For example, Arsenal lean on defence and Barcelona and Bayern on attack.
- **Home and away** are the rank plus or minus the club's own home edge, on top of the standard 30 points. Both sides' edge moves by 0.2 × (result − expected), so a club doing better at home than away builds a positive edge. The gain was small (goal-difference error 1.3220 → 1.3205). Most clubs' edges are within a few points, because home advantage is mostly the same for everyone.
- Stored after every match in `team_rank_history` (`attack_after`, `defence_after`, `home_after`, `away_after`, plus `split_before`, `edge_before` and `goal_base` going into it, for the projections) and for now in `team_rankings` (`attack`, `defence`, `home_rating`, `away_rating`). The club page and team popup show them.
- The projections use them (see Match predictions). The attack learning rate (1.0) was tuned with the projections on 2023/24.

**Line-ups in the rank update: tested, not used.** The idea: when a club starts a weaker XI than usual and loses, its rank should fall less. The expected goal difference in the update was shifted by the starting XI rating against the club's usual one (actual − recent XI rating), for the 13 leagues with line-up ratings. Replaying every fixture and scoring 2024/25 onwards with line-up-free forecasts, it didn't help: log loss 1.00490 with no shift, 1.00496, 1.00513 and 1.00579 with shifts of 0.06, 0.12 and 0.24 goals per XI point. Goal-difference error was 1.6676 at best, with no shift. Rotation does matter at the extremes: a side starting an XI 4–8 points weaker than its opponent's shortfall does about 0.2 goals worse. But only about 4% of line-up-rated matches have gaps that big. A squad player's rank is built from his club's level too, so reserves rate close to starters. The XI gap's spread is only 1.9 points (about 0.08 goals). The pre-match predicted XI gap also cut goal-difference error by only 0.1% out of sample (1.6299 → 1.6284), in line with the prediction backtests further down.

**Why movers, new clubs and shots (MC-0028, released October 2026).** The rank is zero-sum inside a match, so a club changing division used to carry its rank unchanged and a club with five matches behind it moved as slowly as one with five hundred; and 40% of matches have shot counts but no xG, so they moved the rank on the score alone. Each was chosen on 2022-07 to 2024-06 and scored on 2024-07 to 2026-10 (`experiments/rating_dynamics`, `experiments/shots_proxy`); together, log loss 0.0012 better (95% 0.0006 to 0.0018), better in each season. That period had been looked at before, so the release is being checked on live matches against the version it replaced (protocol P16, `experiments/club_rank_release/DESIGN.md`), which can flag it for reverting.

A team's first rank is `leagues.starting_rank` of the first league it plays in. For a team that only ever appears in cups, it's the `starting_rank` of the first cup it plays in.

- `team_rank_history` holds each team's rank before and after every match, like the Ranking Breakdown tab.
- `team_rankings` holds the current summary, like the Ranking tab: current rank, 30 and 100 Ranking, ST ALGO, LT ALGO, and HG/HA/AG/AA over the last 12 months.
- `team_rankings` also has a `reliability` score from 0 to 100, which isn't in the sheet:
  - It's mainly driven by games played: a team scores 66% after 38 games, 89% after 76 and 96% after 114.
  - It's reduced when a team's rank swings a lot. `rank_volatility` is the standard deviation of the team's last 30 per-match rank changes, measured at K 6: each match counts its miss (result − expected goal difference) × 6, whatever its K, weight or new-club factor. That way it measures how surprising a team's results are, not the size of the step. At 10.5 or below (about 78% of teams) there's no reduction. Above that the score falls with the cube: 11.8 gives ×0.70 and 14 gives ×0.42.
  - The constants are at the top of `thecornerfc/models/ranking.py`.

```bash
python -m thecornerfc rank   # the nightly job runs this after syncing
```

Every run replays all fixtures from scratch, which takes seconds. Late results, corrected scores and changes to `starting_rank` are all picked up automatically.
