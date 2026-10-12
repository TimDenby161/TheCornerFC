"""Level gaps: are cup ties between sides from different levels predicted too flat? (DESIGN.md)

Takes the stored pre-match projections and, in cup matches only, moves the expected margin two
ways before the production probability step:

    h3   cross-league matches: by BETA x the gap between the two sides' leagues' starting ranks
    h4   one-sided matches (one side has no league in the data): by DELTA rank points against
         that side
    both the two together (they act on different matches)

BETA and DELTA are chosen on validation (2023-07-01 to 2024-06-30) and nowhere else. The test
period (from 2024-07-01) and the holdout (2021-07-01 to 2023-06-30) are scored once with them.
A historical reconstruction, not a prospective record; it reads no odds.

Nothing is written to the database. The inputs are read once, read-only, and frozen in
inputs.json.gz (gitignored); later runs don't touch the database.

    python experiments/level_gaps/run.py             # evaluate from the frozen inputs
    python experiments/level_gaps/run.py --refresh   # read the inputs first (read-only)
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc.models import predictions  # noqa: E402

HERE = Path(__file__).parent
INPUTS = HERE / "inputs.json.gz"
OUT = HERE / "results.json"
_MEASURES = ROOT / "experiments" / "ends_and_draws" / "run.py"
_spec = importlib.util.spec_from_file_location("ends_and_draws_run", _MEASURES)
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

FIXTURES_FROM = "2020-02-01"
HOLDOUT_START, VALIDATION_START, TEST_START, TEST_END = "2021-07-01", "2023-07-01", "2024-07-01", "2026-10-12"
LEAGUE_WINDOW = timedelta(days=400)   # how recent a side's last league match must be
MIN_COMPETITION = 100                 # changed test matches for a competition to be listed
BETA_GRID = tuple(round(0.05 * i, 2) for i in range(-2, 11))
DELTA_GRID = tuple(25 * i for i in range(-2, 9))
N = base.N_STATS
GOALS = len(base.GOAL_MARKETS)
WIDTH = 4 * N + 2 * GOALS + 2          # all base/cand, changed base/cand, goal sums, residual sums


# ---- which matches change, and by how much ---------------------------------------------------

def classify(fixtures, leagues):
    """{fixture_id: (kind, gap, side)} for every fixture, from fixtures in kickoff order.

    kind is 'cross' (both sides have a league, the leagues differ and both have a starting
    rank), 'one_sided' (exactly one side has no league) or None. gap is the home league's
    starting rank minus the away league's for 'cross'. side is +1 when the change favours the
    home side per unit (the away side has no league) and -1 the other way, for 'one_sided'.
    A side's league is the competition of its last finished League-type match within
    LEAGUE_WINDOW before kickoff; nothing later than the kickoff is used."""
    last = {}
    out = {}
    for f in sorted(fixtures, key=lambda f: (f["kickoff"], f["fixture_id"])):
        when = datetime.fromisoformat(f["kickoff"])
        is_league = leagues.get(str(f["league_id"]), {}).get("type") == "League"
        sides = []
        for team in (f["home_team_id"], f["away_team_id"]):
            seen = last.get(team)
            sides.append(seen[1] if seen and when - seen[0] <= LEAGUE_WINDOW else None)
        kind, gap, side = None, 0.0, 0
        if not is_league:
            home, away = sides
            if home is not None and away is not None and home != away:
                levels = [leagues.get(str(x), {}).get("starting_rank") for x in (home, away)]
                if levels[0] is not None and levels[1] is not None:
                    kind, gap = "cross", float(levels[0]) - float(levels[1])
            elif (home is None) != (away is None):
                kind, side = "one_sided", 1 if away is None else -1
        out[f["fixture_id"]] = (kind, gap, side)
        if is_league:
            for team in (f["home_team_id"], f["away_team_id"]):
                last[team] = (when, f["league_id"])
    return out


def shift(row, beta, delta):
    """Goals to add to the expected margin of one match."""
    if row["kind"] == "cross":
        return beta * row["gap"] / 100
    if row["kind"] == "one_sided":
        return row["side"] * delta / 100
    return 0.0


def favoured(row):
    """+1 when a positive BETA or DELTA favours the home side, -1 the away side, 0 neither."""
    if row["kind"] == "cross":
        return (row["gap"] > 0) - (row["gap"] < 0)
    return row["side"] if row["kind"] == "one_sided" else 0


def moved(home_xg, away_xg, by):
    """Projected goals with the margin moved by `by`, the product kept: what predictions.project
    returns for the new margin from the same base goals."""
    if not by:
        return home_xg, away_xg
    d = home_xg - away_xg + by
    home = (d + math.sqrt(d * d + 4 * home_xg * away_xg)) / 2
    return home, home - d


def probabilities(home_xg, away_xg):
    return predictions.outcome_probabilities(home_xg, away_xg)[:3]


# ---- choosing BETA and DELTA on validation ---------------------------------------------------

def grid_loss(rows, kind, values, spec):
    """Mean log loss over the rows of one kind for each grid value."""
    rows = [r for r in rows if r["kind"] == kind]
    out = []
    for v in values:
        total = 0.0
        for row in rows:
            home, away = moved(row["home_xg"], row["away_xg"], shift(row, **spec(v)))
            total += base.log_loss(probabilities(home, away)[base.outcome(row)])
        out.append({"value": v, "log_loss": total / len(rows) if rows else 0.0})
    return out, len(rows)


def pick(grid):
    """Lowest log loss; a tie goes to the value nearest zero."""
    return min(grid, key=lambda g: (round(g["log_loss"], 12), abs(g["value"])))["value"]


# ---- candidate against baseline --------------------------------------------------------------

def compare(rows, beta, delta, kinds):
    """Candidate against baseline on the same rows, over all of them and over the changed ones
    (those whose kind is in `kinds`), with week-bootstrap intervals."""
    by_week = defaultdict(lambda: [0.0] * WIDTH)
    by_season = defaultdict(lambda: [0.0] * (2 * N))
    by_league = defaultdict(lambda: [0.0] * (2 * N))
    for row in rows:
        result = base.outcome(row)
        d0 = row["home_xg"] - row["away_xg"]
        changed = row["kind"] in kinds
        by = shift(row, beta, delta) if changed else 0.0
        h1, a1 = moved(row["home_xg"], row["away_xg"], by)
        p0 = probabilities(row["home_xg"], row["away_xg"])
        p1 = probabilities(h1, a1) if by else p0
        b, c = [0.0] * N, [0.0] * N
        base.add_stats(b, p0, result, d0)
        base.add_stats(c, p1, result, h1 - a1)
        target = by_week[base.week(row)]
        for i in range(N):
            target[i] += b[i]
            target[N + i] += c[i]
        if not changed:
            continue
        for i in range(N):
            target[2 * N + i] += b[i]
            target[3 * N + i] += c[i]
        g0 = base.goal_losses(row, row["home_xg"], row["away_xg"])
        g1 = base.goal_losses(row, h1, a1) if by else g0
        for i in range(GOALS):
            target[4 * N + i] += g0[i]
            target[4 * N + GOALS + i] += g1[i]
        sign = favoured(row)
        actual = row["ft_home"] - row["ft_away"]
        target[4 * N + 2 * GOALS] += sign * (actual - d0)
        target[4 * N + 2 * GOALS + 1] += sign * (actual - (h1 - a1))
        for store, key in ((by_season, base.season(row)), (by_league, row["league_id"])):
            t = store[key]
            for i in range(N):
                t[i] += b[i]
                t[N + i] += c[i]
    weeks = list(by_week.values())

    def summary(total):
        out = {}
        for name, at in (("all", 0), ("changed", 2 * N)):
            if not total[at]:
                continue
            m0, m1 = base.measures(total[at:at + N]), base.measures(total[at + N:at + 2 * N])
            out[name] = {k: m1[k] - m0[k] for k in base.MEASURES}
            if name == "changed":
                out["ends_gap_fall"] = {"changed": (1 - m1["ends_gap"] / m0["ends_gap"]) if m0["ends_gap"] else 0.0}
                n = total[at]
                out["goal_markets"] = {g: (total[4 * N + GOALS + i] - total[4 * N + i]) / n
                                       for i, g in enumerate(base.GOAL_MARKETS)}
                out["margin_error"] = {"baseline": total[4 * N + 2 * GOALS] / n,
                                       "candidate": total[4 * N + 2 * GOALS + 1] / n}
        return out

    total = [sum(w[i] for w in weeks) for i in range(WIDTH)]
    point = summary(total)
    rnd = random.Random(base.SEED)
    draws = defaultdict(list)
    for _ in range(base.DRAWS):
        sample = [0.0] * WIDTH
        for _ in range(len(weeks)):
            w = weeks[rnd.randrange(len(weeks))]
            for i in range(WIDTH):
                sample[i] += w[i]
        for group, values in summary(sample).items():
            for k, v in values.items():
                draws[(group, k)].append(v)
    intervals = {group: {k: base.interval(draws[(group, k)]) for k in values} for group, values in point.items()}

    def split(store, least=1):
        out = {}
        for key, vec in store.items():
            a, b = base.measures(vec[:N]), base.measures(vec[N:])
            if a["n"] >= least:
                out[str(key)] = {"n": a["n"], "baseline_log_loss": a["log_loss"],
                                 "log_loss": b["log_loss"] - a["log_loss"], "brier": b["brier"] - a["brier"]}
        return out

    competitions = split(by_league, MIN_COMPETITION)
    result = {"weeks": len(weeks), "difference": point, "intervals": intervals,
              "by_season": dict(sorted(split(by_season).items())), "by_competition": competitions,
              "competitions": {"n": len(competitions),
                               "no_worse": sum(v["log_loss"] <= 0 for v in competitions.values())}}
    for name, at in (("all", 0), ("changed", 2 * N)):
        if total[at]:
            result[name] = {"baseline": base.measures(total[at:at + N]),
                            "candidate": base.measures(total[at + N:at + 2 * N])}
    if total[2 * N]:
        result["calibration"] = {"baseline": base.calibration_table(total[2 * N:3 * N]),
                                 "candidate": base.calibration_table(total[3 * N:4 * N])}
    return result


# ---- acceptance ------------------------------------------------------------------------------

def verdict(test, holdout):
    """Bar A and Bar B of DESIGN.md: each condition, then the label."""
    d, ci = test["difference"], test["intervals"]
    everything, changed = d.get("all", {}), d.get("changed")
    seasons = [test["by_season"][s]["log_loss"] for s in ("2024/25", "2025/26") if s in test["by_season"]]
    both_seasons = len(seasons) == 2 and all(s < 0 for s in seasons)
    bar_a = {"log_loss_better_by_0.002_over_all_matches": everything.get("log_loss", 0) <= -0.002,
             "interval_excludes_zero": bool(everything) and ci["all"]["log_loss"][1] < 0,
             "brier_agrees": everything.get("brier", 0) < 0, "both_seasons_better": both_seasons}
    if not changed:
        return {"bar_a": bar_a, "bar_b": {}, "label": "meets neither"}
    held = holdout["difference"].get("changed")
    bar_b = {
        "1_log_loss_better_interval_excludes_zero": changed["log_loss"] < 0 and ci["changed"]["log_loss"][1] < 0,
        "2_brier_no_worse": changed["brier"] <= 0,
        "3_ends_gap_falls_30_percent_interval_excludes_zero":
            d["ends_gap_fall"]["changed"] >= 0.30 and ci["ends_gap_fall"]["changed"][0] > 0,
        "4_calibration_error_no_worse": changed["calibration_error"] <= 0,
        "5_better_in_both_test_seasons": both_seasons,
        "6_holdout_better_interval_excludes_zero":
            bool(held) and held["log_loss"] < 0 and holdout["intervals"]["changed"]["log_loss"][1] < 0,
        "7_no_goal_market_worse_by_0.0005": all(v <= 0.0005 for v in d["goal_markets"].values()),
        "8_60_percent_of_competitions_no_worse": test["competitions"]["n"] > 0
        and test["competitions"]["no_worse"] / test["competitions"]["n"] >= 0.60,
    }
    a, b = all(bar_a.values()), all(bar_b.values())
    return {"bar_a": bar_a, "bar_b": bar_b, "label": "meets A" if a else "meets B only" if b else "meets neither"}


# ---- inputs ----------------------------------------------------------------------------------

COLUMNS = ("fixture_id", "kickoff", "league_id", "home_team_id", "away_team_id", "status_short",
           "ft_home", "ft_away", "home_xg", "away_xg")


def read_inputs():
    """Every finished fixture and its stored projection, read once in a read-only transaction."""
    from thecornerfc.pipeline import db
    with db.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        rows = [[r[0], r[1].astimezone(timezone.utc).isoformat(), *r[2:]] for r in conn.execute(
            """select f.fixture_id, f.kickoff, f.league_id, f.home_team_id, f.away_team_id, f.status_short,
                      f.ft_home, f.ft_away, p.home_xg, p.away_xg
               from fixtures f left join fixture_predictions p using (fixture_id)
               where f.status_short in ('FT', 'AET', 'PEN') and f.kickoff >= %s and f.kickoff < %s""",
            [FIXTURES_FROM, TEST_END])]
        leagues = {str(k): {"name": n, "country": c, "type": t, "starting_rank": None if s is None else float(s)}
                   for k, n, c, t, s in conn.execute(
                       "select league_id, name, country, type, starting_rank from leagues")}
        role = conn.execute("select current_user").fetchone()[0]
    doc = {"extracted_at": datetime.now(timezone.utc).isoformat(), "database_role": role,
           "columns": COLUMNS, "rows": rows, "leagues": leagues}
    with gzip.open(INPUTS, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return doc


def load_inputs():
    with gzip.open(INPUTS, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def scored_rows(doc):
    """The matches that are scored, each with its kind, gap and side."""
    fixtures = [dict(zip(doc["columns"], r)) for r in doc["rows"]]
    kinds = classify(fixtures, doc["leagues"])
    rows = []
    for f in fixtures:
        if f["status_short"] != "FT" or f["ft_home"] is None or f["ft_away"] is None or f["home_xg"] is None \
                or f["away_xg"] is None:
            continue
        kind, gap, side = kinds[f["fixture_id"]]
        rows.append({**f, "kind": kind, "gap": gap, "side": side})
    return rows


# ---- the run ---------------------------------------------------------------------------------

def evaluate(doc):
    split = base.periods(scored_rows(doc))
    validation = split["validation"]
    beta_grid, n_cross = grid_loss(validation, "cross", BETA_GRID, lambda v: {"beta": v, "delta": 0})
    delta_grid, n_one = grid_loss(validation, "one_sided", DELTA_GRID, lambda v: {"beta": 0, "delta": v})
    beta, delta = pick(beta_grid), pick(delta_grid)
    candidates = {"h3": (beta, 0, ("cross",)), "h4": (0, delta, ("one_sided",)),
                  "both": (beta, delta, ("cross", "one_sided"))}
    out = {}
    for name, (b, d, kinds) in candidates.items():
        entry = {"setting": {"beta": b, "delta": d}, "changes": list(kinds)}
        for period in ("validation", "test", "holdout"):
            entry[period] = compare(split[period], b, d, kinds)
        entry["verdict"] = verdict(entry["test"], entry["holdout"])
        out[name] = entry
    counts = {period: dict(sorted(_count(str(r["kind"]) for r in rows).items())) for period, rows in split.items()}
    return {
        "design": {"holdout": [HOLDOUT_START, VALIDATION_START], "validation": [VALIDATION_START, TEST_START],
                   "test": [TEST_START, TEST_END], "seed": base.SEED, "draws": base.DRAWS,
                   "league_window_days": LEAGUE_WINDOW.days, "beta_grid": BETA_GRID, "delta_grid": DELTA_GRID},
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "measures_sha256": hashlib.sha256(_MEASURES.read_bytes()).hexdigest(),
        "inputs": {"extracted_at": doc["extracted_at"], "database_role": doc.get("database_role"),
                   "fixtures": len(doc["rows"]), "scored": {k: len(v) for k, v in split.items()}, "kinds": counts},
        "validation_grids": {"beta": beta_grid, "delta": delta_grid,
                             "matches": {"cross": n_cross, "one_sided": n_one},
                             "at_edge": {"beta": beta in (BETA_GRID[0], BETA_GRID[-1]),
                                         "delta": delta in (DELTA_GRID[0], DELTA_GRID[-1])}},
        "candidates": out,
        "competition_names": {k: [v["name"], v["country"], v["type"]] for k, v in doc["leagues"].items()},
    }


def _count(values):
    out = defaultdict(int)
    for v in values:
        out[v] += 1
    return out


def show(report):
    print("scored", report["inputs"]["scored"], "| kinds", report["inputs"]["kinds"])
    grids = report["validation_grids"]
    print("validation matches", grids["matches"], "| at edge", grids["at_edge"])
    for name in ("beta", "delta"):
        print(" ", name, " ".join(f"{g['value']}:{g['log_loss']:.5f}" for g in grids[name]))
    for name, entry in report["candidates"].items():
        print(f"\n== {name} {entry['setting']}")
        for period in ("validation", "test", "holdout"):
            r = entry[period]
            for scope in ("changed", "all"):
                if scope not in r:
                    continue
                d, ci = r["difference"][scope], r["intervals"][scope]
                print(f"  {period:10s} {scope:7s} n={r[scope]['baseline']['n']:6d} log loss {r[scope]['baseline']['log_loss']:.5f} -> "
                      f"{r[scope]['candidate']['log_loss']:.5f} ({d['log_loss']:+.5f}, {ci['log_loss'][0]:+.5f} to {ci['log_loss'][1]:+.5f}) "
                      f"| Brier {d['brier']:+.5f} | ends gap {r[scope]['baseline']['ends_gap']:.4f} -> {r[scope]['candidate']['ends_gap']:.4f}")
        print("  verdict:", entry["verdict"]["label"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--refresh", action="store_true", help="read the inputs from the database first (read-only)")
    args = parser.parse_args()
    doc = read_inputs() if args.refresh else load_inputs()
    report = evaluate(doc)
    OUT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    show(report)


if __name__ == "__main__":
    main()
