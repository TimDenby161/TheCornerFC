"""Ends and draws: do two calibration changes improve the result probabilities? (DESIGN.md)

Takes the stored pre-match projections (fixture_predictions.home_xg / away_xg) and scores the
result probabilities several ways on the same matches:

    baseline   predictions.outcome_probabilities as it runs
    h1         the ends stretched: one of three one-number forms (quadratic, linear, power),
               the form and its number chosen on validation
    h2         the draw boost refitted: DRAW_INFLATION and DRAW_FADE_MARGIN chosen on validation
    joint      h1's form and h2 searched together on validation
    stacked    h1's and h2's separately chosen settings applied at once

Every setting is chosen on validation (2023-07-01 to 2024-06-30) and nowhere else. The test
period (from 2024-07-01) and the holdout (2021-07-01 to 2023-06-30) are scored once with them.
It is a historical reconstruction, not a prospective record, and reads no odds.

Nothing is written to the database. The inputs are read once, read-only, and frozen in
inputs.json.gz (gitignored); later runs don't touch the database.

    python experiments/ends_and_draws/run.py             # evaluate from the frozen inputs
    python experiments/ends_and_draws/run.py --refresh   # read the inputs first (read-only)
"""
import argparse
import gzip
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc.models import predictions  # noqa: E402

HERE = Path(__file__).parent
INPUTS = HERE / "inputs.json.gz"
OUT = HERE / "results.json"

HOLDOUT_START, VALIDATION_START, TEST_START, TEST_END = "2021-07-01", "2023-07-01", "2024-07-01", "2026-10-12"
SEED, DRAWS = 20261012, 2000
MIN_COMPETITION = 300                 # test matches for a competition to be listed
REPRODUCTION_TOLERANCE = 1e-9

QUADRATIC_GRID = tuple(round(0.02 * i, 2) for i in range(-1, 11))      # c in d * (1 + c|d|)
LINEAR_GRID = tuple(round(1 + 0.02 * i, 2) for i in range(-2, 11))     # k in k * d
POWER_GRID = tuple(round(1 + 0.02 * i, 2) for i in range(-2, 11))      # a in p ** a
FORMS = {"quadratic": (QUADRATIC_GRID, 0.0), "linear": (LINEAR_GRID, 1.0), "power": (POWER_GRID, 1.0)}
INFLATION_GRID = tuple(round(1 + 0.01 * i, 2) for i in range(13))
FADE_GRID = (0.75, 1.0, 1.25, 1.5, 2.0, 3.0)

BASELINE = {"form": None, "value": None,
            "inflation": predictions.DRAW_INFLATION, "fade": predictions.DRAW_FADE_MARGIN}
MARGIN_BANDS = (0.25, 0.5, 1.0, 1.5)  # edges of the five expected-margin bands for the draw gap
ENDS_BANDS = (0, 1, 7, 8, 9)          # tenths: under 20% and from 70% up
GOAL_MARKETS = ("over15", "over25", "over35", "over45", "btts")
N_STATS = 4 + 90 + 15                 # n, log loss, Brier, right; 3 x 10 x (n, p, y); 5 x (n, p, y)


# ---- the model step under test ---------------------------------------------------------------

def raw_outcomes(home_xg, away_xg):
    """Home, draw and away from two independent Poisson rates, before the draw boost: the same
    sums as predictions.outcome_probabilities, without building the whole grid."""
    ph, pa = predictions._pmf(home_xg), predictions._pmf(away_xg)
    total = sum(ph) * sum(pa)
    below, home, draw = 0.0, 0.0, 0.0
    for i in range(len(ph)):
        home += ph[i] * below
        draw += ph[i] * pa[i]
        below += pa[i]
    home, draw = home / total, draw / total
    return home, draw, 1 - home - draw


def finish(raw, exp_diff, inflation, fade):
    """The draw boost, as predictions.outcome_probabilities applies it, with its two numbers
    as arguments."""
    home, draw, away = raw
    boost = 1 + (inflation - 1) * max(0.0, 1 - abs(exp_diff) / fade)
    draw_adj = min(draw * boost, 0.9)
    scale = (1 - draw_adj) / (home + away)
    return home * scale, draw_adj, away * scale


def restretch(home_xg, away_xg, form, value):
    """Projected goals with the expected margin stretched, the product of the two kept: what
    predictions.project returns for the new margin from the same base goals."""
    d = home_xg - away_xg
    if form == "quadratic":
        d2 = d * (1 + value * abs(d))
    elif form == "linear":
        d2 = d * value
    else:
        return home_xg, away_xg
    if d2 == d:
        return home_xg, away_xg
    home = (d2 + math.sqrt(d2 * d2 + 4 * home_xg * away_xg)) / 2
    return home, home - d2


def power(probabilities, a):
    scaled = [p ** a for p in probabilities]
    total = sum(scaled)
    return tuple(p / total for p in scaled)


class Scorer:
    """Result probabilities for a row under a setting, with the Poisson sums kept between
    settings that share projected goals."""

    def __init__(self):
        self._raw = {}

    def goals(self, row, spec):
        return restretch(row["home_xg"], row["away_xg"], spec["form"], spec["value"])

    def probabilities(self, row, spec):
        margin = spec["form"] in ("quadratic", "linear")
        key = (row["fixture_id"], spec["form"], spec["value"]) if margin else (row["fixture_id"], None, None)
        hit = self._raw.get(key)
        if hit is None:
            home_xg, away_xg = self.goals(row, spec)
            hit = self._raw[key] = (raw_outcomes(home_xg, away_xg), home_xg - away_xg)
        out = finish(hit[0], hit[1], spec["inflation"], spec["fade"])
        return power(out, spec["value"]) if spec["form"] == "power" else out

    def forget(self):
        self._raw.clear()


# ---- measures --------------------------------------------------------------------------------

def outcome(row):
    return 0 if row["ft_home"] > row["ft_away"] else 1 if row["ft_home"] == row["ft_away"] else 2


def log_loss(p):
    return -math.log(min(max(p, 1e-15), 1.0))


def week(row):
    return date.fromisoformat(row["kickoff"][:10]).isocalendar()[:2]


def season(row):
    year, month = int(row["kickoff"][:4]), int(row["kickoff"][5:7])
    start = year if month >= 7 else year - 1
    return f"{start}/{str(start + 1)[2:]}"


def margin_band(exp_diff):
    return sum(abs(exp_diff) >= edge for edge in MARGIN_BANDS)


def add_stats(stats, probabilities, result, exp_diff):
    """Add one match to a stats vector (see N_STATS)."""
    stats[0] += 1
    stats[1] += log_loss(probabilities[result])
    stats[2] += sum((p - (k == result)) ** 2 for k, p in enumerate(probabilities))
    stats[3] += max(range(3), key=lambda k: (probabilities[k], -k)) == result
    for k, p in enumerate(probabilities):
        at = 4 + 3 * (10 * k + min(int(p * 10), 9))
        stats[at] += 1
        stats[at + 1] += p
        stats[at + 2] += k == result
    at = 94 + 3 * margin_band(exp_diff)
    stats[at] += 1
    stats[at + 1] += probabilities[1]
    stats[at + 2] += result == 1


def _gap(stats, cells):
    """Match-weighted |mean predicted - observed| over (n, p, y) cells starting at each index."""
    n = sum(stats[c] for c in cells)
    return sum(abs(stats[c + 1] - stats[c + 2]) for c in cells) / n if n else 0.0


def measures(stats):
    n = stats[0]
    classes = [[4 + 3 * (10 * k + b) for b in range(10)] for k in range(3)]
    return {
        "n": int(n), "log_loss": stats[1] / n, "brier": stats[2] / n, "accuracy": stats[3] / n,
        "calibration_error": sum(_gap(stats, cells) for cells in classes) / 3,
        "ends_gap": _gap(stats, [4 + 3 * (10 * k + b) for k in (0, 2) for b in ENDS_BANDS]),
        "draw_gap": _gap(stats, [94 + 3 * b for b in range(5)]),
    }


MEASURES = ("log_loss", "brier", "accuracy", "calibration_error", "ends_gap", "draw_gap")


def calibration_table(stats):
    """Per outcome, the ten bands as [band, n, mean predicted, observed]; and the draw rate by
    expected-margin band."""
    out = {}
    for k, name in enumerate(("home", "draw", "away")):
        rows = []
        for b in range(10):
            at = 4 + 3 * (10 * k + b)
            if stats[at]:
                rows.append([b / 10, int(stats[at]), stats[at + 1] / stats[at], stats[at + 2] / stats[at]])
        out[name] = rows
    labels = ("under 0.25", "0.25 to 0.5", "0.5 to 1", "1 to 1.5", "1.5 and over")
    out["draw_by_margin"] = [[labels[b], int(stats[94 + 3 * b]), stats[95 + 3 * b] / stats[94 + 3 * b],
                              stats[96 + 3 * b] / stats[94 + 3 * b]] for b in range(5) if stats[94 + 3 * b]]
    return out


def interval(values):
    values = sorted(values)
    return [values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]]


def paired(rows, scorer, base_spec, spec):
    """Candidate against baseline on the same rows: measures for each, the differences with
    week-bootstrap intervals, the fall in each named gap, the goal markets, and the by-season
    and by-competition changes."""
    by_week = defaultdict(lambda: [0.0] * (2 * N_STATS + 2 * len(GOAL_MARKETS)))
    by_season = defaultdict(lambda: [0.0] * (2 * N_STATS))
    by_league = defaultdict(lambda: [0.0] * (2 * N_STATS))
    moves_goals = spec["form"] in ("quadratic", "linear")
    for row in rows:
        result = outcome(row)
        d0 = row["home_xg"] - row["away_xg"]
        p0 = scorer.probabilities(row, base_spec)
        p1 = scorer.probabilities(row, spec)
        h1, a1 = scorer.goals(row, spec)
        base, cand = [0.0] * N_STATS, [0.0] * N_STATS
        add_stats(base, p0, result, d0)
        add_stats(cand, p1, result, h1 - a1)
        both = base + cand
        for store, key in ((by_season, season(row)), (by_league, row["league_id"])):
            target = store[key]
            for i, v in enumerate(both):
                target[i] += v
        target = by_week[week(row)]
        for i, v in enumerate(both):
            target[i] += v
        g0 = goal_losses(row, row["home_xg"], row["away_xg"])
        g1 = goal_losses(row, h1, a1) if moves_goals else g0
        for i in range(len(GOAL_MARKETS)):
            target[2 * N_STATS + i] += g0[i]
            target[2 * N_STATS + len(GOAL_MARKETS) + i] += g1[i]
    weeks = list(by_week.values())
    width = len(weeks[0])

    def summary(total):
        m0, m1 = measures(total[:N_STATS]), measures(total[N_STATS:2 * N_STATS])
        out = {"difference": {k: m1[k] - m0[k] for k in MEASURES},
               "gap_fall": {k: (1 - m1[k] / m0[k]) if m0[k] else 0.0 for k in ("ends_gap", "draw_gap")},
               "goal_markets": {name: (total[2 * N_STATS + len(GOAL_MARKETS) + i] - total[2 * N_STATS + i]) / total[0]
                                for i, name in enumerate(GOAL_MARKETS)}}
        return m0, m1, out

    total = [sum(w[i] for w in weeks) for i in range(width)]
    m0, m1, point = summary(total)
    rnd = random.Random(SEED)
    draws = defaultdict(list)
    for _ in range(DRAWS):
        sample = [0.0] * width
        for _ in range(len(weeks)):
            w = weeks[rnd.randrange(len(weeks))]
            for i in range(width):
                sample[i] += w[i]
        _, _, s = summary(sample)
        for group, values in s.items():
            for k, v in values.items():
                draws[(group, k)].append(v)
    intervals = {group: {k: interval(draws[(group, k)]) for k in values} for group, values in point.items()}

    def split(store):
        out = {}
        for key, vec in store.items():
            a, b = measures(vec[:N_STATS]), measures(vec[N_STATS:])
            out[key] = {"n": a["n"], "baseline_log_loss": a["log_loss"], "log_loss": b["log_loss"] - a["log_loss"],
                        "brier": b["brier"] - a["brier"], "baseline_ends_gap": a["ends_gap"],
                        "ends_gap": b["ends_gap"], "baseline_draw_gap": a["draw_gap"], "draw_gap": b["draw_gap"],
                        "baseline_draw_rate": sum(vec[95 + 3 * i] for i in range(5)) / a["n"],
                        "draw_rate": sum(vec[N_STATS + 95 + 3 * i] for i in range(5)) / a["n"],
                        "observed_draw_rate": sum(vec[96 + 3 * i] for i in range(5)) / a["n"]}
        return out

    leagues = {str(k): v for k, v in split(by_league).items() if v["n"] >= MIN_COMPETITION}
    return {"weeks": len(weeks), "baseline": m0, "candidate": m1, **point, "intervals": intervals,
            "calibration": {"baseline": calibration_table(total[:N_STATS]),
                            "candidate": calibration_table(total[N_STATS:2 * N_STATS])},
            "by_season": dict(sorted(split(by_season).items())),
            "by_competition": leagues,
            "competitions": {"n": len(leagues),
                             "no_worse": sum(v["log_loss"] <= 0 for v in leagues.values())}}


def goal_losses(row, home_xg, away_xg):
    """Log loss on each goal market for one match, from production's calibrated goal lines."""
    lines = predictions.goal_lines(home_xg, away_xg)
    btts = predictions.goal_markets(home_xg, away_xg)[1]
    total = row["ft_home"] + row["ft_away"]
    chances = [(lines[1.5], total > 1.5), (lines[2.5], total > 2.5), (lines[3.5], total > 3.5),
               (lines[4.5], total > 4.5), (btts, row["ft_home"] > 0 and row["ft_away"] > 0)]
    return [log_loss(p if won else 1 - p) for p, won in chances]


# ---- choosing settings on validation ---------------------------------------------------------

def mean_log_loss(rows, scorer, spec):
    return sum(log_loss(scorer.probabilities(row, spec)[outcome(row)]) for row in rows) / len(rows)


def _distance(spec):
    """How far a setting is from production, for ties."""
    form = spec["form"]
    step = 0.0 if form is None else abs(spec["value"] - FORMS[form][1])
    return step + abs(spec["inflation"] - BASELINE["inflation"]) + abs(spec["fade"] - BASELINE["fade"])


def choose(rows, scorer, specs):
    """The setting with the lowest validation log loss (ties: nearest production), and the grid."""
    grid = [(mean_log_loss(rows, scorer, spec), spec) for spec in specs]
    best = min(grid, key=lambda g: (round(g[0], 12), _distance(g[1])))
    return best[1], [{**spec, "log_loss": loss} for loss, spec in grid]


def h1_specs(form):
    return [{**BASELINE, "form": form, "value": v} for v in FORMS[form][0]]


def h2_specs():
    return [{**BASELINE, "inflation": i, "fade": f} for i in INFLATION_GRID for f in FADE_GRID]


def joint_specs(form):
    return [{"form": form, "value": v, "inflation": i, "fade": f}
            for v in FORMS[form][0] for i in INFLATION_GRID for f in FADE_GRID]


# ---- acceptance ------------------------------------------------------------------------------

def verdict(name, test, holdout):
    """Bar A and Bar B of DESIGN.md for one candidate: each condition, then the label."""
    d, ci = test["difference"], test["intervals"]["difference"]
    seasons = [test["by_season"][s]["log_loss"] for s in ("2024/25", "2025/26") if s in test["by_season"]]
    better = d["log_loss"] < 0 and ci["log_loss"][1] < 0
    bar_a = {"log_loss_better_by_0.002": d["log_loss"] <= -0.002, "interval_excludes_zero": better,
             "brier_agrees": d["brier"] < 0, "both_seasons_better": len(seasons) == 2 and all(s < 0 for s in seasons)}
    gaps = {"h1": ("ends_gap",), "h2": ("draw_gap",)}.get(name, ("ends_gap", "draw_gap"))
    bar_b = {
        "1_log_loss_better_interval_excludes_zero": better,
        "2_brier_no_worse": d["brier"] <= 0,
        "3_named_gap_falls_30_percent_interval_excludes_zero": all(
            test["gap_fall"][g] >= 0.30 and test["intervals"]["gap_fall"][g][0] > 0 for g in gaps),
        "4_calibration_error_no_worse": d["calibration_error"] <= 0,
        "5_same_direction_both_seasons_and_holdout": len(seasons) == 2 and all(s < 0 for s in seasons)
        and holdout["difference"]["log_loss"] < 0,
        "6_no_goal_market_worse_by_0.0005": all(v <= 0.0005 for v in test["goal_markets"].values()),
        "7_60_percent_of_competitions_no_worse": test["competitions"]["n"] > 0
        and test["competitions"]["no_worse"] / test["competitions"]["n"] >= 0.60,
    }
    a, b = all(bar_a.values()), all(bar_b.values())
    return {"bar_a": bar_a, "bar_b": bar_b, "named_gaps": list(gaps),
            "label": "meets A" if a else "meets B only" if b else "meets neither"}


# ---- inputs ----------------------------------------------------------------------------------

COLUMNS = ("fixture_id", "kickoff", "league_id", "home_xg", "away_xg", "p_home", "p_draw", "p_away",
           "source", "ft_home", "ft_away")


def read_inputs():
    """The stored projections and results, read once in a read-only transaction and frozen."""
    from thecornerfc.pipeline import db
    with db.connect() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        rows = [[r[0], r[1].astimezone(timezone.utc).isoformat(), *r[2:]] for r in conn.execute(
            """select p.fixture_id, f.kickoff, f.league_id, p.home_xg, p.away_xg, p.p_home, p.p_draw,
                      p.p_away, p.source, f.ft_home, f.ft_away
               from fixture_predictions p join fixtures f using (fixture_id)
               where f.status_short = 'FT' and f.ft_home is not null and f.ft_away is not null
                 and p.home_xg is not null and p.away_xg is not null and p.p_home is not null
                 and f.kickoff >= %s and f.kickoff < %s""", [HOLDOUT_START, TEST_END])]
        leagues = {str(k): [n, c, t] for k, n, c, t in conn.execute(
            "select league_id, name, country, type from leagues")}
        role = conn.execute("select current_user").fetchone()[0]
    doc = {"extracted_at": datetime.now(timezone.utc).isoformat(), "database_role": role,
           "columns": COLUMNS, "rows": rows, "leagues": leagues}
    with gzip.open(INPUTS, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return doc


def load_inputs():
    with gzip.open(INPUTS, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def periods(rows):
    out = {"holdout": [], "validation": [], "test": []}
    for row in rows:
        day = row["kickoff"][:10]
        if HOLDOUT_START <= day < VALIDATION_START:
            out["holdout"].append(row)
        elif VALIDATION_START <= day < TEST_START:
            out["validation"].append(row)
        elif TEST_START <= day < TEST_END:
            out["test"].append(row)
    return out


def reproduction(rows):
    """The harness's probability step against production's, and against what was stored."""
    worst, stored_close = 0.0, 0
    for row in rows:
        mine = finish(raw_outcomes(row["home_xg"], row["away_xg"]), row["home_xg"] - row["away_xg"],
                      BASELINE["inflation"], BASELINE["fade"])
        theirs = predictions.outcome_probabilities(row["home_xg"], row["away_xg"])[:3]
        worst = max(worst, max(abs(a - b) for a, b in zip(mine, theirs)))
        stored_close += max(abs(a - b) for a, b in zip(theirs, (row["p_home"], row["p_draw"], row["p_away"]))) < 1e-6
    return {"rows": len(rows), "largest_difference_from_production_function": worst,
            "stored_probabilities_reproduced": stored_close}


# ---- the run ---------------------------------------------------------------------------------

def evaluate(doc):
    rows = [dict(zip(doc["columns"], r)) for r in doc["rows"]]
    split = periods(rows)
    check = reproduction(rows)
    if check["largest_difference_from_production_function"] > REPRODUCTION_TOLERANCE:
        raise SystemExit(f"the harness does not reproduce production: {check}")
    scorer, validation = Scorer(), split["validation"]

    chosen, grids = {}, {}
    forms = {}
    for form in FORMS:
        forms[form], grids[f"h1_{form}"] = choose(validation, scorer, h1_specs(form))
        scorer.forget()
    best_form = min(forms, key=lambda f: (round(mean_log_loss(validation, scorer, forms[f]), 12), _distance(forms[f])))
    scorer.forget()
    chosen["h1"] = forms[best_form]
    chosen["h2"], grids["h2"] = choose(validation, scorer, h2_specs())
    chosen["joint"], joint_grid = choose(validation, scorer, joint_specs(best_form))
    scorer.forget()
    grids["joint_best_ten"] = sorted(joint_grid, key=lambda g: g["log_loss"])[:10]
    chosen["stacked"] = {**chosen["h1"], "inflation": chosen["h2"]["inflation"], "fade": chosen["h2"]["fade"]}
    also = {f"h1_{form}": spec for form, spec in forms.items() if form != best_form}

    results = {"validation_baseline_log_loss": mean_log_loss(validation, scorer, BASELINE)}
    scorer.forget()
    out = {}
    for name, spec in {**chosen, **also}.items():
        entry = {"setting": spec, "registered": name in chosen}
        for period in ("validation", "test", "holdout"):
            entry[period] = paired(split[period], scorer, BASELINE, spec)
            scorer.forget()
        if name in chosen:
            entry["verdict"] = verdict(name, entry["test"], entry["holdout"])
        out[name] = entry
    return {
        "design": {"holdout": [HOLDOUT_START, VALIDATION_START], "validation": [VALIDATION_START, TEST_START],
                   "test": [TEST_START, TEST_END], "seed": SEED, "draws": DRAWS, "baseline": BASELINE,
                   "grids": {"quadratic": QUADRATIC_GRID, "linear": LINEAR_GRID, "power": POWER_GRID,
                             "inflation": INFLATION_GRID, "fade": FADE_GRID}},
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "inputs": {"extracted_at": doc["extracted_at"], "database_role": doc.get("database_role"),
                   "rows": {k: len(v) for k, v in split.items()},
                   "sources": {k: dict(sorted(_count(r["source"] for r in v).items())) for k, v in split.items()}},
        "reproduction": check, "h1_form_chosen": best_form, "validation_grids": grids, **results,
        "candidates": out,
        "competition_names": {k: v for k, v in doc["leagues"].items()},
    }


def _count(values):
    out = defaultdict(int)
    for v in values:
        out[v] += 1
    return out


def show(report):
    print("rows", report["inputs"]["rows"], "| reproduction", report["reproduction"])
    print("H1 form chosen on validation:", report["h1_form_chosen"])
    for name, entry in report["candidates"].items():
        print(f"\n== {name} {'(registered)' if entry['registered'] else '(not chosen, for the record)'} {entry['setting']}")
        for period in ("validation", "test", "holdout"):
            r = entry[period]
            d, ci = r["difference"], r["intervals"]["difference"]
            print(f"  {period:10s} n={r['baseline']['n']:6d} log loss {r['baseline']['log_loss']:.5f} -> {r['candidate']['log_loss']:.5f} "
                  f"({d['log_loss']:+.5f}, {ci['log_loss'][0]:+.5f} to {ci['log_loss'][1]:+.5f}) | Brier {d['brier']:+.5f} "
                  f"({ci['brier'][0]:+.5f} to {ci['brier'][1]:+.5f}) | ends gap {r['baseline']['ends_gap']:.4f} -> {r['candidate']['ends_gap']:.4f} "
                  f"| draw gap {r['baseline']['draw_gap']:.4f} -> {r['candidate']['draw_gap']:.4f} | calibration {r['baseline']['calibration_error']:.4f} -> {r['candidate']['calibration_error']:.4f}")
        if "verdict" in entry:
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
