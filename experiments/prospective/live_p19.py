"""P19: the ideas of 30 October 2026, scored on each new match as it is played (PROTOCOLS.md).

    MC-0040  A18's trees with GAP ratings (opponent-adjusted shots, shots on target and corners),
             against A18's trees as P17 runs them (MC-0018), on the same matches. Where a side
             has no shot rating yet, the candidate is A18 itself.
    MC-0041  a side back in its league after a European match with five or more days' rest:
             the margin moved 0.19 goals towards it, against the live model.

Worked out on paper from the live model's stored snapshots, as P17 does (the same read, the same
fixtures and the same reprojection of history onto the released club rank), and judged by P15's
confidence sequence (live_p15.track), the 5% split across the two. Run with P16 to P18 by
live_tracking.py.

    python experiments/prospective/live_p19.py      # prints P19's record from its own read; stores nothing

Read-only. No API calls, no odds, nothing new stored. Needs numpy, scipy and scikit-learn at the
versions in requirements-p13.txt; run it against production.
"""
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
EXPERIMENTS = ROOT / "experiments"
FRAME, ARCH = EXPERIMENTS / "research_frame", EXPERIMENTS / "architectures"
GAP, AFTER = EXPERIMENTS / "gap_ratings", EXPERIMENTS / "after_europe"

_spec = importlib.util.spec_from_file_location("live_p17", HERE / "live_p17.py")
p17 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p17)
p16, p15, p13 = p17.p16, p17.p15, p17.p13

# Registered in PROTOCOLS.md; change only by a dated amendment there.
START = "2026-10-31"                 # the first kickoff day after registration
ALPHA = 0.05
AGAINST = {"MC-0040": "MC-0018", "MC-0041": "production"}
SETTINGS = {"MC-0040": ({"gap": "experiments/gap_ratings/results.json (chosen per statistic)",
                         "trees": "experiments/architectures/chosen.json (gb)", "no_rating": "A18"},
                        "experiments/gap_ratings/DESIGN.md"),
            "MC-0041": ({"delta": "experiments/after_europe/chosen.json", "min_rest_days": 5, "europe": [2, 3, 848]},
                        "experiments/after_europe/DESIGN.md")}
PINNED = {
    HERE / "live_p17.py": "9d85a50a43c2cc86349eb13c673ea1f78fecb160bb00c4abafe4f7418f00e82f",
    GAP / "run.py": "09ad98490e398e1249c196b21d273a94d8cd76b51fb59125b942d49ccf41d6d9",
    GAP / "results.json": "4811a357211ed2495e07c92da66a5a5a3095c7be0d492241915bee6d44943921",
    AFTER / "run.py": "47dab89aea2c10921c49edf7c69113c3233ba81da90aa502b621193bec798040",
    AFTER / "chosen.json": "e0c5fd1a23c44fb20d3ad8ec1180e9f7098f8248002fe30c6a0a66d3cab5f2cf",
}


def check_pins():
    wrong = [str(p.relative_to(ROOT)) for p, want in PINNED.items() if p13.digest(p) != want]
    if wrong:
        raise SystemExit("P19's files have changed since registration: " + ", ".join(wrong))
    p17.check_pins()


def after_europe(data, min_rest, europe):
    """(n, 2) booleans: each side back in a league match after a European match at least
    min_rest days before, that being its previous match in the data (experiments/after_europe)."""
    import numpy as np
    out = np.zeros((data.n, 2), dtype=bool)
    last = {}
    for i in range(data.n):
        for side, team in enumerate((data.home[i], data.away[i])):
            j = last.get(team)
            if j is not None and data.is_league[i] and data.league[j] in europe \
                    and data.ordinal[i] - data.ordinal[j] >= min_rest:
                out[i, side] = True
            last[team] = i
    return out


def build(doc, start=START):
    """Per accrued fixture, in kickoff order: each candidate's probabilities and those of what it
    is compared with. Returns (rows, exclusions); rows is None before the first fixture."""
    import numpy as np
    frame = p13.load("frame", FRAME / "frame.py")
    sys.modules["frame"] = frame
    features = p13.load("features", FRAME / "features.py")
    sys.modules["features"] = features
    arch = p13.load("p19_architectures", ARCH / "run.py")
    shots = p13.load("p19_shots_proxy", p16.SHOTS / "run.py")
    gap = p13.load("p19_gap_ratings", GAP / "run.py")
    frame.FINAL_END = "9999-12-31"
    chosen = json.loads((ARCH / "chosen.json").read_text())
    beta = np.array(json.loads((p16.SHOTS / "chosen.json").read_text())["beta"])
    gap_chosen = {k: v["chosen"] for k, v in json.loads((GAP / "results.json").read_text())["gap"].items()}
    after = json.loads((AFTER / "chosen.json").read_text())

    # P17's fixtures and history, exactly
    ours = p16.released(doc["versions"])
    kick = {r[0]: r[1] for r in doc["fixtures"]["rows"]}
    latest = p13.latest_before_kickoff(doc["snapshots"], {f: k for f, k in kick.items() if k[:10] >= start})
    picked = {f: s for f, s in latest.items() if s["model_version_id"] in ours}
    columns = doc["predictions"]["columns"]
    rows = [r for r in doc["predictions"]["rows"] if r[0] not in picked and kick.get(r[0], "")[:10] < start]
    for fid, s in picked.items():
        value = {"fixture_id": fid, "home_rank": s["home_match_rank"], "away_rank": s["away_match_rank"],
                 "source": "live", **{k: s[k] for k in ("exp_diff", "home_xg", "away_xg", "p_home", "p_draw", "p_away",
                                                        "p_over25", "p_btts", "home_missing", "away_missing")}}
        rows.append([value[c] for c in columns])
    data = frame.Data({**doc, "predictions": {"columns": columns, "rows": rows}})
    rep = shots.replay(data, beta, p16.SHOTS_SETTING, p16.MOVEMENT)
    hx, ax = frame.reprojected(data, rep)
    regulation = np.isin(data.status, p15.STATUSES) & ~np.isnan(data.ft_home) & ~np.isnan(data.ft_away)
    index = np.array([data.index[f] for f in picked if f in data.index and regulation[data.index[f]]], dtype=int)
    index.sort()
    for i in index:                            # the snapshot's own goals, not a re-projection
        s = picked[int(data.fixture_id[i])]
        hx[i], ax[i] = s["home_xg"], s["away_xg"]
    stored = np.array([[picked[int(f)][k] for k in ("p_home", "p_draw", "p_away")] for f in data.fixture_id[index]])
    stored = stored.reshape(len(index), 3)
    again = frame.outcome_probabilities(hx[index], ax[index]) if len(index) else stored
    same = np.abs(again - stored).max(axis=1) <= p15.TOLERANCE if len(index) else np.zeros(0, dtype=bool)
    excluded = {"latest_snapshot_from_the_old_version": len(latest) - len(picked),
                "not_reproduced_by_the_registered_probability_step": int((~same).sum())}
    index, stored = index[same], stored[same]
    if not len(index):
        return None, excluded

    latest_day = max(str(v) for v in data.day[index])
    last_day = (date.fromisoformat(latest_day) + timedelta(days=1)).isoformat()
    usable = data.scored & ~np.isnan(hx)
    blocks = p13.blocks_until(latest_day)
    feats = features.build(data, rep, hx, ax)
    probs = lambda h, a: frame.outcome_probabilities(h[index], a[index])

    # A18's trees as P17 runs them, and the same with the GAP ratings
    lam, mu = arch.DC(data, **chosen["dc"]["setting"]).run(frame.BURN_IN_END, last_day, verbose=False)
    feats["dc_margin"], feats["dc_total"] = lam - mu - (hx - ax), lam + mu - (hx + ax)
    names = list(chosen["gb"]["features"])
    dm, dt = arch.gb_fit_predict(data, feats, names, hx, ax, blocks, last_day, chosen["gb"]["params"], usable)
    a18 = probs(*arch.gb_apply(hx, ax, dm, dt, chosen["gb"]["shrink"]))
    for name, (hc, ac) in gap.STATS.items():
        c = gap_chosen[name]
        ph, pa = gap.gap(data, getattr(data, hc), getattr(data, ac), c["lambda"], c["phi1"], c["phi2"])
        feats[f"gap_h_{name}"], feats[f"gap_a_{name}"], feats[f"gap_d_{name}"] = ph, pa, ph - pa
        names += [f"gap_h_{name}", f"gap_a_{name}", f"gap_d_{name}"]
    gm, gt = arch.gb_fit_predict(data, feats, names, hx, ax, blocks, last_day, chosen["gb"]["params"], usable)
    with_gap = probs(*arch.gb_apply(hx, ax, gm, gt, chosen["gb"]["shrink"]))
    rated = ~np.isnan(feats["gap_h_shots"][index])
    with_gap = np.where(rated[:, None], with_gap, a18)

    # back after Europe
    f = after_europe(data, after["min_rest_days"], tuple(after["europe"]))
    side = (f[:, 0].astype(float) - f[:, 1].astype(float)) * after["delta"]
    europe = probs(*frame.moved(hx, ax, side))

    return {"frame": frame, "y": data.result[index], "week": data.week[index], "day": data.day[index],
            "candidates": {"MC-0040": with_gap, "MC-0041": europe},
            "against": {"MC-0040": a18, "MC-0041": stored},
            "counts": {"MC-0040_rated": int(rated.sum()), "MC-0041_changed": int((side[index] != 0).sum())}}, excluded


def record(rows, excluded):
    """P19's part of the document: each candidate's track against what it is compared with."""
    alpha = ALPHA / len(AGAINST)
    base = {"alpha": ALPHA, "start": START, "comparisons": len(AGAINST), "exclusions": excluded, "against": AGAINST,
            "settings": {cid: {"setting": s, "source": src} for cid, (s, src) in SETTINGS.items()}}
    if rows is None:
        return {**base, "n": 0, "counts": {}, "changes": {cid: p15.track([], [], alpha) for cid in AGAINST}}
    frame, y = rows["frame"], rows["y"]
    weeks = [int(w) for w in rows["week"]]
    return {**base, "n": int(len(y)), "counts": rows["counts"],
            "changes": {cid: p15.track([float(v) for v in frame.log_loss(p, y) - frame.log_loss(rows["against"][cid], y)],
                                       weeks, alpha)
                        for cid, p in rows["candidates"].items()}}


def main():
    check_pins()
    doc = p16.extract()
    out = record(*build(doc))
    print(json.dumps({k: out[k] for k in ("n", "start", "exclusions", "counts")}, indent=2, default=str))


if __name__ == "__main__":
    main()
