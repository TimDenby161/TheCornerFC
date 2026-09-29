# Defensive contributions and bonus check: result

Run 2026-09-29 (`results.json`). FPL 2026/27 GW1–5 results matched to API-Football lines: 926 player-matches with minutes in GW1–3 (fit) and 607 in GW4–5 (test); 5 unmatched.

## Bonus: the reconstruction holds up, so no rescaling

Real FPL bonus against v1.2's reconstructed bonus, on player-matches with minutes:

| Position | GW1–3 FPL / rebuilt | Corr | GW4–5 FPL / rebuilt | Corr |
|---|---|---|---|---|
| GK | 0.13 / 0.11 | 0.98 | 0.38 / 0.33 | 0.90 |
| DEF | 0.18 / 0.23 | 0.67 | 0.22 / 0.23 | 0.63 |
| MID | 0.26 / 0.22 | 0.81 | 0.14 / 0.17 | 0.83 |
| FWD | 0.30 / 0.33 | 0.92 | 0.36 / 0.36 | 0.92 |

Per-position scale factors fitted on GW1–3 made GW4–5 worse for three positions of four, so the differences are noise and v1.2's bonus is kept. Defenders correlate least, which fits the missing clearances and recoveries.

## Defensive contributions

FPL's count against API-Football's tackles + blocks + interceptions in the same match (GW1–3): defenders 5.9 vs 2.6 (corr 0.73), midfielders 5.1 vs 1.7 (0.79), forwards 2.5 vs 0.5 (0.58).

Test, GW4–5:

| Position | P(DC) given actual minutes: predicted / actual | Brier: model / baseline | Pre-match DC points, everyone predicted: predicted / actual |
|---|---|---|---|
| DEF | 0.199 / 0.207 (n 203) | **0.147 / 0.152** | 0.24 / 0.26 (n 305), −7% |
| MID | 0.083 / 0.089 (n 293) | **0.057 / 0.076** | 0.11 / 0.12 (n 426), −7% |
| FWD | 0.001 / 0.014 (n 71) | 0.014 / 0.014 | 0.001 / 0.020 (n 102): 1 event |

Defenders and midfielders pass both checks (within ±15%, and a Brier score below the baseline). Forwards fail the mean check on a single event, which is too few to read. Calibration is coarse: midfielders at a predicted 0.2–0.4 reach the threshold 44% of the time (n 34).

## v1.3

v1.3 is v1.2 plus defensive contributions, with c / k / r refitted on GW1–5 (`thecornerfc/fantasy_params_v1_3.json`). It is shown only as a local preview on the FPL tab. Everything past the design was seen before freezing, and five gameweeks is little data, so only prospective snapshots can validate it.
