# Fantasy v1.5: penalty takers

Written 2026-09-30, before fitting, for the owner to review. It uses API-Football data only. Takers come from match history, not FPL's `penalties_order`, so it needs no new FPL licensing approval.

## Why

v1.4's team goal total is the match model's λ, built from API-Football team xG, which includes penalties. At equal shots on target, a team's xG is 0.6–0.8 higher in Premier League matches where it won a penalty (2024-26). That total is shared across the squad by goals and shots on target per 90, and both include penalties. So a taker's penalties are spread over his teammates in proportion to their scoring. In 2025-26 penalties were 50% of Palmer's goals, 44% of Bruno Fernandes's and 36% of Thiago's. v1.4 gives most of that expected value to other players.

## What the data says (Premier League, 2024-07 to 2026-09, backfilled 2026-09-30)

- **Complete.** Penalties scored + missed equal the opponents' penalties committed every season: 83 in 2024-25, 92 in 2025-26 and 9 in 2026-27 so far. `penalties_won` undercounts (74 and 70), so it is not used.
- **Rate.** 0.115 penalties per team-match. Teams differ only a little: the spread between teams' rates is mostly noise, and the true variance implies about 134 pseudo-matches of shrinkage toward the league rate.
- **Conversion.** 83–84% per season.
- **Shots.** API-Football's shots and shots on target include penalty attempts: in all 174 player-matches with an attempt, shots ≥ attempts and shots on target ≥ penalties scored.
- **Takers are hard to predict from history alone.** Of 142 penalties where the team had an earlier taker, the last earlier taker who was on the pitch took it 68% of the time, and the most frequent taker in the last 12 months 66%. 31 went to a player who had never taken one for that team. In 16, the previous taker played 90 minutes and someone else took it.
- **Shared penalties are rare.** Only 1 team-match had two different takers.

## Model

Everything is v1.4's except goals, which split into non-penalty and penalty parts.

1. **Expected penalties for a team:** π = the league rate per team-match. The fit compares three candidates (below) and keeps one.
2. **Split the team total:** penalty goals = π × c, and non-penalty goals = max(λ × (1 − own-goal share) − π × c, 0). c is the league conversion rate. Penalties are taken *out of* the match model's λ, not added on top.
3. **Non-penalty goals** are shared as v1.4 shares goals, but by non-penalty evidence: his goals minus penalties scored, and his shots on target minus penalties scored. His team's per-90 totals get the same adjustment.
4. **Penalty goals** are shared by taker weight × expected minutes, with v1.4's `allocate`:

       weight_i = Σ over his team's earlier penalties taken by i of δ^(age in days / 365)  +  α × his non-penalty goal share

   The first term is his own recent record, decayed (δ is fitted). The α term covers the 22% of penalties that go to first-time takers: players who score more are likelier to take one when the usual taker is off. A player's record counts only for his current club. Weighting by expected minutes gives the backup the share the first-choice taker is expected to miss.
5. **Misses:** expected attempts × (1 − c), allocated the same way.

**Candidates for π**, compared on the fit seasons by Poisson log-likelihood of penalties won:
   - (a) the league rate;
   - (b) the league rate × his team's λ / the league mean λ, so attacking sides win more;
   - (c) his team's own rate, shrunk toward the league rate by a fitted number of pseudo-matches.

## Points and display

- **Penalty points** = goal points for his position × expected penalty goals − 2 × expected misses. FPL's −2 covers saved and missed penalties alike.
- **Goal points** become non-penalty only. The two add up to roughly v1.4's goal points for the team, minus the new miss term.
- **FPL tab breakdown.** `part_fields` gains `penalty` after `goal`. The breakdown shows two lines: "Goals (open play)" with expected non-penalty goals and their points, and "Penalties" with expected scored / missed and their points. The grid's goals column stays the total, so it still matches what FPL counts.
- **Snapshots** store the new parts plus each player's taker weight and inputs, so any prediction can be explained afterwards.

## Split and checks

- **Data:** Premier League player-matches from 2024-07 onwards, with each player's history as of kickoff (no look-ahead).
- **Fit:** α, δ and the π candidate on 2024-25. c is the 2024-25 league conversion rate.
- **Test:** 2025-26 plus 2026-27 to date. Each is conditioned on the team's actual goals, so this tests only who scores, not how many:
  1. **Taker log-loss:** for each penalty, −log of the predicted share of the player who took it, among players on the pitch. It must beat the last-taker rule (smoothed by the same α) and v1.4's implied share.
  2. **Scorer log-likelihood:** for each team-match with goals, the log-likelihood of who scored under v1.5's shares against v1.4's. This is the check that matters for points.
  3. **Calibration:** predicted against actual penalty goals for players grouped by taker weight.
- **Frozen v1.5:** refit on everything to date and saved in `thecornerfc/fantasy_params_v1_5.json`. It is captured beside v1.1, v1.3 and v1.4 under a new prospective protocol P11: v1.5 minus v1.4 on the same player-fixtures, goal + penalty points MAE and MSE, reported separately for players with a taker weight above 0.5. What the public tab shows is the owner's choice, as with v1.4.

## Honest limits, stated up front

- History has a ceiling. First-time takers (22%) and designated-taker changes are only covered by α. FPL's `penalties_order` would likely do better, but using it is a new use of FPL data and needs the owner's approval. It is not part of v1.5.
- There is no timing data (no match events). Whether the taker was on the pitch *when* the penalty was given is approximated by his expected minutes.
- Only about 90 penalties a season. α and δ will be noisy, and the fit set is one season.
- Assists for winning a penalty (FPL gives one when the penalty is scored) are not modelled. The assist part is v1.4's.
- Transfers reset a player's record: his penalties for a previous club do not count at a new one.

## Owner's decisions after review (2026-09-30), before fitting

- **FPL's penalty order is an input.** The owner approved this use of FPL data. `fpl.player_states` now stores `penalties_order` (db/migrations/20260930_fpl_penalty_order.sql). When FPL lists a team's takers, their shares blend with history's: FPL gets weight 0.75, and order k counts 0.15^(k−1). FPL's order has no history, so these weights are fixed here rather than fitted. P11 judges them.
- **An "FPL assists" part is added.** It covers the assists FPL awards that API-Football doesn't record:
  - winning a penalty a teammate scores: team penalty goals × (1 − the share won by the taker himself), shared by penalties won plus fouls drawn per 90;
  - everything else (rebounds, deflections): a rate per non-penalty goal fitted on FPL's captured GW results (FPL assists − API assists − penalty-won assists), shared by shots per 90.
  - This uses FPL results to fit one constant, as the defensive-contribution fit did. It is worth 3 points each.
- **v1.5 replaces v1.4 on the public FPL tab**, whatever the checks show. It is judged prospectively under P11.
- **The π candidates.** The model implements (a) and (b) (`lambda_power` 0 or fitted). The chosen one is the best on the test seasons. (c) is used only if it wins with shrinkage inside the grid.
