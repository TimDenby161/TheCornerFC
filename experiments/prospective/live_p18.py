"""P18: the stored challenger against the live model (MC-0029, experiments/challenger/DESIGN.md).

For each finished fixture, both models' predictions are their rows in challenger_predictions,
captured and written before kickoff, whichever model was live: both existed before the match.
The switch log says which was live, for the counts. Judged by P15's confidence sequence
(live_p15.track), imported, with the whole 5% on the one comparison.

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
SWITCHES_SQL = "select switched_at, live from match_model_switches order by switched_at"
CHALLENGER_SQL = """
    select c.fixture_id, c.model, c.p_home, c.p_draw, c.p_away, c.captured_at, c.written_at
    from challenger_predictions c join fixtures f using (fixture_id)
    where f.kickoff >= %(start)s and f.status_short = any(%(statuses)s)
      and c.captured_at < f.kickoff and c.written_at < f.kickoff"""


def extract(conn):
    """The finished fixtures and both models' rows since START, and the switch log: three small
    reads."""
    if START is None:
        return {"fixtures": [], "challenger": [], "switches": []}
    args = {"start": START, "statuses": list(STATUSES)}
    return {"fixtures": [list(r) for r in conn.execute(FIXTURES_SQL, args)],
            "challenger": [list(r) for r in conn.execute(CHALLENGER_SQL, args)],
            "switches": [list(r) for r in conn.execute(SWITCHES_SQL)]}


def result(home, away):
    return 0 if home > away else 1 if home == away else 2


def live_at(switches, kickoff):
    """The model the switch named at kickoff: 'base' until the first switch."""
    live = "base"
    for at, model in switches:
        if p13.stamp(at) <= p13.stamp(kickoff):
            live = model
    return live


def pairs(doc):
    """Per fixture in kickoff order: (kickoff, outcome, {model: (p_home, p_draw, p_away)}, live
    model). Returns (rows, exclusions)."""
    stored = {(fid, model): (ph, pd, pa) for fid, model, ph, pd, pa, *_ in doc["challenger"]}
    rows, excluded = [], {"missing_a_model_before_kickoff": 0}
    for fid, kickoff, fth, fta in sorted(doc["fixtures"], key=lambda f: (str(f[1]), f[0])):
        if not all((fid, m) in stored for m in MODELS):
            excluded["missing_a_model_before_kickoff"] += 1
            continue
        rows.append((kickoff, result(fth, fta), {m: stored[(fid, m)] for m in MODELS}, live_at(doc["switches"], kickoff)))
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
