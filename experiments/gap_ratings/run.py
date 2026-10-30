"""GAP ratings: opponent-adjusted shot and corner ratings in the boosted trees (DESIGN.md).

Builds Wheatcroft's GAP ratings (attack and defence, home and away, per statistic) for shots,
shots on target and corners in kickoff order, chooses each statistic's learning rates by how well
they predict the counts themselves on 2021/22 (no result is looked at), then refits A18's trees
walk-forward twice on identical matches: with A18's 44 features (the baseline) and with nine GAP
features added (the candidate). Scored on the development selection window and once on the final
period. A third fit without the corner ratings is descriptive.

Offline: reads experiments/research_frame/inputs.json.gz only, and A18's recipe from
experiments/architectures (chosen.json and its functions, imported, not changed). Needs numpy,
scipy, scikit-learn.

    python experiments/gap_ratings/run.py
"""
import hashlib
import importlib.util
import itertools
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "research_frame"))
import features  # noqa: E402
import frame  # noqa: E402

_spec = importlib.util.spec_from_file_location("architectures_run", ROOT / "experiments" / "architectures" / "run.py")
arch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(arch)

HERE = Path(__file__).parent
OUT = HERE / "results.json"

STATS = {"shots": ("home_shots", "away_shots"), "sot": ("home_sot", "away_sot"),
         "corners": ("home_corners", "away_corners")}
LAMBDAS = (0.02, 0.05, 0.1, 0.15, 0.2, 0.3)
PHIS = (0.5, 0.7, 0.9, 1.0)
TUNE = ("2021-07-01", "2022-07-01")
MIN_UPDATES = 3
SELECTION_START = "2022-07-01"
LEVEL = 0.99
A18_FINAL = -0.0027992457882088906          # experiments/architectures/results.json, gb
REPRODUCE_WITHIN = 0.0001
MIN_COMPETITION = 300
EUROPE = (2, 3, 848)


# ---- GAP ratings -----------------------------------------------------------------------------

def gap(data, home, away, lam, phi1, phi2):
    """Predicted (home count, away count) before every match from the ratings as they stood,
    NaN until both sides have MIN_UPDATES updates. data's fixtures are in kickoff order."""
    n = data.n
    ph, pa = np.full(n, np.nan), np.full(n, np.nan)
    HA, HD, AA, AD = {}, {}, {}, {}
    updates = defaultdict(int)
    sum_h = sum_a = 0.0
    count = 0
    for k in range(n):
        i, j = data.home[k], data.away[k]
        if updates[i] >= MIN_UPDATES and updates[j] >= MIN_UPDATES:
            ph[k] = (HA[i] + AD[j]) / 2
            pa[k] = (AA[j] + HD[i]) / 2
        si, sj = home[k], away[k]
        if np.isnan(si) or np.isnan(sj):
            continue
        if count:
            mh, ma = sum_h / count, sum_a / count
            for t in (i, j):
                if t not in HA:
                    HA[t], AD[t], AA[t], HD[t] = mh, mh, ma, ma
            ei = si - (HA[i] + AD[j]) / 2
            ej = sj - (AA[j] + HD[i]) / 2
            HA[i] = max(HA[i] + lam * phi1 * ei, 0.0)
            AA[i] = max(AA[i] + lam * (1 - phi1) * ei, 0.0)
            AD[j] = max(AD[j] + lam * phi2 * ei, 0.0)
            HD[j] = max(HD[j] + lam * (1 - phi2) * ei, 0.0)
            AA[j] = max(AA[j] + lam * phi1 * ej, 0.0)
            HA[j] = max(HA[j] + lam * (1 - phi1) * ej, 0.0)
            HD[i] = max(HD[i] + lam * phi2 * ej, 0.0)
            AD[i] = max(AD[i] + lam * (1 - phi2) * ej, 0.0)
            updates[i] += 1
            updates[j] += 1
        sum_h += si
        sum_a += sj
        count += 1
    return ph, pa


def tune(data, name):
    """λ, φ1, φ2 for one statistic: the lowest squared error of the predicted counts on TUNE."""
    h, a = (getattr(data, c) for c in STATS[name])
    window = (data.day >= TUNE[0]) & (data.day < TUNE[1]) & ~np.isnan(h) & ~np.isnan(a)
    grid = []
    for lam, p1, p2 in itertools.product(LAMBDAS, PHIS, PHIS):
        ph, pa = gap(data, h, a, lam, p1, p2)
        rows = window & ~np.isnan(ph)
        mse = float((((ph - h) ** 2 + (pa - a) ** 2)[rows]).mean() / 2)
        grid.append({"lambda": lam, "phi1": p1, "phi2": p2, "mse": mse, "n": int(rows.sum())})
    best = min(grid, key=lambda g: (round(g["mse"], 12), g["lambda"], -g["phi1"], -g["phi2"]))
    return best, grid


# ---- the bookmakers --------------------------------------------------------------------------

def market(data):
    """(n, 3) market probabilities from the last prices, NaN where no complete book exists."""
    books = defaultdict(dict)
    for fixture_id, bookmaker_id, selection, odd, *_ in data.doc["odds"]["rows"]:
        if odd:
            books[(fixture_id, bookmaker_id)][selection] = odd
    per_fixture = defaultdict(list)
    for (fixture_id, _), book in books.items():
        if all(s in book for s in ("Home", "Draw", "Away")):
            inv = np.array([1 / book["Home"], 1 / book["Draw"], 1 / book["Away"]])
            per_fixture[fixture_id].append(inv / inv.sum())
    p = np.full((data.n, 3), np.nan)
    for fixture_id, ps in per_fixture.items():
        k = data.index.get(fixture_id)
        if k is not None:
            m = np.mean(ps, axis=0)
            p[k] = m / m.sum()
    return p


# ---- measures --------------------------------------------------------------------------------

def probabilities(gh, ga, rows):
    p = np.full((len(gh), 3), np.nan)
    p[rows] = frame.outcome_probabilities(gh[rows], ga[rows])
    return p


def diff(data, rows, p_base, p_cand):
    d = frame.log_loss(p_cand[rows], data.result[rows]) - frame.log_loss(p_base[rows], data.result[rows])
    return d


def goal_markets(data, rows, base, cand):
    events = frame.goal_events(data, rows)
    b = frame.binary_log_loss(frame.goal_markets(base[0][rows], base[1][rows]), events).mean(axis=0)
    c = frame.binary_log_loss(frame.goal_markets(cand[0][rows], cand[1][rows]), events).mean(axis=0)
    return dict(zip(frame.GOAL_MARKETS, map(float, c - b)))


def segment(data, rows, mask, p_base, p_cand):
    m = rows & mask
    if not m.any():
        return {"n": 0}
    d = diff(data, m, p_base, p_cand)
    return {"n": int(m.sum()), "log_loss": frame.paired_interval(d, data.week[m], 0.95)}


def verdict(primary, dev_mean, goals):
    mean, lo, hi = primary["log_loss"]
    seasons = [primary["by_season"].get(s, {}).get("log_loss") for s in ("2024/25", "2025/26")]
    no_worse, listed = primary["competitions_no_worse"]
    checks = {"final_99_interval_below_zero": hi < 0,
              "development_better": dev_mean < 0,
              "final_brier_better": primary["brier"][0] < 0,
              "better_2024_25_and_2025_26": all(s is not None and s < 0 for s in seasons),
              "goal_markets_within_0.0005": all(v <= 0.0005 for v in goals.values()),
              "60_percent_of_competitions_no_worse": listed > 0 and no_worse / listed >= 0.6}
    if all(checks.values()):
        label = "passes the screen"
    elif hi < 0:
        label = "a real gain that misses the screen"
    else:
        label = "no gain shown"
    return {"checks": checks, "label": label, "size": "at least 0.002" if mean <= -0.002 else "under 0.002"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    t0 = time.time()
    chosen = json.loads(arch.CHOSEN.read_text())
    data = frame.Data()
    rep, hx, ax, base = arch.baseline(data)
    report = {"evaluator_sha256": digest(__file__), "frame_sha256": digest(frame.__file__),
              "features_sha256": digest(features.__file__), "architectures_sha256": digest(arch.__file__),
              "chosen_sha256": digest(arch.CHOSEN), "level": LEVEL, "gap": {}}

    # GAP ratings, tuned on the counts alone
    feats = features.build(data, rep, hx, ax)
    gap_names, no_corners = [], []
    for name, (hc, ac) in STATS.items():
        best, grid = tune(data, name)
        report["gap"][name] = {"chosen": best, "grid": grid}
        print("gap", name, best, flush=True)
        ph, pa = gap(data, getattr(data, hc), getattr(data, ac), best["lambda"], best["phi1"], best["phi2"])
        cols = [f"gap_h_{name}", f"gap_a_{name}", f"gap_d_{name}"]
        feats[cols[0]], feats[cols[1]], feats[cols[2]] = ph, pa, ph - pa
        gap_names += cols
        if name != "corners":
            no_corners += cols

    # the hierarchical Poisson model's margin and total, as A18 uses them
    lam, mu = arch.DC(data, **chosen["dc"]["setting"]).run(frame.BURN_IN_END, frame.FINAL_END)
    feats["dc_margin"], feats["dc_total"] = lam - mu - (hx - ax), lam + mu - (hx + ax)
    base_names = chosen["gb"]["features"]
    params, shrink = chosen["gb"]["params"], chosen["gb"]["shrink"]
    usable = data.scored & ~np.isnan(hx)

    def trees(names, blocks, end, train_rows, rows):
        dm, dt = arch.gb_fit_predict(data, feats, names, hx, ax, blocks, end, params, train_rows)
        gh, ga = arch.gb_apply(hx, ax, dm, dt, shrink)
        return gh, ga, probabilities(gh, ga, rows)

    # development selection window
    select = data.development & (data.day >= SELECTION_START)
    dev = {}
    for label, names in (("a18", base_names), ("a18_gap", base_names + gap_names)):
        dev[label] = trees(names, arch.GB_BLOCKS_DEV, frame.DEVELOPMENT_END, usable & data.development, select)
    d_dev = diff(data, select, dev["a18"][2], dev["a18_gap"][2])
    report["development"] = {"n": int(select.sum()),
                             "a18": float(frame.log_loss(dev["a18"][2][select], data.result[select]).mean()),
                             "a18_gap": float(frame.log_loss(dev["a18_gap"][2][select], data.result[select]).mean()),
                             "log_loss": frame.paired_interval(d_dev, data.week[select], 0.95)}
    print("development", report["development"], flush=True)

    # final period, scored once
    rows = data.final
    fin = {}
    for label, names in (("a18", base_names), ("a18_gap", base_names + gap_names),
                         ("a18_gap_no_corners", base_names + no_corners)):
        fin[label] = trees(names, arch.GB_BLOCKS_FINAL, frame.FINAL_END, usable, rows)
    p_a18, p_gap = fin["a18"][2], fin["a18_gap"][2]

    reproduced = frame.compare(data, rows, base[rows], p_a18[rows], 0.95)["log_loss"][0]
    report["reproduction"] = {"a18_vs_production": reproduced, "registered": A18_FINAL,
                              "valid": abs(reproduced - A18_FINAL) <= REPRODUCE_WITHIN}
    print("reproduction", report["reproduction"], flush=True)

    primary = frame.compare(data, rows, p_a18[rows], p_gap[rows], LEVEL)
    primary["log_loss_95"] = frame.paired_interval(diff(data, rows, p_a18, p_gap), data.week[rows], 0.95)
    goals = goal_markets(data, rows, fin["a18"][:2], fin["a18_gap"][:2])
    primary["goal_markets"] = goals
    report["final"] = primary
    report["verdict"] = verdict(primary, report["development"]["log_loss"][0], goals)
    report["vs_production"] = {
        "a18": frame.compare(data, rows, base[rows], p_a18[rows], 0.95),
        "a18_gap": frame.compare(data, rows, base[rows], p_gap[rows], 0.95)}
    covered = ~np.isnan(feats["gap_h_shots"])
    europe = np.isin(data.league, EUROPE)
    with_xg = ~np.isnan(data.home_xg)
    report["segments"] = {
        "gap_shot_ratings_for_both": segment(data, rows, covered, p_a18, p_gap),
        "no_gap_shot_ratings": segment(data, rows, ~covered, p_a18, p_gap),
        "europe": segment(data, rows, europe, p_a18, p_gap),
        "match_has_xg": segment(data, rows, with_xg, p_a18, p_gap),
        "match_has_no_xg": segment(data, rows, ~with_xg, p_a18, p_gap),
    }
    d_nc = diff(data, rows, p_a18, fin["a18_gap_no_corners"][2])
    report["no_corners_descriptive"] = {"log_loss": frame.paired_interval(d_nc, data.week[rows], 0.95)}

    # the bookmakers, descriptive
    pm = market(data)
    priced = rows & ~np.isnan(pm).any(axis=1)
    if priced.any():
        res = data.result[priced]
        report["market"] = {"n": int(priced.sum()),
                            "market": float(frame.log_loss(pm[priced], res).mean()),
                            "production": float(frame.log_loss(base[priced], res).mean()),
                            "a18": float(frame.log_loss(p_a18[priced], res).mean()),
                            "a18_gap": float(frame.log_loss(p_gap[priced], res).mean())}
    report["seconds"] = time.time() - t0
    OUT.write_text(json.dumps(report, indent=1) + "\n")
    m = primary["log_loss"]
    print(f"final A18 {primary['baseline']['log_loss']:.5f} -> A18+GAP {primary['candidate']['log_loss']:.5f}"
          f" ({m[0]:+.5f}, 99% {m[1]:+.5f} to {m[2]:+.5f}) -> {report['verdict']['label']}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
