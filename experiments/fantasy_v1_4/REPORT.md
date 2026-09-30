# Fantasy v1.4: result

Run 2026-09-30 (`results.json`) on the frozen extract from experiments/fantasy_dc/: 1,433 matched FPL player-matches with minutes, GW1–5. v1.4 blends each player's own FPL defensive-contribution (DC) record into v1.3's per-90 mean (DESIGN.md).

## Test, GW4–5, given actual minutes

c, k and v1.3's r are fitted on GW1–3. m and v1.4's r are fitted on GW2–3, where the record is 1–2 gameweeks long.

| Position | n | Actual DC rate | v1.3 mean P | v1.4 mean P | Brier v1.3 | Brier v1.4 |
|---|---|---|---|---|---|---|
| DEF | 203 | 0.207 | 0.199 | 0.205 | 0.147 | **0.133** |
| MID | 293 | 0.089 | 0.083 | 0.086 | 0.057 | **0.053** |
| FWD | 71 | 0.014 | 0.001 | 0.001 | 0.014 | 0.014 |

Both pre-set checks pass for defenders and midfielders: a lower Brier score than v1.3, and a mean within ±15% of the actual rate. Forwards are reported only (one event).

## Frozen v1.4

m = 2.79 pseudo-90s, refitted on GW2–5 with v1.3's final c and k. r becomes 10.7 for DEF, 15.8 for MID and 23.0 for FWD (v1.3: 8.2 / 13.8 / 13.3). The dispersion falls because players' own records now explain part of the spread between them. Parameters: `thecornerfc/fantasy_params_v1_4.json`.

After 5 full matches, a player's own record carries 5 / (5 + 2.79) = 64% of the weight. Examples, for the next gameweek:

- Tarkowski (avg 10.2, 3 of 5 hits): DC points 0.59 → 0.82.
- Van Dijk: 0.29 → 0.63.
- The biggest rises are clearance-heavy centre-backs (Pinnock, Egan, Botman, Fofana).
- The biggest falls are full-backs and midfielders who tackle more than they clear (Dalot, Kadıoğlu, Le Fée).

## Limits

- This is a small backtest designed after seeing one player's case.
- m is fitted on records at most 4 gameweeks long.
- Prospective snapshots (P10) are the real test.
