"""P18: the stored challenger against the live model (MC-0029, experiments/challenger/DESIGN.md).

For each finished fixture, the live model's latest prospective snapshot before kickoff says
which model made it ('base' or 'a18'); the other model's prediction is its row in
challenger_predictions, written before kickoff. Both existed before the match. Judged by P15's
confidence sequence (live_p15.track), imported, with the whole 5% on the one comparison.

Run with P16 and P17 by live_tracking.py, which stores the one document. Read-only. No numpy.
"""
import importlib.util
import math
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent

# Registered in PROTOCOLS.md; change only by a dated amendment there.
CHANGE = "MC-0029"
START = None                         # the first kickoff day after the release reaches main, set by that amendment
ALPHA = 0.05
MODELS = ("base", "a18")
STATUSES = ("FT", "AET", "PEN")

_spec = importlib.util.spec_from_file_location("live_p15", HERE / "live_p15.py")
p15 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p15)
p13 = p15.p13

FIXTURES_SQL = """
    select f.fixture_id, f.kickoff, f.ft_home, f.ft_away
    from fixtures f
    where f.kickoff >= %(start)s and f.status_short = any(%(statuses)s)
      and f.ft_home is not null and f.ft_away is not null"""
SNAPSHOTS_SQL = """
    select s.fixture_id, s.captured_at, s.created_at, s.p_home, s.p_draw, s.p_away, s.inputs->>'match_model'
    from match_prediction_snapshots s join fixtures f using (fixture_id)
    where s.source = 'prospective' and f.kickoff >= %(start)s and f.status_short = any(%(statuses)s)
      and s.captured_at < f.kickoff and s.created_at < f.kickoff"""
CHALLENGER_SQL = """
    select c.fixture_id, c.model, c.p_home, c.p_draw, c.p_away, c.captured_at, c.written_at
    from challenger_predictions c join fixtures f using (fixture_id)
    where f.kickoff >= %(start)s and f.status_short = any(%(statuses)s)
      and c.captured_at < f.kickoff and c.written_at < f.kickoff"""


def extract(conn):
    """The finished fixtures, the live snapshots and the challenger rows since START: three
    small reads, keyed on the fixtures' kickoff index."""
    if START is None:
        return {"fixtures": [], "snapshots": [], "challenger": []}
    args = {"start": START, "statuses": list(STATUSES)}
    keys = ("fixture_id", "captured_at", "created_at", "p_home", "p_draw", "p_away", "match_model")
    return {"fixtures": [list(r) for r in conn.execute(FIXTURES_SQL, args)],
            "snapshots": [dict(zip(keys, r)) for r in conn.execute(SNAPSHOTS_SQL, args)],
            "challenger": [list(r) for r in conn.execute(CHALLENGER_SQL, args)]}


def result(home, away):
    return 0 if home > away else 1 if home == away else 2


def pairs(doc):
    """Per fixture in kickoff order: (kickoff, outcome, {model: (p_home, p_draw, p_away)}, live
    model). Returns (rows, exclusions)."""
    kick = {f[0]: f[1] for f in doc["fixtures"]}
    latest = p13.latest_before_kickoff(doc["snapshots"], kick)
    other = {(fid, model): (ph, pd, pa) for fid, model, ph, pd, pa, *_ in doc["challenger"]}
    rows, excluded = [], {"no_snapshot_before_kickoff": 0, "snapshot_from_before_the_two_models": 0,
                          "no_challenger_row_before_kickoff": 0}
    for fid, kickoff, fth, fta in sorted(doc["fixtures"], key=lambda f: (str(f[1]), f[0])):
        snap = latest.get(fid)
        if snap is None:
            excluded["no_snapshot_before_kickoff"] += 1
            continue
        live = snap["match_model"]
        if live not in MODELS:
            excluded["snapshot_from_before_the_two_models"] += 1
            continue
        rival = MODELS[1 - MODELS.index(live)]
        if (fid, rival) not in other:
            excluded["no_challenger_row_before_kickoff"] += 1
            continue
        probs = {live: (snap["p_home"], snap["p_draw"], snap["p_away"]), rival: other[(fid, rival)]}
        rows.append((kickoff, result(fth, fta), probs, live))
    return rows, excluded


def week(kickoff):
    day = date.fromisoformat(str(kickoff)[:10])
    y, w, _ = day.isocalendar()
    return y * 100 + w


def record(doc):
    """P18's part of the tracker's document."""
    rows, excluded = pairs(doc)
    loss = lambda p, y: -math.log(max(float(p[y]), 1e-12))
    diffs = [loss(probs["a18"], y) - loss(probs["base"], y) for _, y, probs, _ in rows]
    track = p15.track(diffs, [week(k) for k, *_ in rows], ALPHA)
    return {"protocol": "P18", "start": START, "alpha": ALPHA, "comparisons": 1, "exclusions": excluded,
            "live_counts": {m: sum(1 for *_, live in rows if live == m) for m in MODELS},
            "changes": {CHANGE: track}, "settings": {CHANGE: {"setting": {"challenger": "a18", "against": "base"},
                                                              "source": "experiments/challenger/DESIGN.md"}}}
