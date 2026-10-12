"""Architectures: checks run AFTER the registered result (REPORT.md). Description only.

None of this is a registered comparison and none of it can support a change. It asks whether
the boosted trees' result could be a leak, where the gain sits, and (on development only)
whether a plain linear correction from the same shot and xG figures would do the same job,
to shape the next experiment.

    python experiments/architectures/after.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_frame"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import features  # noqa: E402
import frame  # noqa: E402
import run  # noqa: E402

OUT = Path(__file__).parent / "after.json"


def brute_force_check(data, feats, hx, ax, trials=200, seed=7):
    """Recompute two features for random fixtures straight from the fixtures before them."""
    rng = np.random.default_rng(seed)
    worst = 0.0
    checked = 0
    stat = ~np.isnan(data.home_shots) & ~np.isnan(data.away_shots)
    for i in rng.choice(np.where(data.final)[0], trials, replace=False):
        team = data.home[i]
        earlier = np.where(((data.home == team) | (data.away == team)) & (np.arange(data.n) < i) & stat)[0][-10:]
        if len(earlier) < 3 or np.isnan(feats["h_shots10"][i]):
            continue
        diffs = [(data.home_shots[j] - data.away_shots[j]) * (1 if data.home[j] == team else -1) for j in earlier]
        worst = max(worst, abs(np.mean(diffs) - feats["h_shots10"][i]))
        assert all(data.ordinal[j] <= data.ordinal[i] for j in earlier)
        checked += 1
    return {"fixtures_checked": checked, "largest_difference": float(worst)}


def main():
    chosen = json.loads(run.CHOSEN.read_text())
    data = frame.Data()
    rep, hx, ax, base = run.baseline(data)
    rows, dev = data.final, data.development
    select = dev & (data.day >= run.SELECTION_START)
    lam, mu = run.DC(data, **chosen["dc"]["setting"]).run(frame.BURN_IN_END, frame.FINAL_END, verbose=False)
    feats = features.build(data, rep, hx, ax)
    feats["dc_margin"], feats["dc_total"] = lam - mu - (hx - ax), lam + mu - (hx + ax)
    usable = data.scored & ~np.isnan(hx)
    names = chosen["gb"]["features"]
    out = {"note": "descriptive, after the registered result; not a test",
           "feature_check": brute_force_check(data, feats, hx, ax)}

    def final_gain(keep):
        dm, dt = run.gb_fit_predict(data, feats, keep, hx, ax, run.GB_BLOCKS_FINAL, frame.FINAL_END, chosen["gb"]["params"], usable)
        gh, ga = run.gb_apply(hx, ax, dm, dt, chosen["gb"]["shrink"])
        p = frame.outcome_probabilities(gh[rows], ga[rows])
        return frame.log_loss(p, data.result[rows]) - frame.log_loss(base[rows], data.result[rows]), dm, dt

    d, dm, dt = final_gain(names)
    out["registered_again"] = float(d.mean())
    has_xg = np.array([np.mean(~np.isnan(data.home_xg[(data.league == lg) & data.final])) for lg in data.league])
    has_shots = np.array([np.mean(~np.isnan(data.home_shots[(data.league == lg) & data.final])) for lg in data.league])
    kind = np.where(has_xg > 0.9, "competitions with xG", np.where(has_shots > 0.9, "competitions with shots, no xG",
                    np.where(has_shots < 0.1, "competitions with neither", "competitions with partial statistics")))
    out["by_kind_of_competition"] = {}
    for k in np.unique(kind):
        m = (kind == k)[rows]
        mean, lo, hi = frame.paired_interval(d[m], data.week[rows][m])
        out["by_kind_of_competition"][k] = {"n": int(m.sum()), "log_loss": [round(mean, 5), round(lo, 5), round(hi, 5)]}
    # how big are the corrections?
    out["size_of_correction"] = {"margin, goals: sd": float(dm[rows].std()), "margin: 5th and 95th": [float(v) for v in np.percentile(dm[rows], [5, 95])],
                                 "total, goals: sd": float(dt[rows].std()), "mean total correction": float(dt[rows].mean())}
    # leak checks: the same model without the inputs whose history is least well timestamped
    out["final_without"] = {}
    for label, drop in (("injuries (lists were written in September 2026, not at the time)", features.GROUPS["injuries"]),
                        ("manager", features.GROUPS["manager"]),
                        ("shots and xG", features.GROUPS["shots_xg"]),
                        ("everything but base and shots and xG", [n for n in names if n not in features.BASE + features.GROUPS["shots_xg"]])):
        d2, _, _ = final_gain([n for n in names if n not in drop])
        out["final_without"][label] = float(d2.mean())
        print("final without", label, f"{d2.mean():+.5f}", flush=True)

    # development only: would a plain linear correction from the shot and xG figures do?
    shot_names = features.GROUPS["shots_xg"]
    pairs = {"xG difference": ("h_xgd10", "a_xgd10"), "shot difference": ("h_shots10", "a_shots10"),
             "on-target difference": ("h_sot10", "a_sot10"), "in-box shot difference": ("h_box10", "a_box10"),
             "goals minus xG": ("h_luck10", "a_luck10")}
    X = np.column_stack([np.nan_to_num(feats[h] - feats[a]) for h, a in pairs.values()]
                        + [(~np.isnan(feats[h] - feats[a])).astype(float) * 0 for h, a in list(pairs.values())[:0]])
    resid = (data.ft_home - data.ft_away) - (hx - ax)
    d_lin = np.zeros(data.n)
    edges = list(run.GB_BLOCKS_DEV) + [frame.DEVELOPMENT_END]
    coefs = {}
    for start, stop in zip(edges, edges[1:]):
        train = usable & dev & (data.day < start)
        test = (data.day >= start) & (data.day < stop)
        A = np.column_stack([X[train], np.ones(train.sum())])
        beta = np.linalg.solve(A.T @ A + 50.0 * np.eye(A.shape[1]), A.T @ resid[train])
        d_lin[test] = np.column_stack([X[test], np.ones(test.sum())]) @ beta
        coefs[start] = dict(zip(list(pairs) + ["constant"], map(float, beta)))
    gh, ga = frame.moved(hx[select], ax[select], d_lin[select])
    lin = frame.log_loss(frame.outcome_probabilities(gh, ga), data.result[select]) - frame.log_loss(base[select], data.result[select])
    mean, lo, hi = frame.paired_interval(lin, data.week[select])
    out["development_linear_correction"] = {
        "what": "ridge regression of the margin error on five differences of each side's last-10 shot and xG figures, refitted each half-season",
        "selection_log_loss": [round(mean, 5), round(lo, 5), round(hi, 5)],
        "boosted_trees_on_the_same_window": chosen["gb"]["selection_log_loss"] - chosen["production_selection_log_loss"],
        "coefficients_last_block": coefs[edges[-2]]}
    print(json.dumps(out, indent=1))
    OUT.write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
