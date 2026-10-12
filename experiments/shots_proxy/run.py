"""Shots as a stand-in for xG: where a match has shot counts but no xG, does an xG estimated
from the shots improve the club rank? (DESIGN.md)

    shots      matches without xG but with shot counts move the rank on a blend of the capped
               goal difference and the estimated xG difference, with their own K

Two stages:

    python experiments/shots_proxy/run.py develop    # fits the estimate, chooses the blend and K
    python experiments/shots_proxy/run.py final      # scores the final period once

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
RATING_CHOSEN = HERE.parent / "rating_dynamics" / "chosen.json"
SELECTION_START = "2022-07-01"
FAMILY = 14                              # the thirteen of REGISTER.md and this one
LEVEL = 1 - 0.05 / FAMILY
LEAGUE_WINDOW = 400
GRID = [dict(goals_weight=g, k=k) for g in (0.3, 0.5, 0.7) for k in (6.0, 7.0, 8.0, 9.0, 10.0)]
NO_PROXY = dict(goals_weight=1.0, k=frame.PRODUCTION["k"])
NO_MOVE = dict(pull=0.0, boost=0.0, tau=20.0)


def fit_estimate(data):
    """Least squares of a side's xG on its shots inside the box, outside it and on target, over
    development matches that have both. Returns (coefficients, rows used, R^2)."""
    rows = (data.day < frame.DEVELOPMENT_END) & ~np.isnan(data.home_xg) & ~np.isnan(data.home_box) \
        & ~np.isnan(data.home_shots) & ~np.isnan(data.home_sot) & ~np.isnan(data.away_box) & ~np.isnan(data.away_xg)
    X = np.concatenate([_design(data.home_box[rows], data.home_shots[rows], data.home_sot[rows]),
                        _design(data.away_box[rows], data.away_shots[rows], data.away_sot[rows])])
    y = np.concatenate([data.home_xg[rows], data.away_xg[rows]])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    r2 = 1 - ((y - X @ beta) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return beta, int(rows.sum()), float(r2)


def _design(box, shots, on_target):
    return np.column_stack([box, shots - box, on_target, np.ones(len(box))])


def estimated(data, beta):
    """(home, away) estimated xG for every fixture; NaN where a shot count is missing."""
    h = np.maximum(_design(data.home_box, data.home_shots, data.home_sot) @ beta, 0.0)
    a = np.maximum(_design(data.away_box, data.away_shots, data.away_sot) @ beta, 0.0)
    return h, a


def replay(data, beta, p, move=NO_MOVE):
    """Production's replay, with proxy matches (no xG, shots on both sides) blended and stepped
    by p. `move` adds the movers pull and the new-club boost of experiments/rating_dynamics,
    for the descriptive stack only."""
    start, _, _ = frame.starting_ranks(data)
    s = frame.PRODUCTION
    eh, ea = estimated(data, beta)
    cur, hist, sums, played = {}, {}, {}, {}
    league_of, seen_on, members = {}, {}, {}
    out = frame.Replay(data.n)
    hfa, cap, gw = s["home_advantage"], s["max_goal_diff"], s["goals_weight"]
    pull, boost, tau = move["pull"], move["boost"], move["tau"]
    used = 0
    for i in range(data.n):
        th, ta, day = data.home[i], data.away[i], data.ordinal[i]
        for t in (th, ta):
            if t not in cur:
                cur[t] = start[t]
                hist[t] = [cur[t]]
                sums[t] = [0.0, cur[t]]
                played[t] = 0
        if data.is_league[i]:
            here = data.league[i]
            for t in (th, ta):
                was = league_of.get(t)
                if was == here:
                    continue
                if was is not None:
                    members[was].discard(t)
                    if pull and members.get(here) and day - seen_on[t] <= LEAGUE_WINDOW \
                            and data.leagues[was]["country"] == data.leagues[here]["country"]:
                        by = pull * (sum(cur[m] for m in members[here]) / len(members[here]) - cur[t])
                        cur[t] += by
                        hist[t] = [v + by for v in hist[t]]
                        total, run = 0.0, [0.0]
                        for v in hist[t]:
                            total += v
                            run.append(total)
                        sums[t] = run
                members.setdefault(here, set()).add(t)
                league_of[t] = here
            seen_on[th] = seen_on[ta] = day
        h, a = cur[th], cur[ta]
        out.h_now[i], out.a_now[i] = h, a
        out.h_lt[i], out.a_lt[i] = frame._lt(hist[th], sums[th]), frame._lt(hist[ta], sums[ta])
        out.h_played[i], out.a_played[i] = len(hist[th]) - 1, len(hist[ta]) - 1
        exp_diff = (h - a + hfa) / 100
        capped = max(-cap, min(cap, data.home_goals[i] - data.away_goals[i]))
        if not (math.isnan(data.home_xg[i]) or math.isnan(data.away_xg[i])):
            result, k = gw * capped + (1 - gw) * (data.home_xg[i] - data.away_xg[i]), s["k_xg"]
        elif p["goals_weight"] < 1 and not (math.isnan(eh[i]) or math.isnan(ea[i])):
            result, k = p["goals_weight"] * capped + (1 - p["goals_weight"]) * (eh[i] - ea[i]), p["k"]
            used += 1
        else:
            result, k = capped, s["k"]
        surprise = (result - exp_diff) * frame.COMPETITION_WEIGHT.get(data.league[i], 1.0)
        kh = ka = k
        if boost:
            kh, ka = k * (1 + boost * math.exp(-played[th] / tau)), k * (1 + boost * math.exp(-played[ta] / tau))
        cur[th], cur[ta] = h + surprise * kh, a - surprise * ka
        for t in (th, ta):
            hist[t].append(cur[t])
            sums[t].append(sums[t][-1] + cur[t])
            played[t] += 1
    out.proxy_matches = used
    return out


def predict(data, beta, p, move=NO_MOVE):
    hx, ax = frame.reprojected(data, replay(data, beta, p, move))
    ok = ~np.isnan(hx)
    probs = np.full((data.n, 3), np.nan)
    probs[ok] = frame.outcome_probabilities(hx[ok], ax[ok])
    return hx, ax, probs


def loss(data, probs, rows):
    return float(frame.log_loss(probs[rows], data.result[rows]).mean())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kinds(data):
    """Each fixture's own data: xG, shots without xG, or neither."""
    has_xg = ~np.isnan(data.home_xg) & ~np.isnan(data.away_xg)
    has_shots = ~np.isnan(data.home_box) & ~np.isnan(data.away_box) & ~np.isnan(data.home_shots) \
        & ~np.isnan(data.away_shots) & ~np.isnan(data.home_sot) & ~np.isnan(data.away_sot)
    return has_xg, has_shots & ~has_xg, ~has_xg & ~has_shots


def develop():
    data = frame.Data()
    beta, n, r2 = fit_estimate(data)
    select = data.development & (data.day >= SELECTION_START)
    _, _, base = predict(data, beta, NO_PROXY)
    base_loss = loss(data, base, select)
    has_xg, proxy, neither = kinds(data)
    report = {"estimate": {"per shot inside the box": float(beta[0]), "per shot outside the box": float(beta[1]),
                           "per shot on target": float(beta[2]), "constant": float(beta[3]), "matches": n, "r2": r2},
              "selection_matches": int(select.sum()), "production_selection_log_loss": base_loss,
              "share_of_matches": {"selection": {"xG": float(has_xg[select].mean()), "shots, no xG": float(proxy[select].mean()),
                                                 "neither": float(neither[select].mean())},
                                   "all fixtures": {"xG": float(has_xg.mean()), "shots, no xG": float(proxy.mean()),
                                                    "neither": float(neither.mean())}},
              "grid": []}
    for p in GRID:
        _, _, probs = predict(data, beta, p)
        d = frame.log_loss(probs[select], data.result[select]) - frame.log_loss(base[select], data.result[select])
        row = {**p, "selection_log_loss": float(d.mean()),
               "by_season": {data.season_label(s): loss(data, probs, data.development & (data.season == s))
                             - loss(data, base, data.development & (data.season == s)) for s in (2021, 2022, 2023)},
               "by_kind": {name: float(d[m[select]].mean()) for name, m in (("xG", has_xg), ("shots, no xG", proxy), ("neither", neither))}}
        report["grid"].append(row)
        print(row, flush=True)
    best = min(report["grid"], key=lambda r: r["selection_log_loss"])
    report["chosen"] = {"goals_weight": best["goals_weight"], "k": best["k"], "selection_gain": -best["selection_log_loss"]}
    report["evaluator_sha256"], report["frame_sha256"] = digest(__file__), digest(frame.__file__)
    report["beta"] = [float(b) for b in beta]
    CHOSEN.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("estimate", "share_of_matches", "chosen")}, indent=1))


def final():
    if not CHOSEN.exists():
        raise SystemExit("run `develop` first: chosen.json is missing")
    chosen = json.loads(CHOSEN.read_text())
    data = frame.Data()
    beta = np.array(chosen["beta"])
    p = {"goals_weight": chosen["chosen"]["goals_weight"], "k": chosen["chosen"]["k"]}
    rows = data.final
    bx, ba, base = predict(data, beta, NO_PROXY)
    hx, ax, probs = predict(data, beta, p)
    c = frame.compare(data, rows, base[rows], probs[rows], LEVEL)
    d = frame.log_loss(probs[rows], data.result[rows]) - frame.log_loss(base[rows], data.result[rows])
    c["interval_95"] = frame.paired_interval(d, data.week[rows], 0.95)
    events = frame.goal_events(data, rows)
    goal = frame.binary_log_loss(frame.goal_markets(hx[rows], ax[rows]), events).mean(axis=0) \
        - frame.binary_log_loss(frame.goal_markets(bx[rows], ba[rows]), events).mean(axis=0)
    c["goal_markets"] = dict(zip(frame.GOAL_MARKETS, map(float, goal)))
    has_xg, proxy, neither = kinds(data)
    c["by_kind"] = {name: {"n": int(m[rows].sum()), "log_loss": float(d[m[rows]].mean())}
                    for name, m in (("xG", has_xg), ("shots, no xG", proxy), ("neither", neither))}
    mean, lo, hi = c["log_loss"]
    seasons = [c["by_season"].get(s, {}).get("log_loss") for s in ("2024/25", "2025/26")]
    bar = {"log_loss_better_by_0.002": mean <= -0.002, "adjusted_interval_excludes_zero": hi < 0,
           "brier_agrees": c["brier"][0] < 0, "better_in_2024/25_and_2025/26": all(s is not None and s < 0 for s in seasons),
           "no_goal_market_worse_by_0.0005": all(v <= 0.0005 for v in c["goal_markets"].values()),
           "60_percent_of_competitions_no_worse": c["competitions_no_worse"][0] / c["competitions_no_worse"][1] >= 0.6}
    c["verdict"] = {"conditions": bar, "label": "meets the bar" if all(bar.values()) else
                    "a real gain below the bar" if hi < 0 and mean < 0 else "no gain shown"}
    report = {"level": LEVEL, "family": FAMILY, "final_matches": int(rows.sum()), "setting": p,
              "chosen_sha256": digest(CHOSEN), "evaluator_sha256": digest(__file__), "frame_sha256": digest(frame.__file__),
              "shots": c}
    print(f"shots {p}: final log loss {c['baseline']['log_loss']:.5f} -> {c['candidate']['log_loss']:.5f} ({mean:+.5f}, {lo:+.5f} to {hi:+.5f})"
          f" | 95% {c['interval_95'][1]:+.5f} to {c['interval_95'][2]:+.5f} | Brier {c['brier'][0]:+.5f} | leagues {c['leagues']['log_loss']:+.5f}"
          f" cups {c['cups']['log_loss']:+.5f} | no worse {c['competitions_no_worse']} | {c['verdict']['label']}")
    print("  by season", {k: round(v["log_loss"], 5) for k, v in c["by_season"].items()}, "| by kind", c["by_kind"],
          "| goal markets", {k: round(v, 5) for k, v in c["goal_markets"].items()})

    # Descriptive only, not a registered test: this change stacked on the rating_dynamics
    # combined setting, whose own final result was already known when this was written.
    if RATING_CHOSEN.exists():
        r5 = json.loads(RATING_CHOSEN.read_text())["chosen"]["combined"]["change"]
        move = {**NO_MOVE, **{k: v for k, v in r5.items() if k in NO_MOVE}}
        _, _, stacked = predict(data, beta, p, move)
        _, _, moved_only = predict(data, beta, NO_PROXY, move)
        ds = frame.log_loss(stacked[rows], data.result[rows]) - frame.log_loss(base[rows], data.result[rows])
        dm = frame.log_loss(moved_only[rows], data.result[rows]) - frame.log_loss(base[rows], data.result[rows])
        report["descriptive_stack"] = {
            "note": "not a registered comparison; the parts were chosen after their own final results were seen",
            "rating_setting": move, "rating_only": frame.paired_interval(dm, data.week[rows], 0.95),
            "shots_and_rating": frame.paired_interval(ds, data.week[rows], 0.95),
            "by_season": {data.season_label(s): float(ds[data.season[rows] == s].mean()) for s in np.unique(data.season[rows])}}
        print("  descriptive stack (95%):", report["descriptive_stack"])
    OUT.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    {"develop": develop, "final": final}[sys.argv[1] if len(sys.argv) > 1 else ""]()
