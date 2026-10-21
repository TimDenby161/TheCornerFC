"""P16: the club-rank release (MC-0028: movers, new clubs and shots for xG) against the model it
replaced, on live matches as they are played (PROTOCOLS.md, experiments/club_rank_release/DESIGN.md).

Each fixture's latest prospective snapshot before kickoff from the released version is scored as
stored. The version before it is re-created from that snapshot: its projected goals moved by the
change in the match-rank gap between the old club rank and the released one, both replayed by the
research frame. The two are judged by P15's confidence sequence (live_p15.track), imported, with
the whole 5% on this one comparison.

    python experiments/prospective/live_p16.py            # prints the record; stores nothing
    python experiments/prospective/live_p16.py --store    # and stores it for the Admin area

Read-only apart from --store, which writes the one administrator's document `live_tracking`, in
P15's shape. No API calls, no odds. Needs numpy (requirements-live.txt); run it against production
(read-only locally, where it can't store).
"""
import argparse
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
EXPERIMENTS = ROOT / "experiments"
FRAME, SHOTS, RATING = EXPERIMENTS / "research_frame", EXPERIMENTS / "shots_proxy", EXPERIMENTS / "rating_dynamics"
CHANGES = EXPERIMENTS / "changes"

# Registered in PROTOCOLS.md; change only by a dated amendment there.
CHANGE = "MC-0028"
START = "2026-10-15"                 # first kickoff day (UTC) that counts
ALPHA = 0.05                         # all of it on the one comparison
TOLERANCE = 1e-8
STATUSES = ("FT", "AET", "PEN")      # a tie level at 90 minutes is a draw
SHOTS_SETTING = {"goals_weight": 0.5, "k": 10.0}                 # shots_proxy/chosen.json
MOVEMENT = {"pull": 0.5, "boost": 0.5, "tau": 40.0}              # rating_dynamics/chosen.json: combined
# The match model's files in the version before the release (tests/test_model_fingerprints.py on
# 2026-10-14). The released version is one whose ranking.py differs and whose others do not.
BEFORE = {
    "ranking.py": "2694a1777da8d4353960a4a130ba71c758bb5da6a76989ab506f8e1c29fb0832",
    "predictions.py": "462dd8ca22d49df66c1716d12cf68665ee8f8a3eeb9104be98dccab1cc1601a0",
    "injuries.py": "3d96c474df0b6d7980484f9d874e0bbca9ee1a3fc65060f68466f770b6e9f35f",
    "player_ratings.py": "73f8e45028493eae12ddbc566360795e09a6fa08cb1789f6bb7017e55d3fd898",
    "match_snapshots.py": "c4ce9c7df94d9c9f9f030c9dbb14ef2e0c558548ebeb2b3fba20de7b921ca566",
}
# Amendment 16 (2026-10-21): files a released version may also differ in. A player-rank change
# (MC-0030 on, and the owner's later tuning of it) moves the predicted XIs' ratings, which reach the
# match model, so it makes a new match version; it is in both sides of every paired comparison
# here (both start from the same stored snapshot), so it can't tilt one
MAY_ALSO_DIFFER = ("player_ratings.py",)
CLOSED = "Live tracking of every candidate (P15) closed when MC-0028 changed production's club rank; P16 tracks the release"

_spec = importlib.util.spec_from_file_location("live_p15", HERE / "live_p15.py")
p15 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p15)
p13 = p15.p13

# Both ranks and the judgement are these files as they were at registration.
PINNED = {
    HERE / "live_p15.py": "138542daab78cebda5d2f86356959a323207501616380854f6d4d809e9e7752f",
    FRAME / "frame.py": "dd5a3e1e2973f0574234e8d120b1a9c99187bb1b999a11eaca250fd698671fba",
    FRAME / "extract.py": "b35e7ac5513def5cf8f3bd3da085cd899064243df952332a4fb42164bbd96169",
    SHOTS / "run.py": "c1d96bd6878fda803bc7eed6cb6c7ef34c2d927d89a7eac1889036e10ec378bc",
    SHOTS / "chosen.json": "2b3db2eec481ad7b0193aa3f4915bb1c5e0f1a2de53edc0ed7b51426f9f7114d",
    RATING / "chosen.json": "83bac50319f1289218105488296c45f75380d646938ca7009c90e6d59d6d0112",
}
SNAPSHOT_SQL, SKIP_QUERIES = p15.SNAPSHOT_SQL, p15.SKIP_QUERIES
VERSIONS_SQL = "select model_version_id, configuration->'source_digests' from model_versions where model_type = 'match'"


def check_pins():
    wrong = [str(p.relative_to(ROOT)) for p, want in PINNED.items() if p13.digest(p) != want]
    if wrong:
        raise SystemExit("P16's files have changed since registration: " + ", ".join(wrong))
    movement = json.loads((RATING / "chosen.json").read_text())["chosen"]["combined"]["change"]
    shots = json.loads((SHOTS / "chosen.json").read_text())["chosen"]
    if movement != MOVEMENT or {k: shots[k] for k in SHOTS_SETTING} != SHOTS_SETTING:
        raise SystemExit("P16's settings are not the ones its experiments chose")


def released(versions):
    """The match-model version ids that are the release: ranking.py changed, and nothing else but
    the files in MAY_ALSO_DIFFER (amendment 16)."""
    out = set()
    for vid, digests in versions:
        digests = digests or {}
        if digests.get("ranking.py") not in (None, BEFORE["ranking.py"]) and \
                all(digests.get(name) == want for name, want in BEFORE.items()
                    if name != "ranking.py" and name not in MAY_ALSO_DIFFER):
            out.add(vid)
    return out


# ---- the database ----------------------------------------------------------------------------

def extract():
    """P15's read (the research frame's queries with the cut moved to tomorrow, no odds, and the
    prospective snapshots), plus the match model's versions."""
    frame_extract = p13.load("p16_frame_extract", FRAME / "extract.py")
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
        doc["versions"] = [[vid, digests] for vid, digests in conn.execute(VERSIONS_SQL)]
    doc["extracted_at"] = datetime.now(timezone.utc).isoformat()
    return doc


# ---- the two models --------------------------------------------------------------------------

def build(doc, start=START):
    """Per accrued fixture, in kickoff order: the release's stored probabilities and the old
    version's re-created ones. Returns (rows, exclusions, checks); rows is None before the first."""
    import numpy as np
    frame = p13.load("frame", FRAME / "frame.py")
    sys.modules["frame"] = frame
    shots = p13.load("p16_shots_proxy", SHOTS / "run.py")
    frame.FINAL_END = "9999-12-31"
    beta = np.array(json.loads((SHOTS / "chosen.json").read_text())["beta"])

    ours = released(doc["versions"])
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

    regulation = np.isin(data.status, STATUSES) & ~np.isnan(data.ft_home) & ~np.isnan(data.ft_away)
    index = np.array([data.index[f] for f in picked if f in data.index and regulation[data.index[f]]], dtype=int)
    index.sort()
    hx = np.array([picked[int(f)]["home_xg"] for f in data.fixture_id[index]], dtype=float)
    ax = np.array([picked[int(f)]["away_xg"] for f in data.fixture_id[index]], dtype=float)
    stored = np.array([[picked[int(f)][k] for k in ("p_home", "p_draw", "p_away")] for f in data.fixture_id[index]])
    stored = stored.reshape(len(index), 3)
    again = frame.outcome_probabilities(hx, ax) if len(index) else stored
    same = np.abs(again - stored).max(axis=1) <= TOLERANCE if len(index) else np.zeros(0, dtype=bool)
    counted = sum(1 for f, k in kick.items() if k[:10] >= start)
    excluded = {"latest_snapshot_from_the_old_version": len(latest) - len(picked),
                "no_snapshot_before_kickoff_or_no_90_minute_score": counted - (len(latest) - len(picked)) - len(index),
                "not_reproduced_by_the_registered_probability_step": int((~same).sum())}
    index, stored, hx, ax = index[same], stored[same], hx[same], ax[same]
    if not len(index):
        return None, excluded, {}

    oh, oa = frame.replay(data).match_rank()
    nh, na = shots.replay(data, beta, SHOTS_SETTING, MOVEMENT).match_rank()
    shift = ((oh - oa) - (nh - na))[index] / 100
    before = frame.outcome_probabilities(*frame.moved(hx, ax, shift))
    kept = [picked[int(f)] for f in data.fixture_id[index]]
    gaps = np.abs(np.concatenate([nh[index] - [s["home_match_rank"] for s in kept], na[index] - [s["away_match_rank"] for s in kept]]))
    checks = {"frame_against_stored_match_rank": {"mean": float(gaps.mean()), "largest": float(gaps.max())},
              "rank_gap_moved_by": {"mean": float(np.abs(shift).mean()) * 100, "largest": float(np.abs(shift).max()) * 100}}
    return {"frame": frame, "y": data.result[index], "week": data.week[index], "day": data.day[index],
            "released": stored, "before": before}, excluded, checks


def changes_in_register():
    return sorted(p.stem for p in CHANGES.glob("MC-*.json"))


def record(rows, excluded, checks, *, environment, generated_at):
    """The document the Admin area reads, in P15's shape: the release is the one change tracked."""
    base = {"protocol": "P16", "generated_at": generated_at, "environment": environment, "start": START,
            "planned": p15.PLANNED, "minimum": {"matches": p15.MINIMUM_MATCHES, "weeks": p15.MINIMUM_WEEKS}, "bar": p15.BAR,
            "alpha": ALPHA, "comparisons": 1, "exclusions": excluded, "checks": checks,
            "not_run": {cid: CLOSED for cid in changes_in_register() if cid != CHANGE},
            "settings": {CHANGE: {"setting": {**SHOTS_SETTING, **MOVEMENT}, "source": "experiments/club_rank_release/DESIGN.md"}}}
    if rows is None:
        return {**base, "n": 0, "weeks": 0, "to": None, "changes": {CHANGE: p15.track([], [], ALPHA)}}
    frame, y = rows["frame"], rows["y"]
    old = frame.log_loss(rows["before"], y)
    new = frame.log_loss(rows["released"], y)
    weeks = [int(w) for w in rows["week"]]
    return {**base, "n": int(len(y)), "weeks": len(set(weeks)), "to": str(max(rows["day"])),
            "production_log_loss": float(old.mean()), "released_log_loss": float(new.mean()),
            "changes": {CHANGE: p15.track([float(v) for v in new - old], weeks, ALPHA)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", action="store_true", help="store the record for the Admin area (needs a run that may write)")
    args = parser.parse_args()
    check_pins()
    doc = extract()
    rows, excluded, checks = build(doc)
    out = record(rows, excluded, checks, environment=doc["database_says"], generated_at=doc["extracted_at"])
    print(json.dumps({"n": out["n"], "weeks": out["weeks"], "to": out["to"], "exclusions": excluded, "checks": checks,
                      "called": out["changes"][CHANGE]["called"]}, indent=2))
    if args.store:
        from thecornerfc.pipeline import db
        from thecornerfc.publish import site_files
        with db.connect() as conn:          # a run that may write, to its own environment's database only
            site_files.store_admin_doc(conn, "live_tracking", out)
        print("stored")


if __name__ == "__main__":
    main()
