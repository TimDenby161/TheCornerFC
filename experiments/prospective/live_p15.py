"""P15: every change in the register that can be run, scored on each new match as it is played
(PROTOCOLS.md). The Model Change Tracker shows the result.

Unlike P13 and P14 this is watched as it goes, so it is judged by a method made for that: a
confidence sequence (Robbins' normal mixture, in the form of Waudby-Smith, Arbour, Sinha, Kennedy
and Ramdas, "Time-uniform central limit theory and asymptotic confidence sequences"), which
holds at every look at once, widened for the weeks the matches come in and split across the
candidates. A candidate is "proven better" from the first week its whole interval is below
zero, however often anyone has looked.

Each candidate is applied to the projected goals of a fixture's latest prospective snapshot
before kickoff, with the settings its own experiment fixed, and scored against that snapshot's
stored probabilities. Nothing here is read by production, and no model is changed by it.

    python experiments/prospective/live_p15.py            # prints the record; stores nothing
    python experiments/prospective/live_p15.py --store    # and stores it for the Admin area

Read-only apart from --store, which writes the one administrator's document `live_tracking`.
No API calls, no odds. Needs numpy, scipy and scikit-learn at the versions in
requirements-p13.txt; run it against production (read-only locally, where it can't store).
"""
import argparse
import importlib.util
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
EXPERIMENTS = ROOT / "experiments"
FRAME, ARCH = EXPERIMENTS / "research_frame", EXPERIMENTS / "architectures"
RATING, GOALS, CALIBRATION, SHOTS, GAPS, ENDS = (EXPERIMENTS / n for n in (
    "rating_dynamics", "goals_home_scores", "relearned_calibration", "shots_proxy", "level_gaps", "ends_and_draws"))

# Registered in PROTOCOLS.md; change only by a dated amendment there.
START = "2026-10-14"                 # first kickoff day (UTC) that counts
ALPHA = 0.05                         # the chance, over the whole run, of any candidate being wrongly called
PLANNED = 6200                       # the sample the interval is made tightest at (P14's target)
MINIMUM_MATCHES, MINIMUM_WEEKS = 500, 8      # nothing is called before both
BAR = 0.002                          # the gain a change needs to be put forward
TOLERANCE = 1e-8
STATUSES = ("FT", "AET", "PEN")      # a tie level at 90 minutes is a draw
# change id -> (candidate, the setting its experiment fixed, where that is recorded)
CANDIDATES = {
    "MC-0003": ("blend", {"now_weight": 0.7}, "experiments/strength_weight: the best alternative"),
    "MC-0007": ("power", {"power": 1.10}, "experiments/ends_and_draws/results.json: h1"),
    "MC-0008": ("draws", {"inflation": 1.07, "fade": 1.0}, "experiments/ends_and_draws/results.json: h2"),
    "MC-0009": ("joint", {"power": 1.08, "inflation": 1.09, "fade": 1.5}, "experiments/ends_and_draws/results.json: joint"),
    "MC-0010": ("gaps", {"beta": 0.10}, "experiments/level_gaps/results.json: h3"),
    "MC-0011": ("no_league", {"delta": 25}, "experiments/level_gaps/results.json: h4"),
    "MC-0013": ("rank", {"pull": 0.5}, "experiments/rating_dynamics/chosen.json: movers"),
    "MC-0014": ("rank", {"boost": 1.0, "tau": 10.0, "damp": 0, "reset": 10}, "experiments/rating_dynamics/chosen.json: uncertainty"),
    "MC-0016": ("rank", {"pull": 0.5, "boost": 0.5, "tau": 40.0}, "experiments/rating_dynamics/chosen.json: combined"),
    "MC-0017": ("dc", {}, "experiments/architectures/chosen.json: dc"),
    "MC-0018": ("gb", {}, "experiments/architectures/chosen.json: gb"),
    "MC-0019": ("pool3", {}, "experiments/architectures/chosen.json: pool3"),
    "MC-0020": ("goal_level", {"half_life": 60, "comp": 100}, "experiments/goals_home_scores/chosen.json: goal_level"),
    "MC-0021": ("league_home", {"half_life": 730, "comp": 300}, "experiments/goals_home_scores/chosen.json: league_home"),
    "MC-0024": ("shots", {"goals_weight": 0.5, "k": 10.0}, "experiments/shots_proxy/chosen.json"),
    "MC-0025": ("formula", {}, "experiments/prospective/PROTOCOLS.md: P13"),
    "MC-0027": ("combined", {}, "experiments/relearned_calibration/chosen.json"),
}
# Changes with nothing to run, and why. Every change in the register is in one list or the other.
NOT_RUN = {
    "MC-0001": "Already in production: there is no earlier version stored to run beside it",
    "MC-0002": "A change to the betting rule, not to the predictions",
    "MC-0004": "A change to player ranks, with no match prediction of its own",
    "MC-0005": "A forecast of a club's next matches, with no match prediction of its own",
    "MC-0006": "A study of what line-ups are worth; it proposed no setting to run",
    "MC-0012": "Testing chose no setting, so there is nothing to run",
    "MC-0015": "Testing chose no setting, so there is nothing to run",
    "MC-0022": "Testing chose no term, so there is nothing to run",
    "MC-0023": "Testing chose no term, so there is nothing to run",
    "MC-0026": "Testing chose no curve, so there is nothing to run",
}

_spec = importlib.util.spec_from_file_location("shadow_p14", HERE / "shadow_p14.py")
p14 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p14)
p13 = p14.p13

# The candidates are these files as they were at registration. A changed file is a different
# candidate, so the run stops.
PINNED = {
    **p14.PINNED,
    HERE / "shadow_p14.py": "5f5fd9c1c3b384b4c0575ae28b8a952e44cad9040d8eb60c325916a2863961fa",
    SHOTS / "run.py": "c1d96bd6878fda803bc7eed6cb6c7ef34c2d927d89a7eac1889036e10ec378bc",
    SHOTS / "chosen.json": "2b3db2eec481ad7b0193aa3f4915bb1c5e0f1a2de53edc0ed7b51426f9f7114d",
    GAPS / "run.py": "8393afd0747fa8505e546e0e5643e914571663aff6ac5a95faf5bec45785e157",
    ENDS / "run.py": "2b91a1d52bd6a29345c8c6c7133d34d881841028e4d2ba06384ded381616ea7b",
}
SNAPSHOT_SQL, FETCHED_SQL, SKIP_QUERIES = p14.SNAPSHOT_SQL, p14.FETCHED_SQL, p14.SKIP_QUERIES


def check_pins():
    wrong = [str(p.relative_to(ROOT)) for p, want in PINNED.items() if p13.digest(p) != want]
    if wrong:
        raise SystemExit("P15's candidate files have changed since registration: " + ", ".join(wrong))


# ---- the judgement: plain Python, no database, no numpy ---------------------------------------

def mixture_rho(alpha, planned=PLANNED):
    """The mixture's one number, set so the interval is at its tightest at the planned sample."""
    a = -2 * math.log(alpha)
    return math.sqrt((a + math.log(a + 1)) / planned)


def half_width(n, sd, alpha, rho, design=1.0):
    """Half the width of the two-sided confidence sequence for a mean after n matches. sd is the
    standard deviation of one match's difference; design widens it for matches that come in
    weeks. Valid at every n at once, at coverage 1 - alpha."""
    if n < 2 or not sd > 0:
        return math.inf
    t = n * rho * rho
    return math.sqrt(design) * sd * math.sqrt(2 * (t + 1) / (n * t) * math.log(math.sqrt(t + 1) / alpha))


def design_effect(sums, counts, mean, sd, n):
    """How much wider than independent matches the weeks make the mean's variance: the
    cluster-robust variance over the plain one, never under 1."""
    if n < 2 or not sd > 0:
        return 1.0
    clustered = sum((s - c * mean) ** 2 for s, c in zip(sums, counts)) / (n * n)
    return max(1.0, clustered / (sd * sd / n))


def verdict(lo, hi, n, weeks):
    """'better' when the whole interval of the log-loss difference is below zero, 'worse' when
    it is above, None otherwise; nothing before the minimum sample."""
    if n < MINIMUM_MATCHES or weeks < MINIMUM_WEEKS:
        return None
    return "better" if hi < 0 else "worse" if lo > 0 else None


def track(differences, weeks, alpha):
    """One candidate's record from its per-match differences (candidate minus production, log
    loss) and each match's ISO week, in kickoff order: where it stands after every week, and
    the first week it was proven either way. A call once made stands: that is what the
    confidence sequence allows, and what stops a later wobble from undoing it."""
    rho = mixture_rho(alpha)
    order, by_week = [], {}
    for d, w in zip(differences, weeks):
        if w not in by_week:
            by_week[w] = [0.0, 0.0, 0]
            order.append(w)
        cell = by_week[w]
        cell[0] += d; cell[1] += d * d; cell[2] += 1
    total = squares = 0.0
    n, series, called = 0, [], None
    for i, w in enumerate(order, 1):
        s, q, c = by_week[w]
        total += s; squares += q; n += c
        mean = total / n
        sd = math.sqrt(max(squares - n * mean * mean, 0.0) / (n - 1)) if n > 1 else 0.0
        design = design_effect([by_week[x][0] for x in order[:i]], [by_week[x][2] for x in order[:i]], mean, sd, n)
        half = half_width(n, sd, alpha, rho, design)
        lo, hi = mean - half, mean + half
        said = verdict(lo, hi, n, i)
        if said and called is None:
            called = {"verdict": said, "week": int(w), "n": n, "gain": -mean}
        finite = math.isfinite(half)
        series.append({"week": int(w), "n": n, "gain": -mean, "low": -hi if finite else None, "high": -lo if finite else None})
    if not series:
        return {"n": 0, "weeks": 0, "gain": None, "low": None, "high": None, "sd": None, "design": None,
                "verdict": None, "called": None, "ready": False, "series": []}
    last = series[-1]
    said = called["verdict"] if called else None
    return {"n": n, "weeks": len(order), "gain": last["gain"], "low": last["low"], "high": last["high"], "sd": sd,
            "design": design, "verdict": said, "called": called,
            "ready": said == "better" and last["gain"] >= BAR, "series": series}


# ---- the database ----------------------------------------------------------------------------

def extract():
    """Everything the candidates need, read once: the research frame's own queries with the cut
    moved to tomorrow (no odds), the prospective snapshots, and when each recent fixture's
    statistics were last fetched."""
    frame_extract = p13.load("p15_frame_extract", FRAME / "extract.py")
    cut = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    doc = {"cut": cut}
    with p13.connect() as conn:
        doc["database_says"] = p13.environment(conn)
        doc["database_role"] = conn.execute("select current_user").fetchone()[0]
        for name, sql in frame_extract.QUERIES.items():
            if name in SKIP_QUERIES:
                continue
            cur = conn.execute(sql, {"cut": cut})
            doc[name] = {"columns": [d.name for d in cur.description],
                         "rows": [[frame_extract.plain(v) for v in row] for row in cur.fetchall()]}
        keys = ("fixture_id", "captured_at", "created_at", "home_xg", "away_xg", "exp_diff", "p_home", "p_draw",
                "p_away", "p_over25", "p_btts", "model_version_id", "home_match_rank", "away_match_rank",
                "home_missing", "away_missing")
        doc["snapshots"] = [dict(zip(keys, (frame_extract.plain(v) for v in row)))
                            for row in conn.execute(SNAPSHOT_SQL, {"start": START})]
    doc["extracted_at"] = datetime.now(timezone.utc).isoformat()
    return doc


# ---- the candidates --------------------------------------------------------------------------

def build(doc, start=START):
    """Per accrued fixture, in kickoff order: production's stored probabilities and every
    candidate's. Returns (rows, exclusions); rows is None before the first fixture."""
    import numpy as np
    frame = p13.load("frame", FRAME / "frame.py")
    sys.modules["frame"] = frame
    features = p13.load("features", FRAME / "features.py")
    sys.modules["features"] = features
    arch = p13.load("p15_architectures", ARCH / "run.py")
    rating = p13.load("p15_rating_dynamics", RATING / "run.py")
    goals = p13.load("p15_goals_home_scores", GOALS / "run.py")
    calibration = p13.load("p15_relearned_calibration", CALIBRATION / "run.py")
    shots = p13.load("p15_shots_proxy", SHOTS / "run.py")
    gaps = p13.load("p15_level_gaps", GAPS / "run.py")
    frame.FINAL_END = "9999-12-31"            # the frame stops scoring at its own cut; P15 goes on
    chosen = json.loads((ARCH / "chosen.json").read_text())
    registered = json.loads((CALIBRATION / "chosen.json").read_text())
    beta = np.array(json.loads((SHOTS / "chosen.json").read_text())["beta"])

    kick = {r[0]: r[1] for r in doc["fixtures"]["rows"]}
    picked = p13.latest_before_kickoff(doc["snapshots"], {f: k for f, k in kick.items() if k[:10] >= start})
    columns = doc["predictions"]["columns"]
    rows = [r for r in doc["predictions"]["rows"] if r[0] not in picked and kick.get(r[0], "")[:10] < start]
    for fid, s in picked.items():
        value = {"fixture_id": fid, "home_rank": s["home_match_rank"], "away_rank": s["away_match_rank"],
                 "source": "live", **{k: s[k] for k in ("exp_diff", "home_xg", "away_xg", "p_home", "p_draw", "p_away",
                                                        "p_over25", "p_btts", "home_missing", "away_missing")}}
        rows.append([value[c] for c in columns])
    data = frame.Data({**doc, "predictions": {"columns": columns, "rows": rows}})

    rep, hx, ax, _ = arch.baseline(data)
    regulation = np.isin(data.status, STATUSES) & ~np.isnan(data.ft_home) & ~np.isnan(data.ft_away)
    index = np.array([data.index[f] for f in picked if f in data.index and regulation[data.index[f]]], dtype=int)
    index.sort()
    for i in index:                            # the snapshot's own goals, not a re-projection
        s = picked[int(data.fixture_id[i])]
        hx[i], ax[i] = s["home_xg"], s["away_xg"]
    stored = np.array([[picked[int(f)][k] for k in ("p_home", "p_draw", "p_away")] for f in data.fixture_id[index]])
    stored = stored.reshape(len(index), 3)
    again = frame.outcome_probabilities(hx[index], ax[index]) if len(index) else stored
    same = np.abs(again - stored).max(axis=1) <= TOLERANCE if len(index) else np.zeros(0, dtype=bool)
    excluded = {"not_reproduced_by_the_registered_probability_step": int((~same).sum()),
                "no_snapshot_before_kickoff_or_no_90_minute_score": int(
                    sum(1 for f, k in kick.items() if k[:10] >= start) - len(index))}
    index, stored = index[same], stored[same]
    if not len(index):
        return None, excluded

    latest = max(str(v) for v in data.day[index])
    last_day = (date.fromisoformat(latest) + timedelta(days=1)).isoformat()
    usable = data.scored & ~np.isnan(hx)
    blocks = p13.blocks_until(latest)
    feats = features.build(data, rep, hx, ax)
    probs = lambda h, a: frame.outcome_probabilities(h[index], a[index])
    power = lambda p, a: (lambda z: z / z.sum(axis=1, keepdims=True))(np.clip(p, 1e-12, 1) ** a)
    moved = calibration.moved
    ph, pa = rep.match_rank()

    def rank_shift(candidate, weight=frame.PRODUCTION["now_weight"]):
        h, a = candidate.match_rank(weight)
        return ((h - a) - (ph - pa)) / 100

    out = {}
    # the result probabilities themselves
    out["MC-0007"] = power(stored, CANDIDATES["MC-0007"][1]["power"])
    s = CANDIDATES["MC-0008"][1]
    out["MC-0008"] = frame.outcome_probabilities(hx[index], ax[index], s["inflation"], s["fade"])
    s = CANDIDATES["MC-0009"][1]
    out["MC-0009"] = power(frame.outcome_probabilities(hx[index], ax[index], s["inflation"], s["fade"]), s["power"])
    # the club rank
    out["MC-0003"] = probs(*moved(hx, ax, rank_shift(rep, CANDIDATES["MC-0003"][1]["now_weight"])))
    for cid in ("MC-0013", "MC-0014", "MC-0016"):
        out[cid] = probs(*moved(hx, ax, rank_shift(rating.replay(data, {**rating.OFF, **CANDIDATES[cid][1]}))))
    out["MC-0024"] = probs(*moved(hx, ax, rank_shift(shots.replay(data, beta, CANDIDATES["MC-0024"][1]))))
    # matches between leagues
    fixtures = [{"fixture_id": int(f), "kickoff": k, "league_id": int(lg), "home_team_id": int(h), "away_team_id": int(a)}
                for f, k, lg, h, a in zip(data.fixture_id, data.kickoff, data.league, data.home, data.away)]
    leagues = {str(k): v for k, v in data.leagues.items()}
    kinds = gaps.classify(fixtures, leagues)
    cross = np.array([kinds[int(f)][1] if kinds[int(f)][0] == "cross" else 0.0 for f in data.fixture_id])
    one = np.array([kinds[int(f)][2] if kinds[int(f)][0] == "one_sided" else 0.0 for f in data.fixture_id])
    out["MC-0010"] = probs(*moved(hx, ax, CANDIDATES["MC-0010"][1]["beta"] * cross / 100))
    out["MC-0011"] = probs(*moved(hx, ax, CANDIDATES["MC-0011"][1]["delta"] * one / 100))
    # goals and home advantage
    out["MC-0020"] = probs(*goals.goal_level(data, hx, ax, CANDIDATES["MC-0020"][1]))
    out["MC-0021"] = probs(*goals.league_home(data, hx, ax, CANDIDATES["MC-0021"][1]))
    # the formulas
    movers = registered["registered_settings"]["movers"]
    projected, _ = calibration.candidates(data, feats, hx, ax, calibration.movers_shift(data, rep, rating, movers), usable,
                                          blocks, last_day, registered["curve"]["setting"],
                                          registered["registered_settings"]["goal_level"], goals)
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


def record(rows, excluded, *, environment, generated_at):
    """The document the Admin area reads."""
    alpha = ALPHA / len(CANDIDATES)
    base = {"protocol": "P15", "generated_at": generated_at, "environment": environment, "start": START,
            "planned": PLANNED, "minimum": {"matches": MINIMUM_MATCHES, "weeks": MINIMUM_WEEKS}, "bar": BAR,
            "alpha": ALPHA, "comparisons": len(CANDIDATES), "exclusions": excluded,
            "not_run": NOT_RUN, "settings": {cid: {"setting": s, "source": src} for cid, (_, s, src) in CANDIDATES.items()}}
    if rows is None:
        return {**base, "n": 0, "weeks": 0, "to": None, "changes": {cid: track([], [], alpha) for cid in CANDIDATES}}
    frame, y = rows["frame"], rows["y"]
    mine = frame.log_loss(rows["production"], y)
    weeks = [int(w) for w in rows["week"]]
    changes = {cid: track([float(v) for v in frame.log_loss(p, y) - mine], weeks, alpha) for cid, p in rows["candidates"].items()}
    return {**base, "n": int(len(y)), "weeks": len(set(weeks)), "to": str(max(rows["day"])),
            "production_log_loss": float(mine.mean()), "changes": changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", action="store_true", help="store the record for the Admin area (needs a run that may write)")
    args = parser.parse_args()
    check_pins()
    doc = extract()
    rows, excluded = build(doc)
    out = record(rows, excluded, environment=doc["database_says"], generated_at=doc["extracted_at"])
    print(json.dumps({"n": out["n"], "weeks": out["weeks"], "to": out["to"], "exclusions": excluded,
                      "called": {cid: c["called"] for cid, c in out["changes"].items() if c["called"]}}, indent=2))
    if args.store:
        from thecornerfc.pipeline import db
        from thecornerfc.publish import site_files
        with db.connect() as conn:          # a run that may write, to its own environment's database only
            site_files.store_admin_doc(conn, "live_tracking", out)
        print("stored")


if __name__ == "__main__":
    main()
