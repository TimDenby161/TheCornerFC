# National team projections: backtest

`run.py` replays every men's full international since 1872 with `nations.replay` and projects each match from the ranks before it, the way `thecornerfc/national_predictions.py` does: the expected margin is the rank gap plus home advantage (none at a neutral ground), and `predictions.project` turns it into goals from what each of two level sides scores (`LEVEL_GOALS`). The chances, over 2.5 and both to score come from the club functions unchanged.

- **Scored matches:** as `experiments/nations_elo`: between FIFA members that both have at least 30 earlier rated matches.
- **Tuning years:** 2000–13 (12,239 matches).
- **Test years:** 2014–26 (11,071 matches).
- **Measure:** log loss, lower is better.

| On the test years | W/D/L | Over 2.5 | Both to score | Goals RMSE |
|---|---|---|---|---|
| Guessing the tuning years' rates | 1.0522 | 0.6922 | 0.6816 | – |
| Ordered logistic on the margin (`nations_elo`) | 0.8702 | – | – | – |
| **In code: `LEVEL_GOALS` 1.1** | **0.8703** | **0.6724** | **0.6752** | **1.187** |
| With each side's goal tendency (not used) | 0.8697 | 0.6681 | 0.6732 | 1.183 |

What the runs showed:
- **`LEVEL_GOALS`:** 1.1 was best on the tuning years, and 1.0 to 1.2 scored about the same. 1.25 was worse on the test years (over 2.5: 0.6794).
- **W/D/L:** the Poisson grid with the club draw boost matches the ordered logistic fitted for the purpose.
- **Goal markets:** the club calibration of over 2.5 and both to score was kept. Without it over 2.5 was 0.6729 and both to score 0.6723, so neither is clearly better.
- **Goal tendency:** moving the level by the goals in both sides' last 12 matches, against what the model expected there, helped a little. It isn't used: the gain is small and it needs each side's recent matches at projection time.

Rerun with `python experiments/nations_proj/run.py`. It takes about 30 seconds and writes `results.json`.
