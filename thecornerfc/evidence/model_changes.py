"""The model change record: every change to a model that was proposed, what it was expected to
do, what testing showed, what was decided, and how it has done since.

A change is a file, experiments/changes/MC-0000.json, with two parts:

    registration   what was written down before the test: what, why, how, the hypothesis, the
                   expected improvement and the success criteria. Never edited afterwards.
    events         what happened next, in order: a status, a result, a decision, a deployment,
                   a reversal, a correction. Only ever added to.

The export copies both into the database (model_changes, model_change_events), which refuses any
update or delete, so the first version recorded is the one that stands: a file edited later is
reported as differing from the record and the record is what the site shows. A mistake is put
right with a correction event.

Three things keep an experiment from passing as a production result. A change counts as deployed
only through a `deployed` event, never through its status. A result a file gives is always an
experiment's (a backtest, a development figure or a registered prospective test). And how a
deployed change has done since, the forward record, is never read from a file: forward() works
it out from the predictions stored before each kickoff.

Nothing here changes a model, and nothing is accepted or deployed by this module.
"""
import hashlib
import json
import logging
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .. import config

log = logging.getLogger(__name__)

REGISTER = Path(__file__).resolve().parents[2] / "experiments" / "changes"
STATUSES = ("Proposed", "Testing", "Accepted", "Rejected", "Reverted", "Inconclusive")
COMPONENTS = ("Club rank", "Match projection", "Match probabilities", "Goal markets", "Line-ups and injuries",
              "Player ranks", "National teams", "Betting rule", "Fantasy points", "Whole model")
MODELS = ("club", "player", "lineup", "match", "betting", "fantasy", "national")
KINDS = ("experiment", "production change")
EVENTS = ("status", "result", "decision", "deployed", "reverted", "correction")
EVALUATIONS = ("development", "backtest", "prospective")
METRICS = ("log_loss", "brier", "rps", "accuracy", "calibration_error", "goal_markets_log_loss", "mse", "mae", "roi", "other")
UNSEEN = ("yes", "partly", "no")
REGISTRATION_TEXT = ("title", "what", "why", "how", "hypothesis", "success_criteria")
NOT_SPECIFIED = "Not specified"
FORWARD_MINIMUM = 1000              # live matches before a forward record is read as anything
_ID = re.compile(r"^MC-[0-9]{4}$")
_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


# ---- the files -------------------------------------------------------------------------------

def digest(value):
    """The identity of a registration or an event: the hash of its content, whatever the order
    of its keys or the layout of its file."""
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _day(value):
    return isinstance(value, str) and bool(_DAY.match(value)) and _parses(value)


def _parses(value):
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def problems(change):
    """What is wrong with one change, as a list of sentences. Empty when it can be recorded."""
    out = []
    if not isinstance(change, dict) or set(change) != {"id", "registration", "events"}:
        return ["a change has exactly three parts: id, registration and events"]
    cid, reg, events = change["id"], change["registration"], change["events"]
    if not isinstance(cid, str) or not _ID.match(cid):
        out.append("the id is MC- and four digits")
    if not isinstance(reg, dict):
        return out + ["the registration is an object"]
    for key in REGISTRATION_TEXT:
        if not isinstance(reg.get(key), str) or not reg[key].strip():
            out.append(f"registration.{key} is missing")
    for key in ("recorded", "date"):
        if not _day(reg.get(key)):
            out.append(f"registration.{key} is a date (YYYY-MM-DD)")
    if not isinstance(reg.get("retrospective"), bool):
        out.append("registration.retrospective says whether this was written after the test (true or false)")
    for key, allowed in (("component", COMPONENTS), ("model", MODELS), ("kind", KINDS)):
        if reg.get(key) not in allowed:
            out.append(f"registration.{key} is one of: {', '.join(allowed)}")
    expected = reg.get("expected")
    if not isinstance(expected, dict) or set(expected) != {"improves", "metrics", "betting", "confidence", "evidence"}:
        out.append("registration.expected has improves, metrics, betting, confidence and evidence (null where none was recorded)")
    else:
        for key in ("improves", "betting", "confidence", "evidence"):
            if expected[key] is not None and (not isinstance(expected[key], str) or not expected[key].strip()):
                out.append(f"registration.expected.{key} is text, or null when none was recorded")
        if not isinstance(expected["metrics"], list):
            out.append("registration.expected.metrics is a list (empty when no number was recorded)")
        else:
            for m in expected["metrics"]:
                if not isinstance(m, dict) or m.get("metric") not in METRICS or not _number(m.get("delta")) \
                        or not isinstance(m.get("source"), str) or not m["source"].strip():
                    out.append("an expected metric has a metric, a delta and the source that recorded it before the test")
                elif any(k in m and not _number(m[k]) for k in ("low", "high")):
                    out.append("an expected metric's low and high are numbers")
    code = reg.get("code")
    if not isinstance(code, dict) or set(code) != {"commit", "experiment", "model_version"}:
        out.append("registration.code has commit, experiment and model_version (null where there is none)")
    elif any(v is not None and not isinstance(v, str) for v in code.values()):
        out.append("registration.code's values are text or null")
    if not isinstance(events, list):
        return out + ["events is a list"]
    last = reg.get("date") if _day(reg.get("date")) else None
    deployed = False
    for i, e in enumerate(events, 1):
        where = f"event {i}"
        if not isinstance(e, dict) or e.get("type") not in EVENTS:
            out.append(f"{where}: its type is one of {', '.join(EVENTS)}")
            continue
        if e.get("date_known_to", "day") not in ("day", "month"):
            out.append(f"{where}: date_known_to is day or month")
        if not _day(e.get("date")):
            out.append(f"{where}: needs a date (YYYY-MM-DD; the first of the month with date_known_to month)")
        elif last and e["date"] < last:
            out.append(f"{where}: is dated before the one above it; events are added at the end")
        else:
            last = e["date"]
        kind = e["type"]
        if kind in ("status", "decision"):
            if e.get("status") not in STATUSES or e.get("status") == "Reverted":
                out.append(f"{where}: its status is one of {', '.join(s for s in STATUSES if s != 'Reverted')} (a reversal is its own event)")
            if kind == "decision" and (not isinstance(e.get("reason"), str) or not e["reason"].strip()):
                out.append(f"{where}: a decision gives its reason")
            if kind == "status" and e.get("status") in ("Accepted", "Rejected", "Inconclusive"):
                out.append(f"{where}: {e.get('status')} is a decision, with its reason")
        elif kind == "result":
            if e.get("evaluation") not in EVALUATIONS:
                out.append(f"{where}: its evaluation is one of {', '.join(EVALUATIONS)}; a forward record is never written by hand")
            if e.get("metric") not in METRICS:
                out.append(f"{where}: its metric is one of {', '.join(METRICS)}")
            if e.get("unseen") not in UNSEEN:
                out.append(f"{where}: unseen says whether the matches were new to the change (yes, partly or no)")
            for key in ("label", "source", "meaningful"):
                if not isinstance(e.get(key), str) or not e[key].strip():
                    out.append(f"{where}: needs {key}")
            if not _number(e.get("delta")):
                out.append(f"{where}: needs the change in the metric (delta)")
            for key in ("baseline", "after"):
                if e.get(key) is not None and not _number(e[key]):
                    out.append(f"{where}: {key} is a number or null")
            if e.get("n") is not None and not (isinstance(e["n"], int) and e["n"] > 0):
                out.append(f"{where}: n is the number of matches, or null")
            period = e.get("period")
            if period is not None and not (isinstance(period, list) and len(period) == 2 and all(_day(d) for d in period)):
                out.append(f"{where}: period is two dates or null")
            interval = e.get("interval")
            if interval is not None and not (isinstance(interval, list) and len(interval) == 2 and all(_number(v) for v in interval)
                                             and _number(e.get("interval_level"))):
                out.append(f"{where}: interval is two numbers with its level, or null")
            market = e.get("vs_market")
            if market is not None and not (isinstance(market, dict) and isinstance(market.get("n"), int)
                                           and _number(market.get("model_minus_market")) and isinstance(market.get("note"), str)):
                out.append(f"{where}: vs_market has n, model_minus_market and a note, or is null")
        elif kind == "deployed":
            if reg.get("kind") != "production change":
                out.append(f"{where}: only a production change is deployed; an experiment that led to one is a separate change")
            if not isinstance(e.get("commit"), str) and e.get("commit") is not None:
                out.append(f"{where}: commit is text or null")
            deployed = True
        elif kind == "reverted":
            if not deployed:
                out.append(f"{where}: only a deployed change can be reverted")
            if not isinstance(e.get("reason"), str) or not e["reason"].strip():
                out.append(f"{where}: a reversal gives its reason")
        elif kind == "correction":
            if not isinstance(e.get("text"), str) or not e["text"].strip():
                out.append(f"{where}: a correction says what is corrected")
            of = e.get("of")
            if of != "registration" and not (isinstance(of, int) and 1 <= of < i):
                out.append(f"{where}: a correction is of the registration or of an earlier event's number")
    return out


def load(folder=None):
    """Every change in the register, in order of id. Raises ValueError naming each file that
    can't be recorded."""
    folder = Path(folder or REGISTER)
    changes, wrong = [], []
    for path in sorted(folder.glob("MC-*.json")):
        try:
            change = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            wrong.append(f"{path.name}: not JSON ({exc})")
            continue
        found = problems(change)
        if isinstance(change, dict) and change.get("id") != path.stem:
            found.append("the file is named after its id")
        wrong += [f"{path.name}: {p}" for p in found]
        changes.append(change)
    if wrong:
        raise ValueError("The model change register has problems:\n  " + "\n  ".join(wrong))
    return changes


def standing(events):
    """Where a change stands after its events: its status, whether it is deployed to production
    now, and the dates that matter."""
    status, deployed_on, reverted_on, decided_on, day_known = "Proposed", None, None, None, True
    for e in events:
        if e["type"] in ("status", "decision"):
            status = e["status"]
            decided_on = e["date"] if e["type"] == "decision" else decided_on
        elif e["type"] == "deployed":
            deployed_on, reverted_on, day_known = e["date"], None, e.get("date_known_to", "day") == "day"
        elif e["type"] == "reverted":
            status, reverted_on = "Reverted", e["date"]
    live = deployed_on is not None and reverted_on is None
    stage = "Reverted" if reverted_on else "Deployed to production" if live else \
        "Proposed" if status == "Proposed" else "Being tested" if status == "Testing" else \
        "Tested and rejected" if status == "Rejected" else "Tested, not deployed"
    return {"status": status, "stage": stage, "deployed": live, "deployed_on": deployed_on if live else None,
            "deployed_day_known": day_known if live else None, "reverted_on": reverted_on, "decided_on": decided_on}


# ---- the database ----------------------------------------------------------------------------

def sync(conn, changes):
    """Add what the register holds and the database doesn't. Nothing recorded is changed: where
    a file no longer matches what was recorded, the record stands and the difference is
    returned. Returns {"added": [...], "differs": [...]}."""
    config.require_db_write("record model changes")
    have = dict(conn.execute("select change_id, sha256 from model_changes").fetchall())
    seen = {}
    for change_id, seq, sha in conn.execute("select change_id, seq, sha256 from model_change_events").fetchall():
        seen.setdefault(change_id, {})[seq] = sha
    added, differs = [], []
    for change in changes:
        cid, sha = change["id"], digest(change["registration"])
        if cid not in have:
            conn.execute("insert into model_changes (change_id, registration, sha256) values (%s, %s::jsonb, %s)",
                         [cid, json.dumps(change["registration"], ensure_ascii=False), sha])
            added.append(cid)
        elif have[cid] != sha:
            differs.append(f"{cid}: the registration in the file is not the one recorded")
        events = seen.get(cid, {})
        if len(change["events"]) < len(events):
            differs.append(f"{cid}: the file has fewer events than the record")
        for seq, event in enumerate(change["events"], 1):
            sha = digest(event)
            if seq not in events:
                conn.execute("insert into model_change_events (change_id, seq, body, sha256) values (%s, %s, %s::jsonb, %s)",
                             [cid, seq, json.dumps(event, ensure_ascii=False), sha])
                added.append(f"{cid} event {seq}")
            elif events[seq] != sha:
                differs.append(f"{cid}: event {seq} in the file is not the one recorded")
    for cid in sorted(set(have) - {c["id"] for c in changes}):
        differs.append(f"{cid}: recorded, but its file has gone")
    conn.commit()
    return {"added": added, "differs": differs}


def recorded(conn):
    """The changes as the database holds them, with when each part was recorded."""
    out = {}
    for cid, registration, at in conn.execute(
            "select change_id, registration, recorded_at from model_changes order by change_id").fetchall():
        out[cid] = {"id": cid, "registration": registration, "recorded_at": at.isoformat(), "events": []}
    for cid, body, at in conn.execute(
            "select change_id, body, recorded_at from model_change_events order by change_id, seq").fetchall():
        out[cid]["events"].append({**body, "recorded_at": at.isoformat()})
    return list(out.values())


_SCORED = """f.status_short in ('FT', 'AET', 'PEN') and f.ft_home is not null and f.ft_away is not null
             and p.p_home is not null and p.p_draw is not null and p.p_away is not null"""
_HAPPENED = "case when f.ft_home > f.ft_away then p.p_home when f.ft_home = f.ft_away then p.p_draw else p.p_away end"
_BRIER = """power(p.p_home - (f.ft_home > f.ft_away)::int, 2) + power(p.p_draw - (f.ft_home = f.ft_away)::int, 2)
            + power(p.p_away - (f.ft_home < f.ft_away)::int, 2)"""


def monthly(conn, since="2021-07-01"):
    """The match model's result predictions by month: [{month, source, n, log_loss, brier}].
    source is "live" (stored before kickoff) or "backfill" (reconstructed afterwards with the
    code of the day it was made). A tie decided after 90 minutes counts as the draw it was."""
    rows = conn.execute(
        f"""select to_char(f.kickoff at time zone 'UTC', 'YYYY-MM'), p.source, count(*),
                   avg(-ln(greatest({_HAPPENED}, 1e-15))), avg({_BRIER})
            from fixture_predictions p join fixtures f using (fixture_id)
            where {_SCORED} and f.kickoff >= %s
            group by 1, 2 order by 1, 2""", [since]).fetchall()
    return [{"month": m, "source": s, "n": int(n), "log_loss": round(float(ll), 5), "brier": round(float(b), 5)}
            for m, s, n, ll, b in rows]


def _window(conn, start, end):
    """Live predictions of matches kicking off in [start, end): each fixture's stored chances
    and what happened."""
    return conn.execute(
        f"""select p.fixture_id, p.p_home, p.p_draw, p.p_away,
                   case when f.ft_home > f.ft_away then 0 when f.ft_home = f.ft_away then 1 else 2 end
            from fixture_predictions p join fixtures f using (fixture_id)
            where {_SCORED} and p.source = 'live' and f.kickoff >= %s and f.kickoff < %s""", [start, end]).fetchall()


def window_record(rows, market=None):
    """{n, log_loss, brier, vs_market} for rows of (fixture, home, draw, away, outcome).
    market: {fixture: [home, draw, away]} margin-free chances, for the fixtures that have them."""
    if not rows:
        return {"n": 0, "log_loss": None, "brier": None, "vs_market": None}
    ll = lambda p, y: -math.log(max(p[y], 1e-15))
    brier = lambda p, y: sum((p[k] - (k == y)) ** 2 for k in range(3))
    model = [([float(h), float(d), float(a)], y) for _, h, d, a, y in rows]
    out = {"n": len(rows), "log_loss": round(sum(ll(p, y) for p, y in model) / len(rows), 5),
           "brier": round(sum(brier(p, y) for p, y in model) / len(rows), 5), "vs_market": None}
    priced = [(p, market[f], y) for (f, *_), (p, y) in zip(rows, model) if market and f in market]
    if priced:
        mine = sum(ll(p, y) for p, _, y in priced) / len(priced)
        theirs = sum(ll(q, y) for _, q, y in priced) / len(priced)
        out["vs_market"] = {"n": len(priced), "model_log_loss": round(mine, 5), "market_log_loss": round(theirs, 5),
                            "model_minus_market": round(mine - theirs, 5)}
    return out


def forward_verdict(after, before, minimum=FORWARD_MINIMUM):
    """What the forward record can be said to show, in words. It never says a change worked on
    the raw scores alone: the fixtures differ between two periods, so the comparison that counts
    is the distance from the bookmakers' prices on each period's own matches."""
    if after["n"] < minimum:
        return "Too early to say", f"{after['n']} live matches since deployment; read from {minimum:,}."
    if before["n"] < minimum:
        return "Cannot be judged", "There is no live record of comparable size from before the deployment to compare with."
    a, b = after["vs_market"], before["vs_market"]
    if not a or not b or min(a["n"], b["n"]) < minimum // 2:
        return "Cannot be judged", "Too few matches with bookmakers' prices on one side of the deployment."
    moved = a["model_minus_market"] - b["model_minus_market"]
    if moved < 0:
        return "Still appears beneficial", "The model is closer to the bookmakers' prices than before the deployment. Other changes and a different run of fixtures could also explain it."
    return "No benefit visible", "The model is no closer to the bookmakers' prices than before the deployment."


def forward(conn, changes, now=None, market_for=None):
    """How each deployed match-model change has done on matches since: {change id: record}.

    The window runs from the day it was deployed to the day the next one was (or to now), so a
    later change's matches are not credited to an earlier one, and it is set beside the live
    record of the same length just before. market_for(since) gives {fixture: chances} and is
    asked once, only when there is a window to compare."""
    now = now or datetime.now(timezone.utc)
    live = [(standing(c["events"]), c["id"]) for c in changes if c["registration"]["model"] == "match"]
    undated = {cid: {"from": None, "to": None, "after": None, "before": None, "deployed_with": [],
                     "verdict": "Cannot be judged", "why": "The day it went live was not recorded, so there is no line to measure from."}
               for where, cid in live if where["deployed"] and not where["deployed_day_known"]}
    deployed = sorted((where["deployed_on"], cid) for where, cid in live if where["deployed"] and where["deployed_day_known"])
    if not deployed:
        return undated
    day = lambda text: datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    windows = []
    for i, (on, cid) in enumerate(deployed):
        start = day(on)
        later = [day(d) for d, _ in deployed[i + 1:] if d > on]
        end = min(later[0], now) if later else now
        windows.append((cid, start, end, start - (end - start)))
    market = market_for(min(w[3] for w in windows)) if market_for else None
    shared = {}
    for cid, start, _, _ in windows:
        shared.setdefault(start, []).append(cid)
    out = {}
    for cid, start, end, earlier in windows:
        after = window_record(_window(conn, start, end), market)
        before = window_record(_window(conn, earlier, start), market)
        verdict, why = forward_verdict(after, before)
        out[cid] = {"from": start.date().isoformat(), "to": end.date().isoformat(), "after": after, "before": before,
                    "verdict": verdict, "why": why,
                    "deployed_with": [other for other in shared[start] if other != cid]}
    return {**undated, **out}


# ---- the document the site reads -------------------------------------------------------------

def from_files(changes):
    """The register as the document wants it, for a run that could store nothing."""
    return [{"id": c["id"], "registration": c["registration"], "recorded_at": None,
             "events": [{**e, "recorded_at": None} for e in c["events"]]} for c in changes]


def document(changes, *, environment, generated_at, current=None, series=None, forward_record=None,
             differs=(), stored=True):
    """The administrator's model_changes document. changes are as recorded (recorded()), or
    from the files when nothing could be stored (stored=False, and the page says so)."""
    forward_record = forward_record or {}
    out = []
    for c in changes:
        where = standing(c["events"])
        results = [{**e, "experimental": True} for e in c["events"] if e["type"] == "result"]
        out.append({"id": c["id"], **c["registration"], "recorded_at": c["recorded_at"], **where,
                    "events": c["events"], "results": results, "forward": forward_record.get(c["id"])})
    return {"generated_at": generated_at, "environment": environment, "stored": stored, "differs": list(differs),
            "not_specified": NOT_SPECIFIED, "statuses": list(STATUSES), "components": list(COMPONENTS),
            "current": current, "series": series or [], "changes": out}
