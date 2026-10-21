"""Do the skill-built position weights keep the player ranks where they are? (DESIGN.md)

Runs player_ratings.compute_player_ratings twice on a read-only connection, with the database
write and the line-up capture replaced: once as the file now is, and once with WEIGHTS put back
to the file's as it was at BASE (read from git, checked against its fingerprint). Same code, same
data; only the weights differ. Nothing is written to the database and no API is called; the local
.cache is refreshed as any local run does, so the second run reads nothing new.

Writes results.json next to this file and prints the verdict.

    python experiments/skill_ranks/run.py
"""
import hashlib
import importlib.util
import inspect
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc.pipeline import db; from thecornerfc.evidence import lineup_snapshots; from thecornerfc.models import player_ratings as pr  # noqa: E402
from thecornerfc.models.positions import GROUPS  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results.json"
BASE = "65703faa1"         # the commit the change is made from
BASE_SHA256 = "73f8e45028493eae12ddbc566360795e09a6fa08cb1789f6bb7017e55d3fd898"   # player_ratings.py there
TOP = 10
# the four checks (DESIGN.md), fixed before any result was seen
MIN_SPEARMAN = 0.98        # current rank, base against changed, within each outfield group
MAX_REPEAT_DROP = 0.01     # season-to-season Spearman may fall by at most this
REPEAT_MINUTES = 1500      # minutes in both seasons for the season-to-season pairs
MAX_XI_MOVE = 0.5          # mean absolute change in predicted-XI rating, points
SKILL_MINUTES = 900        # listed players in the skill top 10s


def base_weights():
    """WEIGHTS from player_ratings.py as it was at BASE."""
    source = subprocess.check_output(["git", "show", f"{BASE}:thecornerfc/models/player_ratings.py"], cwd=ROOT)
    if hashlib.sha256(source).hexdigest() != BASE_SHA256:
        raise SystemExit(f"player_ratings.py at {BASE} is not the file this was registered against")
    spec = importlib.util.spec_from_loader("thecornerfc.models.player_ratings_base", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, f"player_ratings.py@{BASE}", "exec"), module.__dict__)
    return module.WEIGHTS


def run(conn, weights=None):
    """One run of the routine, with WEIGHTS replaced if given. Returns what it would have written,
    by the writer's own argument names."""
    got = {}
    write = pr._write
    names = inspect.signature(write)

    def capture(*args, **kwargs):
        got.update(names.bind(*args, **kwargs).arguments)

    saved = pr.WEIGHTS, pr._write, lineup_snapshots.capture_predictions
    pr._write, lineup_snapshots.capture_predictions = capture, lambda *a, **k: None
    if weights is not None:
        pr.WEIGHTS = weights
    try:
        pr.compute_player_ratings(conn)
    finally:
        pr.WEIGHTS, pr._write, lineup_snapshots.capture_predictions = saved
        conn.rollback()
    return got


def ranks(values):
    """Average ranks, 1 upwards, ties sharing."""
    order = sorted(range(len(values)), key=values.__getitem__)
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(pairs):
    if len(pairs) < 3:
        return None
    a, b = ranks([x for x, _ in pairs]), ranks([y for _, y in pairs])
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    return round(cov / (va * vb) ** 0.5, 4) if va and vb else None


def moves(pairs):
    d = sorted(abs(a - b) for a, b in pairs)
    if not d:
        return {"n": 0}
    return {"n": len(d), "mean": round(sum(d) / len(d), 2), "p95": round(d[int(.95 * (len(d) - 1))], 1),
            "largest": round(d[-1], 1), "two_or_more": round(sum(x >= 2 for x in d) / len(d), 4)}


def repeat(season_rows):
    """Season-to-season Spearman of season rank: all pairs, and the players who changed club."""
    by = {(p, y): (r, m, t) for p, y, r, m, t in season_rows}
    pairs, movers = [], []
    for (p, y), (r, m, t) in by.items():
        nxt = by.get((p, y + 1))
        if nxt and m >= REPEAT_MINUTES and nxt[1] >= REPEAT_MINUTES:
            pairs.append((r, nxt[0]))
            if t and nxt[2] and t != nxt[2]:
                movers.append((r, nxt[0]))
    return {"all": spearman(pairs), "all_n": len(pairs), "movers": spearman(movers), "movers_n": len(movers)}


def evaluate(base, new):
    group = lambda label: GROUPS.get(label)
    cur_b = {p: (r, label, m) for p, r, label, m in base["current"]}
    cur_n = {p: (r, label, m) for p, r, label, m in new["current"]}
    keepers = {p for p, (_, label, _) in cur_n.items() if group(label) == "GK"} | {p for p, (_, label, _) in cur_b.items() if group(label) == "GK"}
    seasons = lambda got: {(p, y): r for p, y, r, _, _ in got["season_rows"]}
    sb, sn = seasons(base), seasons(new)
    pos = lambda got: {(p, g): r for p, gs in got["position_ranks"].items() for g, r in gs.items()}
    pb, pn = pos(base), pos(new)
    keepers_same = all(cur_b.get(p, (None,))[0] == cur_n.get(p, (None,))[0] for p in keepers) \
        and all(sb.get(k) == sn.get(k) for k in set(sb) | set(sn) if k[0] in keepers) \
        and all(pb.get(k) == pn.get(k) for k in set(pb) | set(pn) if k[0] in keepers)

    per_group, moved = {}, {}
    for g in pr.OUTFIELD_GROUPS:
        both = [(cur_b[p][0], cur_n[p][0]) for p in cur_n if p in cur_b and group(cur_n[p][1]) == g]
        per_group[g] = spearman(both)
        moved[g] = moves(both)
    rep_b, rep_n = repeat(base["season_rows"]), repeat(new["season_rows"])

    xi = lambda got: {(row[0], row[1]): row[2] for row in got["team_out"] if row[2] is not None}
    xb, xn = xi(base), xi(new)
    common = set(xb) & set(xn)
    xi_move = round(sum(abs(xb[k] - xn[k]) for k in common) / len(common), 3) if common else None
    picks = lambda got: {k: {r[2] for r in rows} for k, rows in _by_team(got["lineups"]).items()}
    lb, ln = picks(base), picks(new)
    xi_changed = sum(lb[k] != ln[k] for k in set(lb) & set(ln))

    checks = {
        "keepers_untouched": keepers_same,
        "ranks_start_where_they_are": all(v is not None and v >= MIN_SPEARMAN for v in per_group.values()),
        "no_less_repeatable": all(rep_n[k] is not None and rep_b[k] is not None and rep_n[k] >= rep_b[k] - MAX_REPEAT_DROP
                                  for k in ("all", "movers")),
        "match_inputs_barely_move": xi_move is not None and xi_move <= MAX_XI_MOVE,
    }
    top = {}
    for g in pr.OUTFIELD_GROUPS:
        best = lambda cur: {p for _, p in sorted(((r, p) for p, (r, label, _) in cur.items() if group(label) == g), reverse=True)[:TOP]}
        top[g] = len(best(cur_b) & best(cur_n))

    skills = {}
    scores = new.get("skills") or {}
    names = {p: label for p, (_, label, _) in cur_n.items()}
    for skill in sorted({s for v in scores.values() for s in v}):
        listed = sorted(((v[skill], p) for p, v in scores.items() if skill in v and cur_n.get(p, (0, "", 0))[2] >= SKILL_MINUTES), reverse=True)
        skills[skill] = [{"player": p, "position": names.get(p), "score": round(s, 1)} for s, p in listed[:TOP]]

    return {
        "checks": checks,
        "passed": all(checks.values()),
        "recipes": getattr(pr, "SKILLS", None),
        "mixes": getattr(pr, "SKILL_MIX", None),
        "current_rank_spearman_by_group": per_group,
        "current_rank_moves": {"all": moves([(cur_b[p][0], cur_n[p][0]) for p in cur_n if p in cur_b]), **moved},
        f"top_{TOP}_kept": top,
        "season_to_season": {"base": rep_b, "changed": rep_n},
        "predicted_xi_rating_mean_abs_change": xi_move,
        "team_matches": len(common),
        "predicted_xis_with_a_different_player": xi_changed,
        "keepers": len(keepers),
        "skill_top": skills,
    }


def _by_team(rows):
    out = defaultdict(list)
    for r in rows:
        out[(r[0], r[1])].append(r)
    return out


def main():
    conn = db.connect()
    conn.read_only = True                # whatever this machine is switched to, this run writes nothing
    said = conn.execute("select site.environment()").fetchone()[0]
    conn.rollback()
    weights = base_weights()
    new = run(conn)
    base = run(conn, weights)
    result = {"database": said, "base": BASE, **evaluate(base, new)}
    OUT.write_text(json.dumps(result, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("database", "checks", "passed")}, indent=1))
    print("PASSED" if result["passed"] else "FAILED")


if __name__ == "__main__":
    main()
