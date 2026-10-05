"""Record of the October 2026 tuning. It ran against player_ratings.py as it was before the result was built in
(the rating offsets and the old position ranks it patches are gone), so it no longer runs as it
is; verify.py checks the built model against reference.pickle.

Player stat scores with and without API-Football's match rating (audit/commercial-plan.md).

Reads the local appearance cache only (.cache/appearances.pickle, written by the nightly run's
cache.cached_rows); no database. For every player-season with 900+ minutes it scores the season
with the live weights (player_ratings.WEIGHTS) and with variants that leave the rating out, and
reports for each role group:
    moved    how far the stats percentile and the rank it implies move against the live weights
    repeat   Spearman correlation of a player's percentile in one season with his next, for all
             players and for those who changed club (the check the live weights were chosen on)
Writes results.json next to this file.
"""
import json
import math
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc import config, player_ratings as pr  # noqa: E402

MIN_MINUTES = 900
CLUB = 900                 # club level used to turn a percentile into a rank (the same for both versions)


def without_rating(weights):
    """The live outfield weights with the match rating left out, the rest scaled up to the same total."""
    out = {}
    for pos, w in weights.items():
        kept = {k: v for k, v in w.items() if k not in ("rating", "gk_rating")}
        scale = sum(abs(v) for v in w.values()) / sum(abs(v) for v in kept.values())
        out[pos] = {k: v * scale for k, v in kept.items()}
    return out


VARIANTS = {"live": pr.WEIGHTS, "no_rating": without_rating(pr.WEIGHTS)}
# keepers have little else: the candidates that need no rating
GK_VARIANTS = {
    "live": pr.WEIGHTS["GK"],
    "save_pct": {"save_pct": 1.0},
    "save_pct_conceded": {"save_pct": .5, "conceded": -.5},
    "conceded": {"conceded": -1.0},
}


def load_apps():
    with open(ROOT / ".cache" / "appearances.pickle", "rb") as fh:
        parts = pickle.load(fh)["parts"]
    return [row for p in sorted(parts) for row in parts[p][1]]


def rating_offsets(apps):
    """{(league, broad position): league average rating - average across leagues}, as
    player_ratings._rating_offsets does in SQL."""
    lg, allp = defaultdict(lambda: [0.0, 0.0]), defaultdict(lambda: [0.0, 0.0])
    for r in apps:
        if r[7] is not None and (r[3] or 0) > 0:
            for d, k in ((lg, (r[9], r[5])), (allp, r[5])):
                d[k][0] += r[7] * r[3]
                d[k][1] += r[3]
    return {k: s / m - allp[k[1]][0] / allp[k[1]][1] for k, (s, m) in lg.items()}


def seasons_of(apps, offsets):
    """{(player, season): entry} with sums, roles, broad positions, minutes by team and league."""
    out = defaultdict(lambda: {"sums": dict.fromkeys(pr.SUMS, 0.0), "roles": Counter(), "broad": Counter(),
                               "teams": Counter(), "ref": 0.0})
    for row in apps:
        if not (row[3] or 0) > 0:
            continue
        e = out[(row[2], row[8])]
        pr._add_season(e, row, pr._adjusted(row, offsets))
        e["teams"][row[1]] += row[3]
        if row[9] in pr.REFERENCE:
            e["ref"] += row[3]
    return out


def score(m, weights, norms):
    return sum(w * (m[k] - norms[k][0]) / norms[k][1] for k, w in weights.items() if m[k] is not None)


def norms_for(rows, keys):
    out = {}
    for k in keys:
        vals = [m[k] for m in rows if m[k] is not None]
        mean = sum(vals) / len(vals)
        out[k] = (mean, math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) or 1)
    return out


def ranks_of(xs):
    order = sorted(range(len(xs)), key=xs.__getitem__)
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = ranks_of(a), ranks_of(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return cov / math.sqrt(va * vb) if va and vb else None


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(int(q * len(xs)), len(xs) - 1)] if xs else None


def main():
    apps = load_apps()
    seasons = seasons_of(apps, rating_offsets(apps))
    by_group = defaultdict(dict)           # group -> {(player, season): (metrics, main team, in reference leagues)}
    for key, e in seasons.items():
        if e["sums"]["minutes"] < MIN_MINUTES:
            continue
        pos, m = pr.season_group(e), pr.metrics(e["sums"])
        if pos in pr.WEIGHTS and m:
            by_group[pos][key] = (m, e["teams"].most_common(1)[0][0], e["ref"] >= e["sums"]["minutes"] / 2)

    def percentiles(pos, weights):
        """{key: stats percentile} for one role group under one set of weights."""
        rows = by_group[pos]
        ref_rows = [m for m, _, ref in rows.values() if ref]
        norms = norms_for(ref_rows, weights)
        ref_scores = sorted(score(m, weights, norms) for m in ref_rows)
        return {k: pr.stretched_pct(score(m, weights, norms), ref_scores) for k, (m, _, _) in rows.items()}

    def repeat(pos, pct):
        """Spearman of season t with t + 1: (all, n, changed club, n)."""
        rows = by_group[pos]
        pairs = [(pct[(p, s)], pct[(p, s + 1)], rows[(p, s)][1] != rows[(p, s + 1)][1])
                 for (p, s) in rows if (p, s + 1) in rows]
        moved = [x for x in pairs if x[2]]
        return (spearman([a for a, _, _ in pairs], [b for _, b, _ in pairs]), len(pairs),
                spearman([a for a, _, _ in moved], [b for _, b, _ in moved]), len(moved))

    def compare(pos, live, other):
        dp = [abs(other[k] - live[k]) for k in live]
        dr = [abs(pr.final_rank(other[k], CLUB, pos) - pr.final_rank(live[k], CLUB, pos)) for k in live]
        return {"spearman_with_live": spearman([live[k] for k in live], [other[k] for k in live]),
                "pct_mean_abs": sum(dp) / len(dp), "rank_mean_abs": sum(dr) / len(dr),
                "rank_p95_abs": quantile(dr, .95), "rank_max_abs": max(dr),
                "share_rank_moved_2plus": sum(d >= 2 for d in dr) / len(dr)}

    out = {"min_minutes": MIN_MINUTES, "appearances": len(apps),
           "seasons": sorted({s for _, s in seasons}), "groups": {}, "keepers": {}}
    pooled = {name: [] for name in VARIANTS}
    for pos in pr.OUTFIELD_GROUPS:
        live = percentiles(pos, VARIANTS["live"][pos])
        other = percentiles(pos, VARIANTS["no_rating"][pos])
        g = {"player_seasons": len(live), "rating_weight": pr.WEIGHTS[pos]["rating"],
             "moved": compare(pos, live, other)}
        for name, pct in (("live", live), ("no_rating", other)):
            r_all, n_all, r_moved, n_moved = repeat(pos, pct)
            g[name] = {"repeat_all": r_all, "pairs": n_all, "repeat_changed_club": r_moved, "pairs_changed": n_moved}
            rows = by_group[pos]
            pooled[name] += [(pct[(p, s)], pct[(p, s + 1)], rows[(p, s)][1] != rows[(p, s + 1)][1])
                             for (p, s) in rows if (p, s + 1) in rows]
        out["groups"][pos] = g
    out["outfield_pooled"] = {
        name: {"repeat_all": spearman([a for a, _, _ in v], [b for _, b, _ in v]), "pairs": len(v),
               "repeat_changed_club": spearman([a for a, _, c in v if c], [b for _, b, c in v if c]),
               "pairs_changed": sum(c for _, _, c in v)}
        for name, v in pooled.items()}

    gk_live = percentiles("GK", GK_VARIANTS["live"])
    for name, w in GK_VARIANTS.items():
        pct = percentiles("GK", w)
        r_all, n_all, r_moved, n_moved = repeat("GK", pct)
        out["keepers"][name] = {"repeat_all": r_all, "pairs": n_all, "repeat_changed_club": r_moved,
                                "pairs_changed": n_moved, "moved": compare("GK", gk_live, pct)}

    # the players it moves most this season, as a sense check
    names = {}
    latest = max(out["seasons"])
    movers = []
    for pos in pr.OUTFIELD_GROUPS:
        live = percentiles(pos, VARIANTS["live"][pos])
        other = percentiles(pos, VARIANTS["no_rating"][pos])
        for (p, s), v in live.items():
            if s == latest - 1:
                movers.append((pr.final_rank(other[(p, s)], CLUB, pos) - pr.final_rank(v, CLUB, pos), p, pos))
    movers.sort()
    out["biggest_moves_last_full_season"] = {"season": latest - 1,
                                             "down": [(p, pos, round(d, 1)) for d, p, pos in movers[:8]],
                                             "up": [(p, pos, round(d, 1)) for d, p, pos in movers[-8:][::-1]]}
    (Path(__file__).parent / "results.json").write_text(json.dumps(out, indent=1))

    f = lambda x: "  n/a" if x is None else f"{x:5.2f}"
    print(f"{len(apps):,} appearances; seasons {out['seasons'][0]}-{out['seasons'][-1]}; {MIN_MINUTES}+ minutes")
    print("group  seasons  w(rating)  same-order  rank moved: mean  p95   max  2+pts | repeat all: live  none | changed club: live  none (pairs)")
    for pos, g in out["groups"].items():
        m = g["moved"]
        print(f"{pos:5} {g['player_seasons']:8}  {g['rating_weight']:9.2f}  {f(m['spearman_with_live'])}       "
              f"{m['rank_mean_abs']:16.2f} {m['rank_p95_abs']:4.1f} {m['rank_max_abs']:5.1f} {m['share_rank_moved_2plus']:5.0%} | "
              f"{f(g['live']['repeat_all'])} {f(g['no_rating']['repeat_all'])} | "
              f"{f(g['live']['repeat_changed_club'])} {f(g['no_rating']['repeat_changed_club'])} ({g['live']['pairs_changed']})")
    p = out["outfield_pooled"]
    print(f"outfield pooled: repeat all {f(p['live']['repeat_all'])} -> {f(p['no_rating']['repeat_all'])} ({p['live']['pairs']} pairs); "
          f"changed club {f(p['live']['repeat_changed_club'])} -> {f(p['no_rating']['repeat_changed_club'])} ({p['live']['pairs_changed']})")
    print("keepers:")
    for name, g in out["keepers"].items():
        print(f"  {name:18} repeat all {f(g['repeat_all'])} ({g['pairs']}), changed club {f(g['repeat_changed_club'])} "
              f"({g['pairs_changed']}); rank moved mean {g['moved']['rank_mean_abs']:.2f}, max {g['moved']['rank_max_abs']:.1f}")


if __name__ == "__main__":
    main()
