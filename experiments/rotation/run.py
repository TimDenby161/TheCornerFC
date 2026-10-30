"""Rotation: do a side's line-up changes help predict its next match? (DESIGN.md)

Takes the stored pre-match projections and, in matches where it is known for both sides, moves
the expected margin by a value per line-up change:

    A  prior changes: the changes each side made in its previous match (known days before)
    B  changes now: the changes each side made in this match (known an hour before kickoff)

BETA and GAMMA are chosen on validation (2023-07-01 to 2024-06-30) and nowhere else. The test
period (2024-07-01 to 2026-10-11) and the holdout (2021-07-01 to 2023-06-30) are scored once
with them. A historical reconstruction, not a prospective record; it reads no odds.

Nothing is written to the database. The XIs are read once, read-only, and frozen in
inputs.json.gz (gitignored); the fixtures and projections come from the research frame's frozen
inputs. Later runs don't touch the database.

    python experiments/rotation/run.py             # evaluate from the frozen inputs
    python experiments/rotation/run.py --refresh   # read the XIs first (read-only)
"""
import argparse
import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "research_frame"))
import frame as F  # noqa: E402

HERE = Path(__file__).parent
INPUTS = HERE / "inputs.json.gz"
OUT = HERE / "results.json"
CUT = "2026-10-12"

HOLDOUT, VALIDATION, TEST = ("2021-07-01", "2023-07-01"), ("2023-07-01", "2024-07-01"), ("2024-07-01", CUT)
GAP_DAYS = 15                                  # longest gap between a side's consecutive matches
GRID = tuple(round(0.005 * i, 3) for i in range(-10, 11))
FAMILY = 2                                     # candidates, for the Bonferroni level
LEVEL = 1 - 0.05 / FAMILY
BANDS = ((0, 1, "0-1"), (2, 3, "2-3"), (4, 5, "4-5"), (6, 11, "6+"))
GUARD = 0.0005


# ---- the XIs, read once ----------------------------------------------------------------------

def refresh():
    from thecornerfc.pipeline import db
    doc = {"cut": CUT}
    with db.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("set local statement_timeout = '120s'")
        doc["database_role"] = conn.execute("select current_user").fetchone()[0]
        doc["read_only"] = conn.execute("select current_setting('transaction_read_only')").fetchone()[0]
        doc["database"] = conn.execute("select current_database()").fetchone()[0]
        doc["environment"] = conn.execute("select site.environment()").fetchone()[0] \
            if conn.execute("select to_regprocedure('site.environment()')").fetchone()[0] else None
        cur = conn.execute("""
            select fp.fixture_id, fp.team_id, array_agg(fp.player_id order by fp.player_id)
            from fixture_players fp join fixtures f using (fixture_id)
            where fp.started and f.kickoff < %(cut)s and f.status_short in ('FT', 'AET', 'PEN')
            group by fp.fixture_id, fp.team_id""", {"cut": CUT})
        doc["starters"] = [list(r) for r in cur.fetchall()]
    doc["extracted_at"] = datetime.now(timezone.utc).isoformat()
    with gzip.open(INPUTS, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh)
    print("wrote", INPUTS, len(doc["starters"]), "XIs; role", doc["database_role"],
          "read only", doc["read_only"], "environment", doc["environment"])


# ---- line-up changes -------------------------------------------------------------------------

def changes(data, starters):
    """(prior, now): (n, 2) arrays of each side's prior changes and changes now (home, away),
    NaN where not defined. data's fixtures are in kickoff order."""
    xi = {(f, t): frozenset(p) for f, t, p in starters if len(p) == 11}
    now = np.full((data.n, 2), np.nan)
    prior = np.full((data.n, 2), np.nan)
    last = {}                                  # team -> index of its latest match so far
    for i in range(data.n):
        fid = data.fixture_id[i]
        for side, team in enumerate((data.home[i], data.away[i])):
            j = last.get(team)
            if j is not None and data.ordinal[i] - data.ordinal[j] <= GAP_DAYS:
                side_j = 0 if data.home[j] == team else 1
                mine, before = xi.get((fid, team)), xi.get((data.fixture_id[j], team))
                if mine is not None and before is not None:
                    now[i, side] = len(mine - before)
                prior[i, side] = now[j, side_j]
            last[team] = i
    return prior, now


# ---- measures --------------------------------------------------------------------------------

def scored(data):
    return (np.isin(data.status, ("FT", "AET", "PEN")) & ~np.isnan(data.ft_home) & ~np.isnan(data.ft_away)
            & ~np.isnan(data.pred["home_xg"]) & ~np.isnan(data.pred["away_xg"]))


def period(data, span):
    return (data.day >= span[0]) & (data.day < span[1])


def probabilities(data, rows, by):
    hx, ax = data.pred["home_xg"][rows], data.pred["away_xg"][rows]
    if by is not None:
        hx, ax = F.moved(hx, ax, by)
    return F.outcome_probabilities(hx, ax), F.goal_markets(hx, ax)


def shift(c, rows, value):
    return value * (c[rows, 0] - c[rows, 1])


def grid_losses(data, rows, c):
    out = []
    for v in GRID:
        p, _ = probabilities(data, rows, shift(c, rows, v))
        out.append({"value": v, "log_loss": float(F.log_loss(p, data.result[rows]).mean())})
    return out


def pick(grid):
    return min(grid, key=lambda g: (round(g["log_loss"], 12), abs(g["value"])))["value"]


def evaluate(data, rows, c, value):
    """Candidate against the stored projection on rows, at the Bonferroni level and at 95%."""
    p_base, g_base = probabilities(data, rows, None)
    by = np.where(np.isnan(c[rows]).any(axis=1), 0.0, shift(np.nan_to_num(c), rows, value))
    p_cand, g_cand = probabilities(data, rows, by)
    out = F.compare(data, rows, p_base, p_cand, LEVEL)
    d = F.log_loss(p_cand, data.result[rows]) - F.log_loss(p_base, data.result[rows])
    out["log_loss_95"] = F.paired_interval(d, data.week[rows], 0.95)
    events = F.goal_events(data, rows)
    out["goal_markets"] = {name: float((F.binary_log_loss(g_cand[:, k], events[:, k])
                                        - F.binary_log_loss(g_base[:, k], events[:, k])).mean())
                           for k, name in enumerate(F.GOAL_MARKETS)}
    return out


def errors_by_band(data, rows, c):
    """The model's goal-difference error from each side's view, by band of changes."""
    idx = np.flatnonzero(rows)
    err, band_of, weeks = [], [], []
    margin = data.ft_home - data.ft_away
    projected = data.pred["home_xg"] - data.pred["away_xg"]
    for side, sign in ((0, 1), (1, -1)):
        ok = idx[~np.isnan(c[idx, side])]
        err.append(sign * (margin[ok] - projected[ok]))
        band_of.append(c[ok, side])
        weeks.append(data.week[ok])
    err, band_of, weeks = np.concatenate(err), np.concatenate(band_of), np.concatenate(weeks)
    out = {"all": {"n": int(len(err)), "error": F.paired_interval(err, weeks, 0.95)}}
    for lo, hi, label in BANDS:
        m = (band_of >= lo) & (band_of <= hi)
        out[label] = {"n": int(m.sum()), "error": F.paired_interval(err[m], weeks[m], 0.95) if m.sum() else None}
    return out


def verdict(test, holdout, seasons):
    lo, hi = test["log_loss"][1], test["log_loss"][2]
    checks = {
        "test_log_loss_interval_below_zero": hi < 0,
        "holdout_log_loss_better": holdout["log_loss"][0] < 0,
        "test_brier_no_worse": test["brier"][0] <= 0,
        "better_2024_25_and_2025_26": all(seasons.get(s, {"log_loss": 1})["log_loss"] < 0
                                          for s in ("2024/25", "2025/26")),
        "goal_markets_within_guard": all(v <= GUARD for v in test["goal_markets"].values()),
    }
    if all(checks.values()):
        word = "helps"
    elif hi < 0 or lo > 0:
        word = "a real effect, not shown to help"
    else:
        word = "no help shown"
    return word, checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    if args.refresh:
        refresh()
    with gzip.open(INPUTS, "rt", encoding="utf-8") as fh:
        xis = json.load(fh)
    data = F.Data()
    prior, now = changes(data, xis["starters"])
    base = scored(data)
    report = {"inputs": {k: xis[k] for k in ("cut", "database_role", "read_only", "environment", "extracted_at")},
              "xis": len(xis["starters"]), "grid": GRID, "level": LEVEL, "candidates": {}}
    for name, c in (("A_prior_changes", prior), ("B_changes_now", now)):
        covered = base & ~np.isnan(c).any(axis=1)
        rep = {"coverage": {}, "distribution": {}}
        for label, span in (("holdout", HOLDOUT), ("validation", VALIDATION), ("test", TEST)):
            m = base & period(data, span)
            rep["coverage"][label] = {"scored": int(m.sum()), "covered": int((m & covered).sum())}
        vals = c[base & period(data, TEST)].ravel()
        vals = vals[~np.isnan(vals)].astype(int)
        rep["distribution"]["test"] = {str(k): int((vals == k).sum()) for k in range(12)}
        grid = grid_losses(data, covered & period(data, VALIDATION), c)
        value = pick(grid)
        rep["validation_grid"], rep["chosen"] = grid, value
        rep["chosen_at_edge"] = value in (GRID[0], GRID[-1])
        for label, span in (("test", TEST), ("holdout", HOLDOUT)):
            rep[label] = {"covered": evaluate(data, covered & period(data, span), c, value),
                          "all": evaluate(data, base & period(data, span), c, value),
                          "error_by_changes": errors_by_band(data, base & period(data, span), c)}
        word, checks = verdict(rep["test"]["covered"], rep["holdout"]["covered"],
                               rep["test"]["covered"]["by_season"])
        rep["verdict"], rep["checks"] = word, checks
        report["candidates"][name] = rep
        print(name, "chosen", value, "->", word)
    report["generated"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(report, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
