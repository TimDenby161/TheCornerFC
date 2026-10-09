"""Backtest for the national team projections (thecornerfc/models/national_predictions.py). Offline: reads
the public results CSV only, never the database.

Every rated match is projected from the ranks before it, as the club projections are built:
    exp_diff          = (home rank - away rank + home advantage unless neutral) / 100
    home_xg, away_xg  = predictions.project(base, base, exp_diff)   (base: a side's goals when level)
    W/D/L, over 2.5, both score: predictions.outcome_probabilities / goal_markets, unchanged
Scored as experiments/nations_elo: matches between FIFA members that both have MIN_PRIOR earlier
rated matches; base tuned on TUNE years, checked on TEST years. Compared with the ordered logistic
of nations_elo (W/D/L only) and with base-rate guessing.

Also tried: each side's own goal tendency (TENDENCY), the goals in its last FORM_GAMES matches
against what the ranks expected, shrunk by SHRINK games, moving the base.

    python experiments/nations_proj/run.py            # writes results.json
"""
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from thecornerfc.models import nations, predictions

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nations_elo"))
import run as elo_run   # noqa: E402  (the ordered logistic and its periods)

TUNE, TEST, MIN_PRIOR = elo_run.TUNE, elo_run.TEST, elo_run.MIN_PRIOR
BASES = (1.0, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.5)
FORM_GAMES, SHRINKS = 12, (6, 12, 24)


def rows(matches, fifa):
    """[(day, exp_diff, home goals, away goals, home recent, away recent)]: recent is a side's
    last FORM_GAMES rated matches before this one, each (total goals, size of its expected margin)."""
    seen, out = {}, []
    recent = defaultdict(lambda: deque(maxlen=FORM_GAMES))

    def on_match(m, h, a, exp_diff):
        prior = min(seen.get(m.home, 0), seen.get(m.away, 0))
        seen[m.home] = seen.get(m.home, 0) + 1
        seen[m.away] = seen.get(m.away, 0) + 1
        if prior >= MIN_PRIOR and m.home in fifa and m.away in fifa and m.day >= TUNE[0]:
            out.append((m.day, exp_diff, m.home_goals, m.away_goals,
                        list(recent[m.home]), list(recent[m.away])))
        for side in (m.home, m.away):
            recent[side].append((m.home_goals + m.away_goals, abs(exp_diff)))

    nations.replay(matches, on_match=on_match)
    return out


def projected(row, base, shrink=None):
    _, exp_diff, _, _, h_recent, a_recent = row
    b = base
    if shrink:
        # ratio of the goals in both sides' recent matches to what this model expected there
        got = sum(g for g, _ in h_recent + a_recent)
        exp = sum(math.sqrt(d * d + 4 * base * base) for _, d in h_recent + a_recent)
        n = len(h_recent) + len(a_recent)
        level = 2 * base
        b = base * ((got + level * shrink) / (exp + level * shrink)) if n else base
    return predictions.project(b, b, exp_diff)


def score(rows_, base, shrink=None, calibrated=True):
    n = len(rows_)
    ll = over = btts = se = 0.0
    for row in rows_:
        _, _, hg, ag, *_ = row
        hx, ax = projected(row, base, shrink)
        ph, pd, pa, _ = predictions.outcome_probabilities(hx, ax)
        ll -= math.log(max(ph if hg > ag else pd if hg == ag else pa, 1e-12))
        p_over, p_btts = predictions.goal_markets(hx, ax)
        if not calibrated:      # the grid's own chances, without the club calibration
            ph_, pa_ = predictions._pmf(hx), predictions._pmf(ax)
            under = sum(ph_[i] * pa_[j] for i in range(3) for j in range(3 - i)) / (sum(ph_) * sum(pa_))
            p_over = 1 - under
            p_btts = (1 - ph_[0] / sum(ph_)) * (1 - pa_[0] / sum(pa_))
        over -= math.log(max(p_over if hg + ag > 2.5 else 1 - p_over, 1e-12))
        btts -= math.log(max(p_btts if hg and ag else 1 - p_btts, 1e-12))
        se += ((hx - hg) ** 2 + (ax - ag) ** 2) / 2
    return {"n": n, "wdl": ll / n, "over25": over / n, "btts": btts / n, "goals_rmse": math.sqrt(se / n)}


def base_rates(tune, test):
    """Log loss of guessing the tuning years' rates on the test years."""
    def rate(f):
        return sum(f(r) for r in tune) / len(tune)
    def ll(p, f):
        return -sum(math.log(p if f(r) else 1 - p) for r in test) / len(test)
    home, draw = rate(lambda r: r[2] > r[3]), rate(lambda r: r[2] == r[3])
    wdl = -sum(math.log(home if r[2] > r[3] else draw if r[2] == r[3] else 1 - home - draw) for r in test) / len(test)
    over, both = (lambda r: r[2] + r[3] > 2.5), (lambda r: bool(r[2] and r[3]))
    return {"wdl": wdl, "over25": ll(rate(over), over), "btts": ll(rate(both), both)}


def main():
    matches = nations.parse_csv(nations.download())
    all_rows = rows(matches, nations.members(matches))
    tune, test = elo_run.split(all_rows, TUNE), elo_run.split(all_rows, TEST)
    r4 = lambda d: {k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}

    grid = sorted(({"base": b, "shrink": s, "tune": score(tune, b, s)} for b in BASES for s in (None, *SHRINKS)),
                  key=lambda g: g["tune"]["wdl"] + g["tune"]["over25"])
    for g in grid[:8]:
        print(g["base"], g["shrink"], r4(g["tune"]))
    flat = next(g for g in grid if g["shrink"] is None)
    best = grid[0]
    elo_rows = [(d, e, hg - ag) for d, e, hg, ag, *_ in all_rows]
    cuts = elo_run.fit_cuts(elo_run.split(elo_rows, TUNE))
    report = {
        "in_code": {"base": predictions_base(), "test": score(test, predictions_base()),
                    "test_uncalibrated_markets": score(test, predictions_base(), calibrated=False)},
        "best_flat": {"base": flat["base"], "tune": flat["tune"], "test": score(test, flat["base"])},
        "best_with_tendency": {"base": best["base"], "shrink": best["shrink"], "tune": best["tune"],
                               "test": score(test, best["base"], best["shrink"])},
        "ordered_logistic_wdl": {"cuts": cuts, "test": elo_run.logloss(elo_run.split(elo_rows, TEST), cuts)},
        "base_rates_test": base_rates(tune, test),
        "test_average_goals": sum(r[2] + r[3] for r in test) / len(test),
    }
    for k, v in report.items():
        print(k, json.dumps(v, default=str)[:400])
    Path(__file__).with_name("results.json").write_text(json.dumps(report, indent=1))


def predictions_base():
    from thecornerfc.models import national_predictions
    return national_predictions.LEVEL_GOALS


if __name__ == "__main__":
    main()
