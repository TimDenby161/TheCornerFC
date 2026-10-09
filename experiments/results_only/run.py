"""What does the match model lose if it is fed results alone?

Replays the club ranking (ranking.run, side_ratings) and the pre-match projections
(predictions.predict_match, as backfill_predictions builds them) over every finished fixture,
several ways:

    full          the model as it runs: xG blended into the rank, the split and the form
                  records, predicted line-ups by line, injury lists
    no_xg         goals only (K_FACTOR for every match), line-ups and injuries kept
    no_lineups    xG and injuries kept, no line-ups
    no_injuries   xG and line-ups kept, no injury lists
    results_only  goals only, no line-ups, no injuries: nothing but scores, dates, clubs and
                  competitions goes in
    results_only_k<K>   the same with another K, to see whether goals alone want a different one

Each is scored on the same matches: validation 2023-07-01 to 2024-06-30, test from 2024-07-01.
It is a historical reconstruction (today's code on past matches), not a prospective record.

Nothing is written to the database. The inputs that aren't in the query cache (starting ranks,
predicted line-up ratings, missing strengths) are read once, read-only, and frozen in
.cache/results_only_inputs.pickle; later runs don't touch the database.

    python experiments/results_only/run.py            # replay from the frozen inputs
    python experiments/results_only/run.py --read     # read the inputs first (read-only)
"""
import argparse
import json
import math
import pickle
import random
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc import config; from thecornerfc.models import predictions, ranking  # noqa: E402
from thecornerfc.pipeline.cache import CACHE_DIR  # noqa: E402

INPUTS = CACHE_DIR / "results_only_inputs.pickle"
OUT = Path(__file__).parent / "results.json"
VALIDATION_START = datetime(2023, 7, 1, tzinfo=timezone.utc)
TEST_START = datetime(2024, 7, 1, tzinfo=timezone.utc)
K_GRID = (4, 5, 7, 8, 9, 10)
BIG_FIVE = {39, 140, 135, 78, 61}
EFL = {40, 41, 42}


def read_inputs():
    """The inputs, read once in a read-only transaction and frozen in the cache."""
    from thecornerfc.pipeline import db
    from thecornerfc.pipeline.cache import finished_fixtures
    from thecornerfc.models.injuries import missing_strengths
    conn = db.connect()
    fixtures = finished_fixtures(conn)
    levels = {k: float(v) for k, v in conn.execute(
        "select league_id, starting_rank from leagues where starting_rank is not null")}
    leagues = {k: (n, c, t) for k, n, c, t in conn.execute("select league_id, name, country, type from leagues")}
    lines = {(f, t): list(v) for f, t, *v in conn.execute(
        """select fixture_id, team_id, predicted_gk::float8, predicted_def::float8,
                  predicted_mid::float8, predicted_fwd::float8
           from fixture_team_ratings where predicted_xi_rating is not null""")}
    missing = missing_strengths(conn)
    teams = dict(conn.execute("select team_id, name from teams"))
    conn.rollback()
    conn.close()
    INPUTS.write_bytes(pickle.dumps({"fixtures": fixtures, "levels": levels, "leagues": leagues, "lines": lines,
                                     "missing": missing, "teams": teams,
                                     "read_at": datetime.now(timezone.utc).isoformat()}))
    print(f"read {len(fixtures)} fixtures, {len(lines)} line-up ratings, {len(missing)} missing strengths")


def replay(data, *, xg=True, lineups=True, injuries=True, k=None):
    """{fixture: (p_home, p_draw, p_away, home goals projected, away, p_over25)} for every
    finished fixture, and {team: current rank}. The loop is backfill_predictions's."""
    fixtures = data["fixtures"]
    levels = data["levels"]
    first_league, first_comp = {}, {}
    for _, _, league_id, ltype, home, away, *_ in fixtures:
        for team in (home, away):
            first_comp.setdefault(team, league_id)
            if ltype == "League":
                first_league.setdefault(team, league_id)
    starting = lambda team: levels.get(first_league.get(team, first_comp.get(team)), float(ranking.DEFAULT_STARTING_RANK))
    matches = [ranking.Match(f[0], f[4], f[5], f[6], f[7], *((f[9], f[10]) if xg else (None, None)),
                             ranking.COMPETITION_WEIGHT.get(f[2], 1.0), f[2]) for f in fixtures]
    was = ranking.K_FACTOR
    if k is not None:
        ranking.K_FACTOR = k
    try:
        rows, history = ranking.run(matches, starting)
        sides, _ = ranking.side_ratings(rows)
    finally:
        ranking.K_FACTOR = was

    window = timedelta(days=365)
    home_rec, away_rec, comp = defaultdict(deque), defaultdict(deque), defaultdict(deque)
    recent = {}
    out = {}

    def lt_before(team, before):
        hist = recent.setdefault(team, [before])
        s = ranking.summarise(hist)
        return hist, (s["lt_algo"] if s else before)

    for f, (m, h, a, _, _, change), (pre, _, base) in zip(fixtures, rows, sides):
        fid, kickoff, league_id, _, home, away, hg, ag, _, hx, ax = f
        for dq in (home_rec[home], away_rec[away], comp[league_id]):
            while dq and dq[0][0] < kickoff - window:
                dq.popleft()
        h_hist, h_lt = lt_before(home, h)
        a_hist, a_lt = lt_before(away, a)
        if kickoff >= VALIDATION_START:
            games = comp[league_id]
            lg_home = sum(g[1] for g in games) / len(games) if games else predictions.DEFAULT_HOME_GOALS
            lg_away = sum(g[2] for g in games) / len(games) if games else predictions.DEFAULT_AWAY_GOALS
            pair = None
            if lineups:
                lh, la = data["lines"].get((fid, home)), data["lines"].get((fid, away))
                pair = (lh, la) if lh and la else None
            h_miss = data["missing"].get((fid, home)) if injuries else None
            a_miss = data["missing"].get((fid, away)) if injuries else None
            p = predictions.predict_match(
                predictions.match_rank(h, h_lt), predictions.match_rank(a, a_lt),
                [r[1:] for r in home_rec[home]], [r[1:] for r in away_rec[away]], lg_home, lg_away,
                league_id, h_miss or 0.0, a_miss or 0.0,
                (pre[0], pre[1], pre[2], pre[3], base[0], base[1]), pair)
            out[fid] = (p[3], p[4], p[5], p[1], p[2], p[7])
        for hist, new in ((h_hist, h + change), (a_hist, a - change)):
            hist.append(new)
            del hist[:-101]
        hf, af = predictions._form(hg, ag, hx if xg else None, ax if xg else None)
        home_rec[home].append((kickoff, hf, af))
        away_rec[away].append((kickoff, af, hf))
        comp[league_id].append((kickoff, hg, ag))
    return out, {t: hist[-1] for t, hist in history.items()}, {t: len(hist) - 1 for t, hist in history.items()}


def score(pred, f):
    """One match's scores for one variant."""
    hg, ag = f[6], f[7]
    y = 0 if hg > ag else 1 if hg == ag else 2
    p = pred[:3]
    over = hg + ag > 2.5
    po = min(max(pred[5], 1e-9), 1 - 1e-9)
    return {"loss": -math.log(max(p[y], 1e-15)), "brier": sum((q - (i == y)) ** 2 for i, q in enumerate(p)),
            "hit": int(max(range(3), key=p.__getitem__) == y),
            "over": -math.log(po if over else 1 - po),
            "goals_se": ((pred[3] - hg) ** 2 + (pred[4] - ag) ** 2) / 2,
            "margin_ae": abs((pred[3] - pred[4]) - (hg - ag))}


def segments_of(f, leagues):
    fid, kickoff, league_id, ltype, *_, hx, ax = f
    out = ["all", "has xG" if hx is not None and ax is not None else "no xG"]
    if league_id == 39:
        out.append("Premier League")
    if league_id in EFL:
        out.append("Championship, League One, League Two")
    if league_id in BIG_FIVE:
        out.append("big five leagues")
    if league_id in config.INJURY_MODEL_LEAGUES:
        out.append("ten leagues with injury lists")
    out.append("leagues" if ltype == "League" else "cups")
    out.append("2024/25" if kickoff < datetime(2025, 7, 1, tzinfo=timezone.utc) else "2025/26 on")
    return out


def summary(scored, name, base="full"):
    """Averages for one variant over scored rows [(week, {variant: scores})], with the paired
    difference from base and a weekly-block bootstrap interval for it."""
    n = len(scored)
    if not n:
        return None
    mean = lambda key, v=name: sum(s[v][key] for _, s in scored) / n
    out = {"n": n, "log_loss": mean("loss"), "brier": mean("brier"), "accuracy": mean("hit"),
           "over25_log_loss": mean("over"), "goals_rmse": math.sqrt(mean("goals_se")), "margin_mae": mean("margin_ae")}
    if name != base:
        blocks = defaultdict(lambda: [0.0, 0])
        for week, s in scored:
            b = blocks[week]
            b[0] += s[name]["loss"] - s[base]["loss"]
            b[1] += 1
        out["log_loss_minus_full"] = out["log_loss"] - mean("loss", base)
        vals = list(blocks.values())
        if len(vals) >= 8:
            rng = random.Random(20261006)
            draws = sorted(sum(x for x, _ in smp) / sum(c for _, c in smp)
                           for smp in (rng.choices(vals, k=len(vals)) for _ in range(2000)))
            out["log_loss_minus_full_ci95"] = [draws[50], draws[1949]]
    return out


def spearman(a, b):
    keys = sorted(set(a) & set(b))
    def ranks(d):
        order = sorted(keys, key=lambda t: d[t])
        return {t: i for i, t in enumerate(order)}
    ra, rb = ranks(a), ranks(b)
    n = len(keys)
    return 1 - 6 * sum((ra[t] - rb[t]) ** 2 for t in keys) / (n * (n * n - 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--read", action="store_true", help="read the inputs from the database first (read-only)")
    args = parser.parse_args()
    if args.read or not INPUTS.exists():
        read_inputs()
    data = pickle.loads(INPUTS.read_bytes())
    fixtures = {f[0]: f for f in data["fixtures"]}

    variants = {"full": {}, "no_xg": {"xg": False}, "no_lineups": {"lineups": False},
                "no_injuries": {"injuries": False},
                "results_only": {"xg": False, "lineups": False, "injuries": False}}
    for k in K_GRID:
        variants[f"results_only_k{k}"] = {"xg": False, "lineups": False, "injuries": False, "k": k}
    preds, ranks, played = {}, {}, {}
    for name, kw in variants.items():
        preds[name], ranks[name], played = replay(data, **kw)
        print(f"replayed {name}: {len(preds[name])} projections", flush=True)

    scored = {"validation": [], "test": []}
    seg_rows = defaultdict(list)
    for fid, f in fixtures.items():
        if fid not in preds["full"]:
            continue
        row = (f[1].strftime("%G-%V"), {name: score(preds[name][fid], f) for name in variants})
        part = "test" if f[1] >= TEST_START else "validation"
        scored[part].append(row)
        if part == "test":
            for seg in segments_of(f, data["leagues"]):
                seg_rows[seg].append(row)

    result = {
        "evidence": "historical reconstruction with today's code, not a prospective record",
        "inputs_read_at": data["read_at"], "fixtures_replayed": len(fixtures),
        "validation": {name: summary(scored["validation"], name) for name in variants},
        "test": {name: summary(scored["test"], name) for name in variants},
        "test_segments": {seg: {name: summary(rows, name) for name in ("full", "no_xg", "results_only")}
                          for seg, rows in sorted(seg_rows.items())},
    }
    grid = {name: result["validation"][name]["log_loss"] for name in variants if name.startswith("results_only")}
    result["results_only_k_chosen_on_validation"] = min(grid, key=grid.get)

    # the club ratings themselves: how far do they move?
    active = {t for t, n in played.items() if n >= 30}
    last_seen = {}
    for f in data["fixtures"]:
        last_seen[f[4]] = last_seen[f[5]] = f[1]
    cutoff = max(last_seen.values()) - timedelta(days=120)
    active = {t for t in active if last_seen[t] >= cutoff}
    a = {t: ranks["full"][t] for t in active}
    b = {t: ranks["results_only"][t] for t in active}
    diffs = sorted(abs(a[t] - b[t]) for t in active)
    top = lambda d, n=25: [[data["teams"].get(t, str(t)), round(d[t], 1)] for t in sorted(d, key=d.get, reverse=True)[:n]]
    place = lambda d: {t: i + 1 for i, t in enumerate(sorted(d, key=d.get, reverse=True))}
    pa, pb = place(a), place(b)
    movers = sorted(active, key=lambda t: abs(a[t] - b[t]), reverse=True)[:15]
    result["club_ratings"] = {
        "clubs_compared": len(active), "spearman": spearman(a, b),
        "mean_abs_difference": sum(diffs) / len(diffs), "median_abs_difference": diffs[len(diffs) // 2],
        "p95_abs_difference": diffs[int(.95 * len(diffs))], "max_abs_difference": diffs[-1],
        "top_25_full": top(a), "top_25_results_only": top(b),
        "top_100_places_moved_mean": sum(abs(pa[t] - pb[t]) for t in active if pa[t] <= 100) / 100,
        "biggest_movers": [[data["teams"].get(t, str(t)), round(a[t], 1), round(b[t], 1), pa[t], pb[t]] for t in movers],
    }
    OUT.write_text(json.dumps(result, indent=1, default=str))
    for part in ("validation", "test"):
        print(f"\n{part} (n = {result[part]['full']['n']})")
        for name in variants:
            s = result[part][name]
            ci = s.get("log_loss_minus_full_ci95")
            print(f"  {name:18s} log loss {s['log_loss']:.5f}  brier {s['brier']:.5f}  acc {s['accuracy']:.4f}  "
                  f"over2.5 {s['over25_log_loss']:.5f}  goals rmse {s['goals_rmse']:.4f}"
                  + (f"  vs full {s['log_loss_minus_full']:+.5f} [{ci[0]:+.5f}, {ci[1]:+.5f}]" if ci else ""))
    print("\nsegments (test), log loss full / no_xg / results_only")
    for seg, d in result["test_segments"].items():
        print(f"  {seg:38s} n {d['full']['n']:6d}  {d['full']['log_loss']:.5f}  {d['no_xg']['log_loss']:.5f}  "
              f"{d['results_only']['log_loss']:.5f}  ({d['results_only']['log_loss_minus_full']:+.5f})")
    c = result["club_ratings"]
    print(f"\nclub ratings, {c['clubs_compared']} clubs: spearman {c['spearman']:.4f}, mean move {c['mean_abs_difference']:.1f}, "
          f"95th pct {c['p95_abs_difference']:.1f}, max {c['max_abs_difference']:.1f}")


if __name__ == "__main__":
    main()
