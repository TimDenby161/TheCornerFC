# Defensive contributions and a bonus check, from FPL's own results

Written 2026-09-29, before the FPL results were looked at. The owner approved this use of captured FPL results the same day (README, FPL section). Data: FPL's final (`data_checked`) results for 2026/27 GW1–5, matched to API-Football stat lines through `fpl_id_map_current`. The extract is read-only (`extract.py`).

## Defensive contributions (DC)

FPL rule: 2 points when a player's count reaches the threshold in a match. Defenders need 10 clearances, blocks, interceptions and tackles (CBIT). Midfielders and forwards need 12 of those plus recoveries (CBIRT). Goalkeepers can't score them. FPL's `defensive_contribution` stat is the count, and `explain` holds the points.

API-Football has tackles, blocks and interceptions but no clearances or recoveries. So the model maps a player's API rate onto FPL's count:

- **API rate:** his (tackles + blocks + interceptions) per 90 over his league appearances in the 365 days before kickoff, shrunk toward his position's rate with 900 pseudo-minutes. This is computed like the v1.2 rates, from API-Football only, so predictions never need FPL data.
- **Count in a match:** X ~ NegBin with mean (minutes / 90) × (c_pos + k_pos × API rate), and dispersion r_pos. c, k and r are fitted per FPL position by maximum likelihood on player-matches with minutes > 0.
- **Expected DC points:** 2 × [P(start) × P(X ≥ T | minutes as starter) + P(sub on) × P(X ≥ T | minutes as sub)], using v1.2's minutes model.

## Bonus check and rescaling

Compare FPL's real bonus with v1.2's reconstructed bonus on the same player-matches: the mean by FPL position, and the correlation. If they differ, v1.2's bonus betas are multiplied per position by (mean real / mean reconstructed), fitted on the fit split.

## Split and checks

- **Fit:** GW1–3. **Test:** GW4–5. The split is by gameweek, never by player.
- **Positions:** FPL's own.
- **DC checks on test, by position:**
  - Mean predicted DC points within ±15% of actual.
  - Brier score of P(DC) below a baseline of the position's fit-split DC rate among players with 60+ minutes × P(60+).
  - A 5-bin calibration table.
- **Bonus check on test:** mean predicted bonus (rescaled) against real, by position.

## Honest limits, stated up front

- The data is five gameweeks, about 1,500 player-matches with minutes, so parameters are noisy. Test is about 600 player-matches.
- The API rate says nothing about recoveries, so a midfielder's DC chance is driven by his tackles, blocks and interceptions only.
- Player inputs come from API-Football history (365 days); only the fitted constants come from FPL.
- The minutes model inside expected DC points is v1.2's, but c / k / r are fitted on actual minutes, not predicted.
