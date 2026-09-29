"""Backtest for the national team Elo (thecornerfc/nations.py). Offline: reads the public results
CSV only, never the database.

Every rated match is predicted from the ranks before it: expected goal difference = exp_diff.
Scored on matches between FIFA members that both have MIN_PRIOR earlier rated matches:
RMSE and MAE of the goal difference, and W/D/L log loss (an ordered logistic on exp_diff, its
two cut-points fitted on the tuning years). Tuned on TUNE years, checked on TEST years.

    python experiments/nations_elo/run.py            # grid, writes results.json
"""
import itertools
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from thecornerfc import nations

TUNE = ("2000", "2014")
TEST = ("2014", "9999")
MIN_PRIOR = 30
# Final grid. Earlier, wider runs (K 10-30, home 20-50, cap 3-4) all had their best at an edge.
GRID = {"k": (4, 5, 6, 8), "home_adv": (40, 50, 60), "cap": (3, 6, 8, 99),
        "friendly": (0.5, 0.75, 1.0), "finals": (1.0, 1.25)}


def predictions(matches, fifa, **p):
    weights = {"finals": p["finals"], "competitive": 1.0, "friendly": p["friendly"]}
    seen, out = {}, []

    def on_match(m, h, a, exp_diff):
        prior = min(seen.get(m.home, 0), seen.get(m.away, 0))
        seen[m.home] = seen.get(m.home, 0) + 1
        seen[m.away] = seen.get(m.away, 0) + 1
        if prior >= MIN_PRIOR and m.home in fifa and m.away in fifa and m.day >= TUNE[0]:
            out.append((m.day, exp_diff, m.home_goals - m.away_goals))

    nations.replay(matches, k=p["k"], home_adv=p["home_adv"], cap=p["cap"], weights=weights, on_match=on_match)
    return out


def _cdf(x):
    return 1 / (1 + math.exp(-x))


def logloss(rows, cuts):
    lo, hi, scale = cuts
    total = 0.0
    for _, e, gd in rows:
        p_away = _cdf(lo - scale * e)
        p_home = 1 - _cdf(hi - scale * e)
        p = p_home if gd > 0 else p_away if gd < 0 else 1 - p_home - p_away
        total -= math.log(max(p, 1e-12))
    return total / len(rows)


def fit_cuts(rows):
    best = None
    for scale in (0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0):
        for lo in [x / 20 for x in range(-20, 1)]:
            for hi in [x / 20 for x in range(0, 21)]:
                ll = logloss(rows, (lo, hi, scale))
                if best is None or ll < best[0]:
                    best = (ll, (lo, hi, scale))
    return best[1]


def score(rows, cuts=None):
    n = len(rows)
    return {"n": n, "rmse": math.sqrt(sum((gd - e) ** 2 for _, e, gd in rows) / n),
            "mae": sum(abs(gd - e) for _, e, gd in rows) / n,
            **({"logloss": logloss(rows, cuts)} if cuts else {})}


def split(rows, period):
    return [r for r in rows if period[0] <= r[0] < period[1]]


def main():
    matches = nations.parse_csv(nations.download())
    fifa = nations.members(matches)
    results = []
    for values in itertools.product(*GRID.values()):
        p = dict(zip(GRID, values))
        rows = predictions(matches, fifa, **p)
        results.append({**p, "tune": score(split(rows, TUNE))})
    results.sort(key=lambda r: r["tune"]["rmse"])
    for r in results[:10]:
        print({k: v for k, v in r.items() if k != "tune"}, round(r["tune"]["rmse"], 4))

    # The chosen values and the old World-Football-Elo-like weights, with log loss, on both periods
    def full(p):
        rows = predictions(matches, fifa, **p)
        cuts = fit_cuts(split(rows, TUNE))
        return {**p, "cuts": cuts, "tune": score(split(rows, TUNE), cuts), "test": score(split(rows, TEST), cuts)}
    best = {k: v for k, v in results[0].items() if k in GRID}
    current = {"k": nations.K_FACTOR, "home_adv": nations.HOME_ADVANTAGE_POINTS, "cap": nations.MAX_GOAL_DIFF,
               "friendly": nations.TIER_WEIGHT["friendly"], "finals": nations.TIER_WEIGHT["finals"]}
    club_like = {"k": 6, "home_adv": 30, "cap": 3, "friendly": 1 / 3, "finals": 1.0}
    report = {"best_by_tune_rmse": full(best), "in_code": full(current), "club_values": full(club_like),
              "grid_top10": results[:10]}
    for name in ("best_by_tune_rmse", "in_code", "club_values"):
        r = report[name]
        print(name, {k: r[k] for k in GRID}, "tune", {k: round(v, 4) for k, v in r["tune"].items()},
              "test", {k: round(v, 4) for k, v in r["test"].items()})
    Path(__file__).with_name("results.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
