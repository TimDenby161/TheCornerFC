"""Relearned calibration, and the four formula candidates that protocol P14 tracks (DESIGN.md).

    formula      the shot formula of protocol P13: the margin error regressed on five
                 differences of the two sides' last-ten shot and xG figures
    calibration  the expected margin's error relearned from production's own expected margin
                 (a curve, with a term for cups), and the goal total following recent scoring
                 (the goal level of experiments/goals_home_scores, at its registered setting)
    movers       the two rank changes of experiments/rating_dynamics at their registered
                 combined setting: a club changing division is moved towards it, a new club
                 moves faster
    combined     the three in turn: movers, then the formula, then the calibration, each fitted
                 on what the one before left

Everything is walk-forward. The regressions are refitted every 1 January and 1 July on scored
matches before that date; the goal level and the ranks learn from earlier days only.

One stage only:

    python experiments/relearned_calibration/run.py develop

It chooses the curve's setting on the selection window (2022-07-01 to 2024-06-30), reports each
candidate there and writes chosen.json. There is no `final` stage: none of these candidates is
scored on a match after 30 June 2024 here. Their test is prospective (P14). Offline: reads
experiments/research_frame/inputs.json.gz only. Needs numpy.
"""
import hashlib
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
EXPERIMENTS = HERE.parent
sys.path.insert(0, str(EXPERIMENTS / "research_frame"))
import frame  # noqa: E402
import features  # noqa: E402

CHOSEN = HERE / "chosen.json"
SELECTION_START = "2022-07-01"
FIRST_REFIT = "2022-01-01"               # six months of scored matches behind the first fit
MIN_GAIN = 0.0002                        # what the curve must add to the goal level to be chosen
RIDGE = 50.0                             # the formula's penalty, as registered in P13
FORMULA_PAIRS = (("xG difference", "h_xgd10", "a_xgd10"), ("shot difference", "h_shots10", "a_shots10"),
                 ("on-target difference", "h_sot10", "a_sot10"), ("in-box shot difference", "h_box10", "a_box10"),
                 ("goals minus xG", "h_luck10", "a_luck10"))
CURVE_GRID = [dict(years=y, ridge=r, curved=c, cups=k) for y in (2, 4, None) for r in (10.0, 100.0, 1000.0)
              for c in (False, True) for k in (False, True)]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def refit_dates(first, last_day):
    """Every 1 January and 1 July from `first` (one of them) up to and including last_day."""
    out, year, month = [], int(first[:4]), int(first[5:7])
    while f"{year}-{month:02d}-01" <= last_day:
        out.append(f"{year}-{month:02d}-01")
        year, month = (year + 1, 1) if month == 7 else (year, 7)
    return out


# ---- the stages: each takes projected goals and returns a shift of the expected margin --------

def _walk(data, X, resid, usable, blocks, end, ridge, years=None):
    """Ridge regression of resid on X (a constant is added), refitted at each date in blocks on
    usable matches before it (the last `years` years of them, when given) and applied to the
    fixtures from that date to the next. Returns (shift, {date: coefficients})."""
    shift, fitted = np.zeros(data.n), {}
    for start, stop in zip(blocks, list(blocks[1:]) + [end]):
        train = usable & (data.day < start)
        if years is not None:
            first = date.fromisoformat(start)
            train &= data.day >= first.replace(year=first.year - years).isoformat()
        test = (data.day >= start) & (data.day < stop)
        if not train.any() or not test.any():
            continue
        A = np.column_stack([X[train], np.ones(int(train.sum()))])
        beta = np.linalg.solve(A.T @ A + ridge * np.eye(A.shape[1]), A.T @ resid[train])
        shift[test] = np.column_stack([X[test], np.ones(int(test.sum()))]) @ beta
        fitted[start] = [float(b) for b in beta]
    return shift, fitted


def margin_error(data, hx, ax):
    return (data.ft_home - data.ft_away) - (hx - ax)


def formula_shift(data, feats, hx, ax, usable, blocks, end):
    """P13's formula: the five last-ten differences (a missing figure counts as zero)."""
    X = np.column_stack([np.nan_to_num(feats[h] - feats[a]) for _, h, a in FORMULA_PAIRS])
    return _walk(data, X, margin_error(data, hx, ax), usable, blocks, end, RIDGE)


def curve_columns(setting):
    return ["margin"] + (["margin x |margin|"] if setting["curved"] else []) + \
        (["cup", "cup x margin"] if setting["cups"] else []) + ["constant"]


def curve_shift(data, hx, ax, usable, blocks, end, setting):
    """The margin's error as a function of the margin itself, so mismatches are no longer flat."""
    m = np.nan_to_num(hx - ax)
    cols = [m]
    if setting["curved"]:
        cols.append(m * np.abs(m))
    if setting["cups"]:
        cup = (~data.is_league).astype(float)
        cols += [cup, cup * m]
    return _walk(data, np.column_stack(cols), margin_error(data, hx, ax), usable, blocks, end,
                 setting["ridge"], setting["years"])


def movers_shift(data, production_replay, rating_dynamics, change):
    """Goals of expected margin that the rank changes add: the candidate replay's match-rank gap
    less production's own, both at the near-kickoff weight."""
    rep = rating_dynamics.replay(data, {**rating_dynamics.OFF, **change})
    h, a = rep.match_rank()
    ph, pa = production_replay.match_rank()
    return ((h - a) - (ph - pa)) / 100


def moved(hx, ax, shift):
    """frame.moved, leaving fixtures with no projection as they are."""
    ok = ~np.isnan(hx)
    home, away = hx.copy(), ax.copy()
    home[ok], away[ok] = frame.moved(hx[ok], ax[ok], shift[ok])
    return home, away


def candidates(data, feats, hx, ax, rank_shift, usable, blocks, end, curve, goal_level, goals_home_scores):
    """{name: (home goals, away goals)} for every fixture, from projected goals hx / ax.
    curve is the chosen setting or None; goal_level the registered setting."""
    level = lambda h, a: goals_home_scores.goal_level(data, h, a, goal_level)

    def calibrated(h, a):
        if curve is None:
            return level(h, a), {}
        shift, fitted = curve_shift(data, h, a, usable, blocks, end, curve)
        return level(*moved(h, a, shift)), fitted

    out, detail = {}, {}
    shift, detail["formula"] = formula_shift(data, feats, hx, ax, usable, blocks, end)
    out["formula"] = moved(hx, ax, shift)
    out["calibration"], detail["calibration"] = calibrated(hx, ax)
    out["movers"] = moved(hx, ax, rank_shift)
    h, a = out["movers"]
    shift, detail["combined_formula"] = formula_shift(data, feats, h, a, usable, blocks, end)
    out["combined"], detail["combined_calibration"] = calibrated(*moved(h, a, shift))
    return out, detail


# ---- develop ---------------------------------------------------------------------------------

def measures(data, hx, ax, bx, ba, rows):
    y = data.result[rows]
    p, b = frame.outcome_probabilities(hx[rows], ax[rows]), frame.outcome_probabilities(bx[rows], ba[rows])
    d = frame.log_loss(p, y) - frame.log_loss(b, y)
    events = frame.goal_events(data, rows)
    goal = frame.binary_log_loss(frame.goal_markets(hx[rows], ax[rows]), events) \
        - frame.binary_log_loss(frame.goal_markets(bx[rows], ba[rows]), events)
    _, lo, hi = frame.paired_interval(d, data.week[rows], 0.95)
    return {"log_loss": float(d.mean()), "brier": float((frame.brier(p, y) - frame.brier(b, y)).mean()),
            "goal_markets": float(goal.mean()), "sd_per_fixture": float(d.std(ddof=1)),
            "sd_week_clustered": float((hi - lo) / 3.92 * np.sqrt(len(d)))}


def develop():
    data = frame.Data()
    rating_dynamics = load("p14_rating_dynamics", EXPERIMENTS / "rating_dynamics" / "run.py")
    goals_home_scores = load("p14_goals_home_scores", EXPERIMENTS / "goals_home_scores" / "run.py")
    movers = json.loads((EXPERIMENTS / "rating_dynamics" / "chosen.json").read_text())["chosen"]["combined"]["change"]
    level = json.loads((EXPERIMENTS / "goals_home_scores" / "chosen.json").read_text())["chosen"]["goal_level"]["setting"]

    rep = frame.replay(data)
    bx, ba = frame.reprojected(data, rep)
    feats = features.build(data, rep, bx, ba)
    usable = data.scored & ~np.isnan(bx)
    end = frame.DEVELOPMENT_END
    blocks = refit_dates(FIRST_REFIT, "2024-06-30")
    select = data.development & (data.day >= SELECTION_START)
    seasons = {data.season_label(s): data.development & (data.season == s) & (data.day >= FIRST_REFIT)
               for s in (2021, 2022, 2023)}
    loss = lambda h, a: float(frame.log_loss(frame.outcome_probabilities(h[select], a[select]), data.result[select]).mean())

    report = {"selection_window": [SELECTION_START, end], "selection_matches": int(select.sum()),
              "refitted_on": blocks, "production_selection_log_loss": loss(bx, ba),
              "registered_settings": {"movers": movers, "goal_level": level, "formula_ridge": RIDGE}}
    level_only = loss(*goals_home_scores.goal_level(data, bx, ba, level))
    report["goal_level_only_selection_log_loss"] = level_only
    grid = []
    for setting in CURVE_GRID:
        shift, _ = curve_shift(data, bx, ba, usable, blocks, end, setting)
        value = loss(*goals_home_scores.goal_level(data, *moved(bx, ba, shift), level))
        grid.append({**setting, "selection_log_loss": value})
        print("curve", grid[-1], flush=True)
    best = min(grid, key=lambda r: r["selection_log_loss"])
    chosen = level_only - best["selection_log_loss"] >= MIN_GAIN
    curve = {k: best[k] for k in ("years", "ridge", "curved", "cups")} if chosen else None
    report["curve_grid"] = grid
    report["curve"] = {"setting": curve, "selection_gain_over_goal_level": level_only - best["selection_log_loss"],
                       "chosen": chosen}

    rank_shift = movers_shift(data, rep, rating_dynamics, movers)
    out, detail = candidates(data, feats, bx, ba, rank_shift, usable, blocks, end, curve, level, goals_home_scores)
    report["candidates"] = {}
    for name, (hx, ax) in out.items():
        report["candidates"][name] = {"selection": measures(data, hx, ax, bx, ba, select),
                                      "by_season": {s: measures(data, hx, ax, bx, ba, rows)["log_loss"]
                                                    for s, rows in seasons.items()}}
        print(name, json.dumps(report["candidates"][name]), flush=True)
    report["coefficients_at_the_last_refit"] = {
        "formula": dict(zip([n for n, _, _ in FORMULA_PAIRS] + ["constant"], detail["formula"][blocks[-1]])),
        "curve": dict(zip(curve_columns(curve), detail["calibration"][blocks[-1]])) if curve else None}
    report["sha256"] = {"run.py": digest(__file__), "frame.py": digest(frame.__file__),
                        "features.py": digest(features.__file__),
                        "rating_dynamics/run.py": digest(EXPERIMENTS / "rating_dynamics" / "run.py"),
                        "goals_home_scores/run.py": digest(EXPERIMENTS / "goals_home_scores" / "run.py")}
    report["inputs_extracted_at"] = data.doc["extracted_at"]
    CHOSEN.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    {"develop": develop}[sys.argv[1] if len(sys.argv) > 1 else ""]()
