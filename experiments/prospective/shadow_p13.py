"""P13: two shadow corrections to production's match predictions, on prospective snapshots
(PROTOCOLS.md).

    gb       the boosted-tree correction of experiments/architectures, exactly as registered
             there: its settings, its features, its half-season retraining
    formula  a ridge regression of the margin error on five differences of the two sides'
             last-ten shot and xG figures, refitted on the same half-season dates

Each is applied to the projected goals of a fixture's latest prospective snapshot before
kickoff and scored against that snapshot's own stored probabilities. Nothing here is read by
production: the corrections are worked out afterwards, offline, from the database as it stands.

Blinded by default. With no option it asks the database one question (how many fixtures have
accrued) and prints that. --unblind refuses until the registered target is reached; --interim
overrides that and labels the output a protocol deviation that cannot support a decision.

    python experiments/prospective/shadow_p13.py                # accrual only; runs in .venv
    python experiments/prospective/shadow_p13.py --reestimate   # once, at 500: SD only
    python experiments/prospective/shadow_p13.py --unblind      # once, at the target

Read-only: one READ ONLY / REPEATABLE READ transaction, no API calls, no odds. --reestimate and
--unblind read every finished fixture once and need numpy, scipy and scikit-learn at the
versions in requirements-p13.txt; run them against production (read-only), not staging.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
FRAME = ROOT / "experiments" / "research_frame"
ARCH = ROOT / "experiments" / "architectures"

# Registered in PROTOCOLS.md; change only by a dated amendment there.
START = "2026-10-13"                 # first kickoff day (UTC) that counts
TARGET = 9400
REESTIMATE_AT = 500
THRESHOLD = 0.002                    # the improvement a proposal needs
PLANNING_EFFECT = 0.0028             # gb's registered historical result, for the sample size
TOLERANCE = 1e-8
SEED, DRAWS, MIN_WEEKS = 20260927, 2000, 8
RIDGE = 50.0
EUROPE = (2, 3, 848)
FORMULA_PAIRS = (("xG difference", "h_xgd10", "a_xgd10"), ("shot difference", "h_shots10", "a_shots10"),
                 ("on-target difference", "h_sot10", "a_sot10"), ("in-box shot difference", "h_box10", "a_box10"),
                 ("goals minus xG", "h_luck10", "a_luck10"))
# The candidate is these files as they were when gb met its bar. A changed file is a different
# candidate, so the evaluator stops.
PINNED = {
    ARCH / "run.py": "6d971182346bcace45b0d3504daf35fac089e26f60bef5da54255c192b9342da",
    ARCH / "chosen.json": "7b6a4b0fc51b78c3cbddc4aa620b417fb88e278170b65b29236dfe9dbd259502",
    FRAME / "frame.py": "dd5a3e1e2973f0574234e8d120b1a9c99187bb1b999a11eaca250fd698671fba",
    FRAME / "features.py": "3d850304212cd88146df88b3497e8d491e8c9bb507bdc4af1e90354904bb6ab6",
    FRAME / "extract.py": "b35e7ac5513def5cf8f3bd3da085cd899064243df952332a4fb42164bbd96169",
}

ACCRUAL_SQL = """
    select count(*), count(distinct to_char(f.kickoff at time zone 'UTC', 'IYYY-IW'))
    from fixtures f
    where f.status_short = 'FT' and f.ft_home is not null and f.ft_away is not null
      and f.kickoff >= %(start)s
      and exists (select 1 from match_prediction_snapshots s
                  where s.fixture_id = f.fixture_id and s.source = 'prospective'
                    and s.captured_at < f.kickoff and s.created_at < f.kickoff)"""
SNAPSHOT_SQL = """
    select s.fixture_id, s.captured_at, s.created_at, s.home_xg, s.away_xg, s.exp_diff, s.p_home,
           s.p_draw, s.p_away, s.p_over25, s.p_btts, s.model_version_id,
           (s.inputs->>'home_match_rank')::float8, (s.inputs->>'away_match_rank')::float8,
           (s.inputs->>'home_missing')::float8, (s.inputs->>'away_missing')::float8
    from match_prediction_snapshots s join fixtures f using (fixture_id)
    where s.source = 'prospective' and f.status_short = 'FT' and f.kickoff >= %(start)s
      and s.captured_at < f.kickoff and s.created_at < f.kickoff"""
FETCHED_SQL = "select fixture_id, stats_fetched_at from fixtures where kickoff >= %(from)s and stats_fetched_at is not null"
SKIP_QUERIES = ("odds", "bookmakers", "coverage_injuries", "coverage_lineups", "table_sizes", "stats_timing")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_pins():
    wrong = [str(p.relative_to(ROOT)) for p, want in PINNED.items() if digest(p) != want]
    if wrong:
        raise SystemExit("P13's candidate files have changed since registration: " + ", ".join(wrong))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stamp(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def created(snapshot):
    """When a snapshot existed: the later of its capture and its insertion."""
    return max(stamp(snapshot["captured_at"]), stamp(snapshot["created_at"]))


def latest_before_kickoff(snapshots, kickoffs):
    """{fixture_id: snapshot}: each fixture's latest snapshot that existed before its kickoff."""
    chosen = {}
    for s in snapshots:
        kickoff = kickoffs.get(s["fixture_id"])
        if kickoff is None or created(s) >= stamp(kickoff):
            continue
        if s["fixture_id"] not in chosen or created(s) > created(chosen[s["fixture_id"]]):
            chosen[s["fixture_id"]] = s
    return chosen


def blocks_until(last_day):
    """Retraining dates: 1 July and 1 January, from the one in force on START to last_day."""
    out, year, month = [], 2026, 7
    while f"{year}-{month:02d}-01" <= last_day:
        out.append(f"{year}-{month:02d}-01")
        year, month = (year + 1, 1) if month == 7 else (year, 7)
    return out


def fixtures_required(sd, effect=PLANNING_EFFECT):
    return max(REESTIMATE_AT, math.ceil(((1.959964 + 0.841621) * sd / effect) ** 2))


# ---- the database ----------------------------------------------------------------------------

def connect():
    from thecornerfc.pipeline import db
    conn = db.connect()
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    conn.execute("set local statement_timeout = '300s'")
    return conn


def environment(conn):
    try:
        return conn.execute("select site.environment()").fetchone()[0]
    except Exception:
        return None


def accrual():
    with connect() as conn:
        said = environment(conn)
        n, weeks = conn.execute(ACCRUAL_SQL, {"start": START}).fetchone()
    return {"database_says": said, "accrued_upper_bound": n, "weeks": weeks, "target": TARGET,
            "note": "finished fixtures from the start day with a prospective snapshot before kickoff; "
                    "the few whose snapshot today's probability step does not reproduce are taken out at analysis"}


def extract():
    """Everything the candidates need, read once: the research frame's own queries with the cut
    moved to tomorrow (no odds), the prospective snapshots, and when each recent fixture's
    statistics were last fetched."""
    frame_extract = load("p13_frame_extract", FRAME / "extract.py")
    cut = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    doc = {"cut": cut}
    with connect() as conn:
        doc["database_says"] = environment(conn)
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
        doc["fetched"] = {str(f): frame_extract.plain(t) for f, t in conn.execute(FETCHED_SQL, {"from": "2026-07-01"})}
    doc["extracted_at"] = datetime.now(timezone.utc).isoformat()
    return doc


# ---- the candidates --------------------------------------------------------------------------

def build(doc):
    """Per accrued fixture: production's stored probabilities and each candidate's, with what
    the analysis needs beside them. Returns (rows as arrays, exclusions)."""
    import numpy as np
    frame = load("frame", FRAME / "frame.py")
    sys.modules["frame"] = frame
    features = load("features", FRAME / "features.py")
    sys.modules["features"] = features
    arch = load("p13_architectures", ARCH / "run.py")
    frame.FINAL_END = "9999-12-31"            # the frame stops scoring at its own cut; P13 goes on
    chosen = json.loads((ARCH / "chosen.json").read_text())

    kick = {r[0]: r[1] for r in doc["fixtures"]["rows"]}
    picked = latest_before_kickoff(doc["snapshots"], {f: k for f, k in kick.items() if k[:10] >= START})
    # the stored projection of an accrued fixture is its chosen snapshot, nothing later
    columns = doc["predictions"]["columns"]
    rows = [r for r in doc["predictions"]["rows"] if r[0] not in picked and kick.get(r[0], "")[:10] < START]
    for fid, s in picked.items():
        value = {"fixture_id": fid, "home_rank": s["home_match_rank"], "away_rank": s["away_match_rank"],
                 "source": "live", **{k: s[k] for k in ("exp_diff", "home_xg", "away_xg", "p_home", "p_draw", "p_away",
                                                        "p_over25", "p_btts", "home_missing", "away_missing")}}
        rows.append([value[c] for c in columns])
    data = frame.Data({**doc, "predictions": {"columns": columns, "rows": rows}})

    rep, hx, ax, _ = arch.baseline(data)
    index = np.array([data.index[f] for f in picked if f in data.index and data.scored[data.index[f]]], dtype=int)
    index.sort()
    for i in index:                            # the snapshot's own goals, not a re-projection
        s = picked[int(data.fixture_id[i])]
        hx[i], ax[i] = s["home_xg"], s["away_xg"]
    stored = np.array([[picked[int(f)][k] for k in ("p_home", "p_draw", "p_away")] for f in data.fixture_id[index]])
    again = frame.outcome_probabilities(hx[index], ax[index])
    same = np.abs(again - stored).max(axis=1) <= TOLERANCE
    excluded = {"not_reproduced_by_the_registered_probability_step": int((~same).sum()),
                "no_snapshot_before_kickoff_or_not_regulation_time": int(
                    sum(1 for f, k in kick.items() if k[:10] >= START) - len(index))}
    index, stored = index[same], stored[same]
    if not len(index):
        return None, excluded

    latest = max(str(v) for v in data.day[index])
    last_day = (date.fromisoformat(latest) + timedelta(days=1)).isoformat()
    lam, mu = arch.DC(data, **chosen["dc"]["setting"]).run(frame.BURN_IN_END, last_day, verbose=False)
    feats = features.build(data, rep, hx, ax)
    feats["dc_margin"], feats["dc_total"] = lam - mu - (hx - ax), lam + mu - (hx + ax)
    usable = data.scored & ~np.isnan(hx)
    blocks = blocks_until(latest)

    dm, dt = arch.gb_fit_predict(data, feats, chosen["gb"]["features"], hx, ax, blocks, last_day,
                                 chosen["gb"]["params"], usable)
    gh, ga = arch.gb_apply(hx, ax, dm, dt, chosen["gb"]["shrink"])

    X = np.column_stack([np.nan_to_num(feats[h] - feats[a]) for _, h, a in FORMULA_PAIRS])
    resid = (data.ft_home - data.ft_away) - (hx - ax)
    shift, coefficients = np.zeros(data.n), {}
    for start, stop in zip(blocks, blocks[1:] + [last_day]):
        train = usable & (data.day < start)
        test = (data.day >= start) & (data.day < stop)
        A = np.column_stack([X[train], np.ones(int(train.sum()))])
        beta = np.linalg.solve(A.T @ A + RIDGE * np.eye(A.shape[1]), A.T @ resid[train])
        shift[test] = np.column_stack([X[test], np.ones(int(test.sum()))]) @ beta
        coefficients[start] = dict(zip([name for name, _, _ in FORMULA_PAIRS] + ["constant"], map(float, beta)))
    fh, fa = frame.moved(hx, ax, shift)

    # operational subset: both sides' latest earlier match had its statistics in before the snapshot
    last_match, before = {}, {}
    for i in range(data.n):
        for t in (data.home[i], data.away[i]):
            before[(i, t)] = last_match.get(t)
            last_match[t] = i
    fetched = doc.get("fetched", {})

    def in_time(i):
        made = created(picked[int(data.fixture_id[i])])
        for t in (data.home[i], data.away[i]):
            j = before.get((i, t))
            if j is None or np.isnan(data.home_shots[j]):
                continue                        # no earlier match, or one with no statistics to wait for
            at = fetched.get(str(int(data.fixture_id[j])))
            if at is None and data.day[j] < "2026-07-01":
                continue                        # fetched long before; not in the recent list
            if at is None or stamp(at) > made:
                return False
        return True

    events = frame.goal_events(data, index)
    out = {
        "frame": frame, "y": data.result[index], "week": data.week[index], "day": data.day[index],
        "league": data.league[index], "is_league": data.is_league[index],
        "models": {"production": stored, "gb": frame.outcome_probabilities(gh[index], ga[index]),
                   "formula": frame.outcome_probabilities(fh[index], fa[index])},
        "goal_markets": {"production": frame.binary_log_loss(frame.goal_markets(hx[index], ax[index]), events),
                         "gb": frame.binary_log_loss(frame.goal_markets(gh[index], ga[index]), events),
                         "formula": frame.binary_log_loss(frame.goal_markets(fh[index], fa[index]), events)},
        "operational": np.array([in_time(i) for i in index]),
        "retrained_on": blocks, "formula_coefficients": coefficients,
        "correction_sd": {"gb_margin": float(dm[index].std()), "formula_margin": float(shift[index].std())},
    }
    return out, excluded


# ---- the analysis (only ever reached through --unblind or --reestimate) -----------------------

def interval(frame, diff, weeks):
    import numpy as np
    if len(np.unique(weeks)) < MIN_WEEKS:
        return {"delta": float(np.mean(diff)) if len(diff) else None, "weeks": int(len(np.unique(weeks))),
                "ci95": None, "reason": f"fewer than {MIN_WEEKS} weekly blocks"}
    mean, lo, hi = frame.paired_interval(diff, weeks, 0.95, DRAWS, SEED)
    return {"delta": mean, "weeks": int(len(np.unique(weeks))), "ci95": [lo, hi]}


def ends_gap(p, y):
    """Match-weighted |mean predicted - observed| over the home-win and away-win bands below
    20% and from 70% up (experiments/ends_and_draws)."""
    import numpy as np
    total = 0.0
    for k in (0, 2):
        band = np.minimum((p[:, k] * 10).astype(int), 9)
        for b in (0, 1, 7, 8, 9):
            m = band == b
            total += abs(p[m, k].sum() - (y[m] == k).sum())
    n = sum(int((np.minimum((p[:, k] * 10).astype(int), 9) == b).sum()) for k in (0, 2) for b in (0, 1, 7, 8, 9))
    return float(total / n) if n else None


def analyse(rows):
    import numpy as np
    frame, y, weeks = rows["frame"], rows["y"], rows["week"]
    base = rows["models"]["production"]
    europe = np.isin(rows["league"], EUROPE)
    out = {"n": int(len(y)), "weeks": int(len(np.unique(weeks))), "threshold": THRESHOLD,
           "production": {**frame.summary(base, y), "ends_gap": ends_gap(base, y)},
           "retrained_on": rows["retrained_on"], "formula_coefficients": rows["formula_coefficients"],
           "correction_sd": rows["correction_sd"], "operational_share": float(rows["operational"].mean()),
           "candidates": {}}
    for name in ("gb", "formula"):
        p = rows["models"][name]
        d = frame.log_loss(p, y) - frame.log_loss(base, y)
        b = frame.brier(p, y) - frame.brier(base, y)
        goal = rows["goal_markets"][name] - rows["goal_markets"]["production"]
        c = {"measures": {**frame.summary(p, y), "ends_gap": ends_gap(p, y)},
             "log_loss": interval(frame, d, weeks), "brier": interval(frame, b, weeks),
             "leagues": interval(frame, d[rows["is_league"]], weeks[rows["is_league"]]),
             "cups": interval(frame, d[~rows["is_league"]], weeks[~rows["is_league"]]),
             "european_ties": {"n": int(europe.sum()), **interval(frame, d[europe], weeks[europe])},
             "operational_subset": {"n": int(rows["operational"].sum()),
                                    **interval(frame, d[rows["operational"]], weeks[rows["operational"]])},
             "goal_markets": {m: interval(frame, goal[:, i], weeks) for i, m in enumerate(frame.GOAL_MARKETS)},
             "goal_markets_mean": interval(frame, goal.mean(axis=1), weeks),
             "by_month": {m: {"n": int((np.char.find(rows["day"].astype(str), m) == 0).sum()),
                              "log_loss": float(d[np.char.find(rows["day"].astype(str), m) == 0].mean())}
                          for m in sorted({str(v)[:7] for v in rows["day"]})}}
        ci = c["log_loss"]["ci95"]
        rule = {"better_by_the_threshold": c["log_loss"]["delta"] <= -THRESHOLD,
                "interval_excludes_zero": bool(ci and ci[1] < 0),
                "brier_agrees": c["brier"]["delta"] < 0,
                "goal_markets_no_worse": c["goal_markets_mean"]["delta"] <= 0.0005,
                "european_ties_no_worse": c["european_ties"]["delta"] is None or c["european_ties"]["delta"] <= 0}
        c["decision_rule"] = rule
        c["may_be_proposed"] = all(rule[k] for k in ("better_by_the_threshold", "interval_excludes_zero",
                                                     "brier_agrees", "goal_markets_no_worse"))
        c["may_be_proposed_for_european_ties_too"] = c["may_be_proposed"] and rule["european_ties_no_worse"]
        out["candidates"][name] = c
    return out


def reestimate(rows):
    """SD of gb's paired differences only, never their mean."""
    import numpy as np
    frame, y = rows["frame"], rows["y"]
    d = frame.log_loss(rows["models"]["gb"], y) - frame.log_loss(rows["models"]["production"], y)
    sd = float(np.std(d, ddof=1))
    return {"n": int(len(d)), "sd": sd, "planning_effect": PLANNING_EFFECT, "fixtures_required": fixtures_required(sd)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--unblind", action="store_true", help="outcome metrics, once the target is reached")
    parser.add_argument("--interim", action="store_true", help="allow --unblind early; labelled a protocol deviation")
    parser.add_argument("--reestimate", action="store_true", help=f"one-time blinded sample-size re-estimate at {REESTIMATE_AT}")
    args = parser.parse_args()
    check_pins()
    status = {"protocol": "P13", "generated_at": datetime.now(timezone.utc).isoformat(),
              "evaluator_sha256": digest(__file__), "start": START, "target": TARGET, "blinded": not args.unblind}
    if not (args.unblind or args.reestimate):
        status["accrual"] = accrual()
        (HERE / "status_P13.json").write_text(json.dumps(status, indent=2) + "\n")
        print(json.dumps(status["accrual"], indent=2))
        return
    doc = extract()
    if doc["database_says"] != "production":
        raise SystemExit(f"P13 is analysed on production (read-only); this database says it is {doc['database_says']}")
    rows, excluded = build(doc)
    n = 0 if rows is None else len(rows["y"])
    status.update(extracted_at=doc["extracted_at"], database_role=doc["database_role"], accrued=n, exclusions=excluded)
    if args.reestimate:
        if n < REESTIMATE_AT:
            raise SystemExit(f"P13: {n} fixtures accrued; re-estimation needs {REESTIMATE_AT}")
        status["reestimate"] = reestimate(rows)
        print(json.dumps(status, indent=2))
        return
    if n < TARGET and not args.interim:
        raise SystemExit(f"P13: {n} of {TARGET} fixtures; refusing to unblind before the registered target")
    status["results"] = analyse(rows)
    if n < TARGET:
        status["results"]["label"] = "INTERIM - protocol deviation; not decision-grade"
    (HERE / "results_P13.json").write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
