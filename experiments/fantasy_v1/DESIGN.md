# Fantasy v1: a deliberately simple FPL expected-points model

Written before any model output was looked at. Production formulas and database records stay unchanged: extraction is a read-only repeatable-read transaction, frozen inputs are cached locally, and the report holds aggregates only.

## What is and is not available

FPL capture is off pending the licensing decision (`FPL_CAPTURE_ENABLED`), and every FPL evidence table is empty. So **official FPL expected points, prices and official FPL points cannot be benchmarked or evaluated**. That is a result, not permission to pull FPL-derived data from elsewhere. Everything below uses API-Football data already in the database.

The target is therefore **reconstructed FPL points** from API-Football per-match stat lines under FPL scoring rules:

| Part | Rule used | Notes |
|---|---|---|
| Appearance | 1 if minutes > 0, +1 if ≥ 60 | exact |
| Goals | GK/DEF 6, MID 5, FWD 4 | position from API-Football, see below |
| Assists | 3 | API-Football assists are stricter than FPL's |
| Clean sheet | GK/DEF 4, MID 1; ≥ 60 minutes and the team conceded none | whole-match proxy for "while on the pitch" |
| Goals conceded | GK/DEF −1 per 2; ≥ 60 minutes | whole-match proxy |
| Saves | GK 1 per 3 | exact |
| Penalty saves, cards | +5, −1, −3 | target only, not modelled in v1 |
| Bonus, own goals, penalty misses, defensive contributions | not reconstructable | missing from target and model |

The primary target is the full reconstructable total (all rows above). The v1-scope target (without penalty saves and cards) is also reported.

**Position** is the player's most common API-Football position (G/D/M/F) over his appearances in that league season, standing in for FPL's fixed season position. Wingers that FPL lists as MID may be F here and the reverse. The same label is used by model and target.

**Gameweek** is API-Football's round (`Regular Season - n`). Rescheduled fixtures keep their original round, unlike FPL's double gameweeks.

## Model

Every component is computed per player per fixture from information before kickoff, and stored.

1. **Expected minutes (first class).** From the player's history in his team's previous league matches:
   - P(start): logistic on an exponentially weighted start rate over the team's last 10 matches, started last match, started the one before, and log(1 + team matches since his last appearance).
   - P(sub appearance | not started): logistic on the weighted sub-appearance rate, weighted start rate, sub last match, and the same gap.
   - Minutes when starting, P(≥ 60 | start) and minutes as a sub: his own averages over his last 20 starts / sub appearances, shrunk toward the position average with 5 pseudo-appearances.
   - Expected minutes = P(start) × minutes-as-starter + (1 − P(start)) × P(sub) × minutes-as-sub. P(play) and P(≥ 60) follow the same way.
   - The main model does **not** use injury lists: `injuries` rows carry no capture time (all rewritten 2026-09-23), so historical lists may include post-kickoff knowledge. An **availability variant** adds "listed missing" and "listed doubtful" to both logistics and is reported separately as timing-unverified.
2. **Team goal expectation** is the match model's pre-match `home_xg` / `away_xg`. For 2026/27 fixtures, use the latest prospective `match_prediction_snapshots` captured before kickoff where one exists, otherwise the stored `fixture_predictions` row. Before 2026 these are **reconstructions** by the current code, tuned on 2023/24, so they are not prospective.
3. **Goal allocation** uses attacking evidence, not overall Ability. Goal evidence = ½ goals + ½ (shots on target × league goals per shot on target). Each player's evidence per 90 over the last 365 days of league matches is divided by his team's evidence per match in the same window. The result is shrunk toward his role group's average (GK, CB, FB, DM, CM, AM, W, ST, from his most common starting role) by K pseudo-minutes. Expected goals = team λ × (1 − own-goal share) × (rate × expected minutes) / Σ over the squad of (rate × expected minutes). So the squad's expected goals add up to the match model's.
4. **Assist allocation** is the same, with assist evidence = ½ assists + ½ (key passes × league assists per key pass), and a team total of λ × league assists per goal.
5. **Clean sheet**: team P(CS) = e^(−λ against), the match model's own Poisson zero. Player CS expectation = P(≥ 60) × P(CS).
6. **Goals conceded** (GK/DEF): P(≥ 60) × E[⌊G/2⌋], with G ~ Poisson(λ against).
7. **Goalkeeper saves**: team saves ~ Poisson(a + b × λ against), with a and b fitted on training team-matches. GK expectation = expected minutes / 90 × E[⌊S/3⌋]. It is kept only if its validation calibration is clean: mean predicted within 10% of actual in each λ tercile. Otherwise it is dropped from v1 and the report says so.

Not modelled: bonus, cards, own goals, penalty misses and saves, BPS, defensive contributions.

**Universe**: each team-fixture's candidates are players who appeared for that team in the league within the previous 365 days, whose latest appearance in any covered league was for this team. New signings enter after their first appearance. The share of actual points scored outside the universe is reported.

## Splits and selection

- 2020/21: history only.
- Train: kickoffs from 2021-07-01 to before 2023-07-01. Fits the logistics, position averages, role priors and league ratios.
- Validation: 2023/24. Selects the start-rate decay from {0.5, 0.7, 0.85} on minutes MAE, then K from {450, 900, 1800} on total-points MAE.
- Parameters are then refitted on train + validation, frozen, and applied once to the test set.
- Test: 2024-07-01 onward (2024/25, 2025/26 and 2026/27 to date).

## Benchmarks (same rows)

- **Official FPL xP**: not evaluable (no captured FPL data).
- **Price**: not evaluable (no captured FPL data).
- **Points per game**: the player's reconstructed points per appearance this season before the fixture, or last league season's if he has no appearance yet this season, otherwise 0. As FPL's PPG does, it conditions on playing.
- **Recent average**: mean reconstructed points over his team's last 5 league matches, counting 0 when he did not play.
- **Ablation, flat team goals**: the full model with every λ replaced by the training-period league average for home or away. This isolates what the match model contributes.

## Metrics

On test, overall and by position, by ability band, by gameweek and by season:
- MAE and RMSE of points.
- Pearson and Spearman correlations.
- Top-N hit rate per round across all players: the share of the predicted top N whose actual points reach the actual N-th best, for N = 10, 25, 50. Mean actual points of the predicted top N. By position: top 5 GK, 10 DEF, 10 MID, 5 FWD.
- Minutes MAE, start calibration (10 bins, ECE, Brier) and clean-sheet calibration (team level, 10 bins, ECE). Mean-bias for every component.

**Ability band** stands in for price, because no price is captured. It is the player's latest `fixture_player_ranks` value before the fixture, in bands < 60, 60–70, 70–80 and ≥ 80. It is not price.

Uncertainty: differences against each benchmark use a paired cluster bootstrap over (season, round), with 2,000 draws. Intervals are pointwise and not adjusted for multiplicity. Segment results are exploratory.

## Success criteria (decided now)

Correlation alone is not success. v1 counts as validated for building on only if, on test:
1. MAE **and** RMSE are lower than both PPG and recent average, with 95% intervals of the difference excluding zero.
2. Mean prediction is within ±5% of mean actual for the v1-scope target overall and within ±10% in each position.
3. Start ECE ≤ 0.03 and team clean-sheet ECE ≤ 0.03.
4. The model beats the flat-team-goals ablation on MAE, so the match model earns its place.

Even when all four pass, this validates against *reconstructed* points only. It says nothing about beating official FPL xP or price, which need captured FPL data.
