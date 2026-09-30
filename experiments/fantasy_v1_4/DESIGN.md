# Fantasy v1.4: each player's own FPL defensive-contribution record

Written 2026-09-30, before fitting. The owner approved this use of captured FPL results the same day: each player's own FPL defensive-contribution (DC) counts become an input to his own prediction. The earlier approval covered only fitting constants per position (experiments/fantasy_dc/).

## Why

v1.3 predicts a player's FPL DC count from API-Football's tackles + blocks + interceptions. API-Football has no clearances or recoveries, so every player gets his position's average share of those through the intercept c. Clearance-heavy centre-backs are underrated. For example, Tarkowski averaged 10.2 over GW1–5 and reached 10 in 3 of 5 matches, but v1.3 expects 8.1 a match (a 32% chance).

## Model

v1.3's per-90 mean, μ = c_pos + k_pos × API rate, becomes a prior that the player's own FPL record updates, as in a gamma-Poisson model:

    μ' = (his FPL DC count + μ × m) / (his FPL minutes / 90 + m)

His record covers every FPL gameweek of the season finished before the prediction, for all clubs. m (pseudo-90s, shared by all positions) is fitted, and so is each position's NegBin dispersion r, since part of the spread between players is now explained. c and k are v1.3's. Everything else is v1.3's: the minutes model, thresholds, and 2 × [P(start) × P(X ≥ T | starter minutes) + P(sub on) × P(X ≥ T | sub minutes)].

## Split and checks

- Data: FPL's final GW1–5 results matched to API-Football, as in experiments/fantasy_dc/ (the same frozen extract).
- The record for a match in GW t uses GWs 1 to t − 1 only. GW1 has no record (μ' = μ).
- **Fit:** c, k and v1.3's r on GW1–3 (as fantasy_dc did). m and v1.4's r on GW2–3 by maximum likelihood, given actual minutes.
- **Test:** GW4–5, given actual minutes, for defenders and midfielders:
  1. Brier score of P(DC) below v1.3's, fitted on the same GW1–3.
  2. Mean P(DC) within ±15% of the actual rate.
  - Forwards are reported only: about one event in the test data.
- **Frozen v1.4:** v1.3's parameters, with m and r refitted on GW2–5, using v1.3's final c and k. It is shown on the FPL tab whatever the result (the owner's choice), and is judged by prospective snapshots like v1.1 and v1.3.

## Honest limits, stated up front

- Four gameweeks of records at most, so m is noisy and a player's record is at most about 5 matches.
- Transfers carry the record across clubs, and a new role at a new club may not match it.
- Double gameweeks add their counts and minutes together, which is fine for a rate.
