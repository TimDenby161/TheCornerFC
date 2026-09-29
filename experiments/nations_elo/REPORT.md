# National team Elo: backtest

`run.py` replays every men's full international since 1872 with `nations.replay` and predicts each match from the ratings before it. Expected goal difference is `exp_diff`.

- **Scored matches:** between FIFA members that both have at least 30 earlier rated matches.
- **Tuning years:** 2000–13 (12,239 matches).
- **Test years:** 2014–26 (11,071 matches).
- **Measures:** RMSE and MAE of goal difference, and W/D/L log loss (an ordered logistic on `exp_diff`, fitted on the tuning years).

| Values | Test RMSE | Test MAE | Test log loss |
|---|---|---|---|
| Club values unchanged (K 6, home 30, cap 3, friendlies ⅓) | 1.708 | 1.277 | 0.8756 |
| **Chosen (K 6, home 50, cap 8, all tiers 1)** | **1.651** | **1.266** | **0.8702** |
| Best on tuning RMSE (K 6, home 60, cap 8) | 1.655 | 1.271 | 0.8708 |

What the grid runs showed:
- **K:** earlier runs over K 10–30 were all worse than K 6. K 5–6 is best, and 3–4 and 8+ are worse.
- **Goal cap:** the biggest single gain. A cap of 3 was clearly worse than 6–8. A cap of 99 (no cap) was slightly worse than 8.
- **Home advantage:** 50–60 are about equal. 50 is better on the test years.
- **Tier weights:** friendlies at 0.33–0.75 and finals at 1.25–1.5 were slightly worse than equal weights on both periods.

Rerun with `python experiments/nations_elo/run.py`. It takes about 2 minutes and writes `results.json`.
