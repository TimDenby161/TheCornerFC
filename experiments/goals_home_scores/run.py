"""Goals, home advantage and scorelines: the four remaining single hypotheses (DESIGN.md).

    goal_level    the projected total follows how many goals are actually being scored, overall
                  and (shrunk) by competition, instead of staying where 2023/24 left it
    league_home   home advantage by competition, learned as the seasons go and shrunk hard
                  towards the overall figure
    low_score     a Dixon-Coles term on the score grid for 0-0, 1-0, 0-1 and 1-1
    bivariate     a bivariate Poisson score grid (a shared goal component for the two sides)

Each learns only from matches on earlier days. Two stages:

    python experiments/goals_home_scores/run.py develop    # chooses settings on development
    python experiments/goals_home_scores/run.py final      # scores the final period once

Offline: reads experiments/research_frame/inputs.json.gz only. Needs numpy.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_frame"))
import frame  # noqa: E402

HERE = Path(__file__).parent
CHOSEN, OUT = HERE / "chosen.json", HERE / "results.json"
SELECTION_START = "2022-07-01"
FAMILY = 13
LEVEL = 1 - 0.05 / FAMILY
MIN_GAIN = 0.0001

GOAL_GRID = [dict(half_life=h, comp=c) for h in (60, 120, 240, 480) for c in (None, 100, 300)]
HOME_GRID = [dict(half_life=h, comp=c) for h in (180, 365, 730) for c in (None, 100, 300, 1000)]
RHO_GRID = tuple(round(-0.16 + 0.02 * i, 2) for i in range(12))            # -0.16 .. 0.06
SHARE_GRID = tuple(round(0.02 * i, 2) for i in range(0, 11))               # shared share of min(home, away)
INFLATION_GRID = (1.0, 1.02, 1.04, 1.06, 1.08, 1.1)
GLOBAL_PRIOR = 2000.0                    # matches of "no change" the overall figures start from


# ---- walk-forward running figures ------------------------------------------------------------

def running(data, value, weight, half_life, comp):
    """For every fixture, a figure from matches on earlier days only: the decayed sum of
    `value` over the decayed sum of `weight`, overall and (when comp is a number) by
    competition with `comp` pseudo-matches at the overall figure. value / weight are NaN for
    matches that don't count. Returns the figure for each fixture."""
    out = np.zeros(data.n)
    decay = 0.5 ** (1 / half_life)
    g_num, g_den = 0.0, 0.0
    c_num, c_den, c_day = {}, {}, {}
    mean_weight = float(np.nanmean(weight))
    days = data.ordinal
    order = np.arange(data.n)
    i = 0
    last_day = days[0]
    while i < data.n:
        day = days[i]
        j = i
        while j < data.n and days[j] == day:
            j += 1
        steps = day - last_day
        if steps:
            g_num *= decay ** steps
            g_den *= decay ** steps
            last_day = day
        overall = g_num / (g_den + GLOBAL_PRIOR * mean_weight)
        for r in order[i:j]:
            if comp is None:
                out[r] = overall
            else:
                c = data.league[r]
                f = decay ** (day - c_day.get(c, day))
                num, den = c_num.get(c, 0.0) * f, c_den.get(c, 0.0) * f
                out[r] = (num + comp * mean_weight * overall) / (den + comp * mean_weight)
        for r in order[i:j]:
            if np.isnan(value[r]):
                continue
            g_num += value[r]
            g_den += weight[r]
            if comp is not None:
                c = data.league[r]
                f = decay ** (day - c_day.get(c, day))
                c_num[c], c_den[c], c_day[c] = c_num.get(c, 0.0) * f + value[r], c_den.get(c, 0.0) * f + weight[r], day
        i = j
    return out


def goal_level(data, hx, ax, p):
    """Projected goals with the total scaled to recent scoring and the expected margin kept."""
    ok = data.scored
    pred_total = hx + ax
    actual = np.where(ok, data.ft_home + data.ft_away, np.nan)
    excess = running(data, actual - np.where(ok, pred_total, np.nan), np.where(ok, pred_total, np.nan), p["half_life"], p["comp"])
    total = pred_total * (1 + excess)
    d = hx - ax
    home = np.maximum((total + d) / 2, 0.05)
    away = np.maximum((total - d) / 2, 0.05)
    return home, away


def league_home(data, hx, ax, p):
    """Projected goals with the margin moved by the competition's running home-side residual."""
    ok = data.scored
    resid = np.where(ok, (data.ft_home - data.ft_away) - (hx - ax), np.nan)
    by = running(data, resid, np.where(ok, 1.0, np.nan), p["half_life"], p["comp"])
    return frame.moved(hx, ax, by)


# ---- score grids -----------------------------------------------------------------------------

def boosted(g, exp_diff, inflation):
    """A score grid with its diagonal raised by production's draw boost and the rest rescaled,
    so its home / draw / away sums are production's result probabilities."""
    draw = np.einsum("nii->n", g)
    boost = 1 + (inflation - 1) * np.maximum(0.0, 1 - np.abs(exp_diff) / frame.DRAW_FADE_MARGIN)
    draw_adj = np.minimum(draw * boost, 0.9)
    eye = np.eye(frame.MAX_GOALS + 1, dtype=bool)
    out = g * ((1 - draw_adj) / (1 - draw))[:, None, None]
    out[:, eye] = g[:, eye] * (draw_adj / draw)[:, None]
    return out


def low_score_grid(hx, ax, rho, inflation):
    g = frame.grid(hx, ax).copy()
    if rho:
        g[:, 0, 0] *= 1 - hx * ax * rho
        g[:, 0, 1] *= 1 + hx * rho
        g[:, 1, 0] *= 1 + ax * rho
        g[:, 1, 1] *= 1 - rho
        g = np.clip(g, 1e-12, None)
        g /= g.sum(axis=(1, 2), keepdims=True)
    return boosted(g, hx - ax, inflation)


def bivariate_grid(hx, ax, share, inflation):
    """Bivariate Poisson with the two sides' means kept: a shared component of
    share x min(home, away) goals."""
    if not share:
        return boosted(frame.grid(hx, ax), hx - ax, inflation)
    l3 = share * np.minimum(hx, ax)
    p1, p2, p3 = frame.pmf(hx - l3), frame.pmf(ax - l3), frame.pmf(l3)
    n, m = len(hx), frame.MAX_GOALS + 1
    g = np.zeros((n, m, m))
    for k in range(m):
        g[:, k:, k:] += p3[:, k, None, None] * p1[:, :m - k, None] * p2[:, None, :m - k]
    g /= g.sum(axis=(1, 2), keepdims=True)
    return boosted(g, hx - ax, inflation)


def score_loss(g, data, rows):
    h = np.minimum(data.ft_home[rows], frame.MAX_GOALS).astype(int)
    a = np.minimum(data.ft_away[rows], frame.MAX_GOALS).astype(int)
    return -np.log(np.clip(g[np.arange(len(h)), h, a], 1e-15, 1))


def grid_outcomes(g):
    home = (g * frame._LOWER).sum(axis=(1, 2))
    draw = np.einsum("nii->n", g)
    return np.stack([home, draw, 1 - home - draw], axis=1)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baseline(data):
    hx, ax = frame.reprojected(data, frame.replay(data))
    return hx, ax


def goal_market_loss(data, hx, ax, rows):
    return frame.binary_log_loss(frame.goal_markets(hx[rows], ax[rows]), frame.goal_events(data, rows))


def result_loss(data, hx, ax, rows):
    return frame.log_loss(frame.outcome_probabilities(hx[rows], ax[rows]), data.result[rows])


# ---- develop ---------------------------------------------------------------------------------

def develop():
    data = frame.Data()
    hx, ax = baseline(data)
    select = data.development & (data.day >= SELECTION_START)
    report = {"selection_window": [SELECTION_START, frame.DEVELOPMENT_END], "selection_matches": int(select.sum()),
              "grids": {}, "chosen": {}}

    base_goal = goal_market_loss(data, hx, ax, select).mean()
    rows = []
    for p in GOAL_GRID:
        gh, ga = goal_level(data, hx, ax, p)
        rows.append({**p, "goal_markets_log_loss": float(goal_market_loss(data, gh, ga, select).mean() - base_goal),
                     "result_log_loss": float((result_loss(data, gh, ga, select) - result_loss(data, hx, ax, select)).mean())})
        print("goal_level", rows[-1], flush=True)
    best = min(rows, key=lambda r: r["goal_markets_log_loss"])
    report["grids"]["goal_level"] = rows
    report["chosen"]["goal_level"] = {"setting": {k: best[k] for k in ("half_life", "comp")},
                                      "selection_gain": -best["goal_markets_log_loss"],
                                      "chosen": -best["goal_markets_log_loss"] >= MIN_GAIN}

    base_result = result_loss(data, hx, ax, select).mean()
    rows = []
    for p in HOME_GRID:
        gh, ga = league_home(data, hx, ax, p)
        rows.append({**p, "result_log_loss": float(result_loss(data, gh, ga, select).mean() - base_result)})
        print("league_home", rows[-1], flush=True)
    best = min(rows, key=lambda r: r["result_log_loss"])
    report["grids"]["league_home"] = rows
    report["chosen"]["league_home"] = {"setting": {k: best[k] for k in ("half_life", "comp")},
                                       "selection_gain": -best["result_log_loss"],
                                       "chosen": -best["result_log_loss"] >= MIN_GAIN}

    sx, sa = hx[select], ax[select]
    base_score = score_loss(boosted(frame.grid(sx, sa), sx - sa, frame.DRAW_INFLATION), data, select).mean()
    report["production_selection_score_log_loss"] = float(base_score)
    for name, values, make, key in (("low_score", RHO_GRID, low_score_grid, "rho"), ("bivariate", SHARE_GRID, bivariate_grid, "share")):
        rows = []
        for v in values:
            for infl in INFLATION_GRID:
                g = make(sx, sa, v, infl)
                rows.append({key: v, "inflation": infl, "score_log_loss": float(score_loss(g, data, select).mean() - base_score),
                             "result_log_loss": float(frame.log_loss(grid_outcomes(g), data.result[select]).mean() - base_result)})
        best = min(rows, key=lambda r: r["score_log_loss"])
        print(name, best, flush=True)
        report["grids"][name] = rows
        # the hypothesis is the structural term: a best setting with that term at zero is the draw
        # boost alone, which experiments/ends_and_draws already tested, so nothing is chosen
        report["chosen"][name] = {"setting": {key: best[key], "inflation": best["inflation"]},
                                  "selection_gain": -best["score_log_loss"],
                                  "chosen": bool(best[key]) and -best["score_log_loss"] >= MIN_GAIN}
    report["evaluator_sha256"], report["frame_sha256"] = digest(__file__), digest(frame.__file__)
    CHOSEN.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report["chosen"], indent=1))


# ---- final -----------------------------------------------------------------------------------

def interval(diff, data, rows, level=LEVEL):
    return frame.paired_interval(diff, data.week[rows], level)


def by_season(diff, data, rows):
    seasons = data.season[rows]
    return {data.season_label(s): float(diff[seasons == s].mean()) for s in np.unique(seasons)}


def no_worse(diff, data, rows):
    leagues = data.league[rows]
    listed = [lg for lg in np.unique(leagues) if (leagues == lg).sum() >= 300]
    return [int(sum(diff[leagues == lg].mean() <= 0 for lg in listed)), len(listed)]


def label(primary, seasons, guards, share):
    mean, lo, hi = primary
    bar = {"primary_better_by_0.002": mean <= -0.002, "adjusted_interval_excludes_zero": hi < 0,
           "better_in_2024/25_and_2025/26": all(seasons.get(s, 1) < 0 for s in ("2024/25", "2025/26")),
           "no_guard_worse_by_0.0005": all(v <= 0.0005 for v in guards.values()),
           "60_percent_of_competitions_no_worse": share[1] > 0 and share[0] / share[1] >= 0.6}
    text = "meets the bar" if all(bar.values()) else "a real gain below the bar" if hi < 0 and mean < 0 else "no gain shown"
    return {"conditions": bar, "label": text}


def final():
    if not CHOSEN.exists():
        raise SystemExit("run `develop` first: chosen.json is missing")
    chosen = json.loads(CHOSEN.read_text())["chosen"]
    data = frame.Data()
    hx, ax = baseline(data)
    rows = data.final
    report = {"level": LEVEL, "family": FAMILY, "final_matches": int(rows.sum()), "chosen_sha256": digest(CHOSEN),
              "evaluator_sha256": digest(__file__), "frame_sha256": digest(frame.__file__), "candidates": {}}
    base_goal = goal_market_loss(data, hx, ax, rows)
    base_result = result_loss(data, hx, ax, rows)
    fx, fa = hx[rows], ax[rows]
    base_grid = boosted(frame.grid(fx, fa), fx - fa, frame.DRAW_INFLATION)
    base_score = score_loss(base_grid, data, rows)
    events = frame.goal_events(data, rows)
    base_lines = frame.binary_log_loss(frame.goal_markets_from_grid(base_grid, calibrated=True), events)

    def record(name, setting, primary_name, diff, guards, extra=None):
        c = {"setting": setting, "primary": primary_name, "primary_change": interval(diff, data, rows),
             "interval_95": interval(diff, data, rows, 0.95), "by_season": by_season(diff, data, rows),
             "competitions_no_worse": no_worse(diff, data, rows), "guards": guards, **(extra or {})}
        c["verdict"] = label(c["primary_change"], c["by_season"], guards, c["competitions_no_worse"])
        report["candidates"][name] = c
        m = c["primary_change"]
        print(f"{name:12s} {setting} {primary_name}: {m[0]:+.5f} ({m[1]:+.5f} to {m[2]:+.5f}) | by season "
              f"{ {k: round(v, 5) for k, v in c['by_season'].items()} } | guards { {k: round(v, 5) for k, v in guards.items()} } "
              f"| no worse {c['competitions_no_worse']} | {c['verdict']['label']}", flush=True)

    for name in ("goal_level", "league_home", "low_score", "bivariate"):
        entry = chosen[name]
        if not entry["chosen"]:
            report["candidates"][name] = {"setting": entry["setting"], "label": "nothing chosen on development; not scored"}
            print(name, "nothing chosen on development; not scored")
            continue
        s = entry["setting"]
        if name == "goal_level":
            gh, ga = goal_level(data, hx, ax, s)
            per_market = goal_market_loss(data, gh, ga, rows) - base_goal
            diff = per_market.mean(axis=1)
            guards = {"result_log_loss": float((result_loss(data, gh, ga, rows) - base_result).mean())}
            total = (data.ft_home + data.ft_away)[rows]
            extra = {"by_market": dict(zip(frame.GOAL_MARKETS, map(float, per_market.mean(axis=0)))),
                     "total_goals_by_season": {
                         data.season_label(se): {"actual": float(total[data.season[rows] == se].mean()),
                                                 "production": float((hx + ax)[rows][data.season[rows] == se].mean()),
                                                 "candidate": float((gh + ga)[rows][data.season[rows] == se].mean())}
                         for se in np.unique(data.season[rows])}}
            record(name, s, "mean log loss over the five goal markets", diff, guards, extra)
        elif name == "league_home":
            gh, ga = league_home(data, hx, ax, s)
            diff = result_loss(data, gh, ga, rows) - base_result
            guards = {m: float(v) for m, v in zip(frame.GOAL_MARKETS, (goal_market_loss(data, gh, ga, rows) - base_goal).mean(axis=0))}
            brier = frame.brier(frame.outcome_probabilities(gh[rows], ga[rows]), data.result[rows]) \
                - frame.brier(frame.outcome_probabilities(fx, fa), data.result[rows])
            record(name, s, "result log loss", diff, guards, {"brier": float(brier.mean())})
        else:
            make, key = (low_score_grid, "rho") if name == "low_score" else (bivariate_grid, "share")
            g = make(fx, fa, s[key], s["inflation"])
            diff = score_loss(g, data, rows) - base_score
            lines = frame.binary_log_loss(frame.goal_markets_from_grid(g, calibrated=True), events) - base_lines
            guards = {"result_log_loss": float((frame.log_loss(grid_outcomes(g), data.result[rows]) - base_result).mean()),
                      **{m: float(v) for m, v in zip(frame.GOAL_MARKETS, lines.mean(axis=0))}}
            h, a = data.ft_home[rows], data.ft_away[rows]
            cells = {}
            for sh, sa in ((0, 0), (1, 0), (0, 1), (1, 1), (2, 2)):
                cells[f"{sh}-{sa}"] = {"actual": float(((h == sh) & (a == sa)).mean()),
                                       "production": float(base_grid[:, sh, sa].mean()), "candidate": float(g[:, sh, sa].mean())}
            record(name, s, "exact-score log loss", diff, guards, {"scores": cells})
    OUT.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    {"develop": develop, "final": final}[sys.argv[1] if len(sys.argv) > 1 else ""]()
