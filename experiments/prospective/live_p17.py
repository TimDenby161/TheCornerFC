"""P17: every idea in the change register that can be run on top of the live model, scored on each
new match as it is played (PROTOCOLS.md). P15 did this against the model before the club-rank
release (MC-0028); P17 does it against the released one, and runs with P16 in one read.

Each candidate is applied, with the setting its own experiment fixed, to the projected goals of a
fixture's latest prospective snapshot from the released version, and scored against that
snapshot's stored probabilities. History before the release is the stored projections moved onto
the released club rank (frame.reprojected), so ideas that learn from the model's errors as they
go (the goal level, home advantage by competition, the shot formula, the boosted trees) learn the
released model's. Judged by P15's confidence sequence (live_p15.track), the 5% split across the
candidates.

    python experiments/prospective/live_p17.py            # prints P16's and P17's record; stores nothing
    python experiments/prospective/live_p17.py --store    # and stores the one document for the Admin area

Read-only apart from --store, which writes the administrator's document `live_tracking`, in P15's
shape: P16's release and P17's ideas together. No API calls, no odds. Needs numpy, scipy and
scikit-learn at the versions in requirements-p13.txt; run it against production.
"""
import argparse
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
GOALS, CALIBRATION, GAPS = (EXPERIMENTS / n for n in ("goals_home_scores", "relearned_calibration", "level_gaps"))

_spec = importlib.util.spec_from_file_location("live_p16", HERE / "live_p16.py")
p16 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p16)
p15, p13 = p16.p15, p16.p13

# Registered in PROTOCOLS.md; change only by a dated amendment there.
START = p16.START                    # the release's first kickoff day: the same fixtures as P16
ALPHA = 0.05                         # the chance, over the whole run, of any candidate being wrongly called
TRACKED = ("MC-0003", "MC-0007", "MC-0008", "MC-0009", "MC-0010", "MC-0011", "MC-0017", "MC-0018", "MC-0019",
           "MC-0020", "MC-0021", "MC-0025", "MC-0027")
CANDIDATES = {cid: p15.CANDIDATES[cid] for cid in TRACKED}       # each with the setting P15 registered
IN_PRODUCTION = "In production since 2026-10-14, as part of the club-rank release (MC-0028)"
NOT_RUN = {**p15.NOT_RUN, **{cid: IN_PRODUCTION for cid in ("MC-0013", "MC-0014", "MC-0016", "MC-0024")}}
# The files that define the candidates and both ranks, as they were at registration
PINNED = {**p15.PINNED, **p16.PINNED,
          HERE / "live_p16.py": "5635b8d136e48b327681633d065a0b91dcb4573d6f6f05454bd58a92c208b491"}


def check_pins():
    wrong = [str(p.relative_to(ROOT)) for p, want in PINNED.items() if p13.digest(p) != want]
    if wrong:
        raise SystemExit("P17's files have changed since registration: " + ", ".join(wrong))
    p16.check_pins()


def build(doc, start=START):
    """Per accrued fixture, in kickoff order: the live model's stored probabilities and every
    candidate's on top of it. Returns (rows, exclusions); rows is None before the first fixture."""
    import numpy as np
    frame = p13.load("frame", FRAME / "frame.py")
    sys.modules["frame"] = frame
    features = p13.load("features", FRAME / "features.py")
    sys.modules["features"] = features
    arch = p13.load("p17_architectures", ARCH / "run.py")
    goals = p13.load("p17_goals_home_scores", GOALS / "run.py")
    calibration = p13.load("p17_relearned_calibration", CALIBRATION / "run.py")
    shots = p13.load("p17_shots_proxy", p16.SHOTS / "run.py")
    gaps = p13.load("p17_level_gaps", GAPS / "run.py")
    frame.FINAL_END = "9999-12-31"
    chosen = json.loads((ARCH / "chosen.json").read_text())
    registered = json.loads((CALIBRATION / "chosen.json").read_text())
    beta = np.array(json.loads((p16.SHOTS / "chosen.json").read_text())["beta"])

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

    # the live model: the released club rank, and every stored projection moved onto it
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
    power = lambda p, a: (lambda z: z / z.sum(axis=1, keepdims=True))(np.clip(p, 1e-12, 1) ** a)
    moved = calibration.moved
    ph, pa = rep.match_rank()

    out = {}
    # the result probabilities themselves
    out["MC-0007"] = power(stored, CANDIDATES["MC-0007"][1]["power"])
    s = CANDIDATES["MC-0008"][1]
    out["MC-0008"] = frame.outcome_probabilities(hx[index], ax[index], s["inflation"], s["fade"])
    s = CANDIDATES["MC-0009"][1]
    out["MC-0009"] = power(frame.outcome_probabilities(hx[index], ax[index], s["inflation"], s["fade"]), s["power"])
    # the club rank's blend of now and the long run, on the released rank
    h, a = rep.match_rank(CANDIDATES["MC-0003"][1]["now_weight"])
    out["MC-0003"] = probs(*moved(hx, ax, ((h - a) - (ph - pa)) / 100))
    # matches between leagues
    fixtures = [{"fixture_id": int(f), "kickoff": k, "league_id": int(lg), "home_team_id": int(hm), "away_team_id": int(aw)}
                for f, k, lg, hm, aw in zip(data.fixture_id, data.kickoff, data.league, data.home, data.away)]
    leagues = {str(k): v for k, v in data.leagues.items()}
    kinds = gaps.classify(fixtures, leagues)
    cross = np.array([kinds[int(f)][1] if kinds[int(f)][0] == "cross" else 0.0 for f in data.fixture_id])
    one = np.array([kinds[int(f)][2] if kinds[int(f)][0] == "one_sided" else 0.0 for f in data.fixture_id])
    out["MC-0010"] = probs(*moved(hx, ax, CANDIDATES["MC-0010"][1]["beta"] * cross / 100))
    out["MC-0011"] = probs(*moved(hx, ax, CANDIDATES["MC-0011"][1]["delta"] * one / 100))
    # goals and home advantage
    out["MC-0020"] = probs(*goals.goal_level(data, hx, ax, CANDIDATES["MC-0020"][1]))
    out["MC-0021"] = probs(*goals.league_home(data, hx, ax, CANDIDATES["MC-0021"][1]))
    # the formulas; the movers in MC-0027 are in the live model already, so they add nothing here
    projected, _ = calibration.candidates(data, feats, hx, ax, np.zeros(data.n), usable, blocks, last_day,
                                          registered["curve"]["setting"], registered["registered_settings"]["goal_level"], goals)
    out["MC-0025"], out["MC-0027"] = probs(*projected["formula"]), probs(*projected["combined"])
    # other models
    lam, mu = arch.DC(data, **chosen["dc"]["setting"]).run(frame.BURN_IN_END, last_day, verbose=False)
    dc = arch.dc_probabilities(lam[index], mu[index], chosen["dc"]["rho"])
    out["MC-0017"] = dc
    feats["dc_margin"], feats["dc_total"] = lam - mu - (hx - ax), lam + mu - (hx + ax)
    dm, dt = arch.gb_fit_predict(data, feats, chosen["gb"]["features"], hx, ax, blocks, last_day, chosen["gb"]["params"], usable)
    out["MC-0018"] = probs(*arch.gb_apply(hx, ax, dm, dt, chosen["gb"]["shrink"]))
    w = chosen["pool3"]["weights"]
    out["MC-0019"] = arch.pool([stored, dc, out["MC-0018"]], [w["production"], w["dc"], w["gb"]])
    assert set(out) == set(CANDIDATES)
    return {"frame": frame, "y": data.result[index], "week": data.week[index], "day": data.day[index],
            "production": stored, "candidates": out}, excluded


def record(rows, excluded):
    """P17's part of the document: each candidate's track, and why the others are not run."""
    alpha = ALPHA / len(CANDIDATES)
    base = {"alpha": ALPHA, "comparisons": len(CANDIDATES), "exclusions": excluded, "not_run": NOT_RUN,
            "settings": {cid: {"setting": s, "source": src} for cid, (_, s, src) in CANDIDATES.items()}}
    if rows is None:
        return {**base, "n": 0, "changes": {cid: p15.track([], [], alpha) for cid in CANDIDATES}}
    frame, y = rows["frame"], rows["y"]
    mine = frame.log_loss(rows["production"], y)
    weeks = [int(w) for w in rows["week"]]
    return {**base, "n": int(len(y)), "production_log_loss": float(mine.mean()),
            "changes": {cid: p15.track([float(v) for v in frame.log_loss(p, y) - mine], weeks, alpha)
                        for cid, p in rows["candidates"].items()}}


def combined(release, ideas):
    """One document in P15's shape: P16's record of the release with P17's of the ideas."""
    tracked = {**release["changes"], **ideas["changes"]}
    return {**release, "protocol": "P16 and P17", "changes": tracked,
            "not_run": {cid: why for cid, why in ideas["not_run"].items() if cid not in tracked},
            "comparisons": {"P16": release["comparisons"], "P17": ideas["comparisons"]},
            "exclusions": {"P16": release["exclusions"], "P17": ideas["exclusions"]},
            "settings": {**release["settings"], **ideas["settings"]},
            "p17": {"alpha": ideas["alpha"], "n": ideas["n"], "production_log_loss": ideas.get("production_log_loss")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", action="store_true", help="store the record for the Admin area (needs a run that may write)")
    args = parser.parse_args()
    check_pins()
    doc = p16.extract()
    rows, excluded, checks = p16.build(doc)
    release = p16.record(rows, excluded, checks, environment=doc["database_says"], generated_at=doc["extracted_at"])
    ideas = record(*build(doc))
    out = combined(release, ideas)
    print(json.dumps({"n": out["n"], "weeks": out["weeks"], "to": out["to"], "exclusions": out["exclusions"], "checks": checks,
                      "called": {cid: c["called"] for cid, c in out["changes"].items() if c["called"]}}, indent=2))
    if args.store:
        from thecornerfc.pipeline import db
        from thecornerfc.publish import site_files
        with db.connect() as conn:          # a run that may write, to its own environment's database only
            site_files.store_admin_doc(conn, "live_tracking", out)
        print("stored")


if __name__ == "__main__":
    main()
