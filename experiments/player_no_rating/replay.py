"""Record of the October 2026 tuning. It ran against player_ratings.py as it was before the result was built in
(the rating offsets and the old position ranks it patches are gone), so it no longer runs as it
is; verify.py checks the built model against reference.pickle.

Full replay of the player ratings with and without API-Football's match rating.

Runs player_ratings.compute_player_ratings twice on a read-only connection (the local default,
READ_ONLY_DATABASE_URL), with the database write and the line-up snapshot replaced by a capture:
once with the live weights and once with the candidate ones (CANDIDATE below). Nothing is written
to the database; the local .cache is refreshed as any local run does.

Then, on the candidate only, the backup fix: a keeper with no minutes this season at a club in
the per-match leagues that has played BACKUP_GAMES or more, and who is not on an upcoming
fixture's injury list, is scaled down by SQUAD_MARKDOWN (he would be if he had played a minute).

Writes replay.json next to this file and prints a summary.
"""
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from thecornerfc import config; from thecornerfc.pipeline import db; from thecornerfc.evidence import lineup_snapshots; from thecornerfc.models import player_ratings as pr, positions  # noqa: E402
from run import quantile, rating_offsets, spearman, without_rating  # noqa: E402

BACKUP_GAMES = 5
CANDIDATE = without_rating(pr.WEIGHTS)
CANDIDATE["GK"] = {"save_pct": .50, "pass_acc": .25, "conceded": -.25}   # owner's choice 2026-10-04


def add_failed_dribbles(conn):
    """A stat the live model doesn't use yet: failed dribbles per 90 ("dribbles_lost": attempts
    minus dribbles won, both stored for every appearance). Attempts aren't in the appearance
    cache, so they're fetched once (.cache/experiment_dribbles.pickle) and added to each row
    here; season totals from the other leagues have none and leave the stat out."""
    if "dribbles" in pr.STATS:
        return
    path = pr.cached_rows.__globals__["CACHE_DIR"] / "experiment_dribbles.pickle"
    if path.exists():
        attempts = pickle.loads(path.read_bytes())
    else:
        attempts = {(f, p): n for f, p, n in conn.execute(
            "select fixture_id, player_id, dribbles from fixture_players where dribbles > 0")}
        path.write_bytes(pickle.dumps(attempts))
        conn.rollback()
    rows = [r[:-1] + (attempts.get((r[0], r[2]), 0), r[-1]) for r in pr._appearances(conn)]
    conn.rollback()
    pr._appearances = lambda conn: rows
    pr.STATS = pr.STATS + ("dribbles",)
    pr.SUMS = pr.STATS + ("xga", "xg_mins")
    pr.METRIC_INPUTS["dribbles_lost"] = {"dribbles"}
    live_metrics = pr.metrics

    def metrics(s):
        m = live_metrics(s)
        if m:
            m["dribbles_lost"] = max(s.get("dribbles", 0) - s["dribbles_won"], 0) * 90 / s["minutes"]
        return m
    pr.metrics = metrics


def top_stats(top, lo=950.0, hi=1080.0):
    """Outfield stats move a player further from his club's level the stronger the club: x 1 at a
    club rated `lo` or below (as now), rising to x `top` at `hi` and above. The elite bonus, the
    club base and everything else are as in player_ratings.outfield_rank."""
    def outfield_rank(pct, club, share=None, pos=None):
        mult = 1 + (top - 1) * min(max((club - lo) / (hi - lo), 0.0), 1.0)
        stats = pr.OUT_STATS_WEIGHT * mult * (pct - 50) + pr.ELITE_WEIGHT * max(0.0, pct - pr.ELITE_FROM)
        r = (100 * min(club / pr.CLUB_RANK_MAX, 1) - pr.OUT_CLUB_OFFSET + pr.POSITION_STATS.get(pos, 1.0) * stats
             + pr.POSITION_OFFSET.get(pos, 0))
        if share is not None:
            r *= min(1.0, 1 - pr.SQUAD_MARKDOWN + pr.SQUAD_MARKDOWN * share / pr.OUT_FULL_SHARE)
        return pr.soft_ceiling(r)
    pr.outfield_rank = outfield_rank


def agreed(conn):
    """The owner's choices after the first replay (2026-10-05), applied to player_ratings in this
    process only: failed dribbles as a stat, the full-back weights, a bigger penalty for an
    unfamiliar position, and wing-backs as a role group of their own (they were full-backs)."""
    add_failed_dribbles(conn)
    CANDIDATE["FB"] = {"key_passes": .18, "dribbled_past": -.15, "tackles_int": .13, "passes": .12, "pass_acc": .09,
                       "assists": .08, "goals": .06, "dribbles_won": .06, "shots_on": .05, "dribbles_lost": -.04,
                       "duels_pct": .04}
    pr.FAMILIARITY_PENALTY = 10.0
    pr.POSITION_OWN_LEVEL = True         # a position's rank says how good he is in that position
    pr.LEVEL_DECAY = 0.5                 # an older season counts half the one after it (was 0.7)
    top_stats(2.0)                       # stats count up to twice as much at the strongest clubs
    CANDIDATE["AM"]["assists"] = .16
    CANDIDATE["CM"].update(passes=.20, key_passes=.15, shots_on=.05)
    for weights in CANDIDATE.values():   # discipline (fouls and cards) dropped everywhere: "not useful"
        weights.pop("discipline", None)
    if "WB" in pr.OUTFIELD_GROUPS:
        return
    CANDIDATE["WB"] = {"key_passes": .20, "tackles_int": .12, "dribbled_past": -.12, "passes": .09, "assists": .09,
                       "dribbles_won": .08, "pass_acc": .07, "goals": .07, "shots_on": .06, "duels_pct": .05,
                       "dribbles_lost": -.05}
    positions.GROUPS.update(LWB="WB", RWB="WB")
    pr.OUTFIELD_GROUPS = pr.OUTFIELD_GROUPS + ("WB",)
    pr.POSITION_STATS["WB"], pr.POSITION_OFFSET["WB"] = pr.POSITION_STATS["FB"], pr.POSITION_OFFSET["FB"]
    # line-up selection as before: a wing-back fills other slots as a full-back did
    for pair, fit in list(pr.GROUP_FIT.items()):
        if "FB" in pair:
            pr.GROUP_FIT[frozenset({"WB"} | (pair - {"FB"}))] = fit
    pr.GROUP_FIT[frozenset(("WB", "FB"))] = pr.SAME_GROUP_FIT


def replay(conn, weights):
    """One run of the live routine with these weights; returns what it would have written."""
    got = {}

    def capture(conn, appearance_scores, to_rank, team_out, lineups, current, season_rows, position_ranks,
                projections, components=None, history=None):
        got.update(team_out=team_out, lineups=lineups, current=current, season_rows=season_rows,
                   position_ranks=position_ranks, projections=projections)

    saved = pr.WEIGHTS, pr._write, lineup_snapshots.capture_predictions, pr._offsets
    pr.WEIGHTS, pr._write = weights, capture
    # the live one builds a temp table, which a read-only connection can't: the same sums in Python
    pr._offsets = lambda conn: rating_offsets(pr._appearances(conn))
    lineup_snapshots.capture_predictions = lambda *a, **k: None
    try:
        pr.compute_player_ratings(conn)
    finally:
        pr.WEIGHTS, pr._write, lineup_snapshots.capture_predictions, pr._offsets = saved
    conn.rollback()
    return got


def backups(conn, got):
    """{player: club} for keepers the backup fix marks down (see module docstring)."""
    season = max(y for _, y, _, _, _ in got["season_rows"])
    games = dict(conn.execute(
        """select team_id, count(*) from (
               select home_team_id as team_id from fixtures where league_id = any(%(l)s) and season = %(s)s
                 and status_short in ('FT', 'AET', 'PEN')
               union all
               select away_team_id from fixtures where league_id = any(%(l)s) and season = %(s)s
                 and status_short in ('FT', 'AET', 'PEN')) g group by 1""",
        {"l": config.MATCH_PLAYER_LEAGUES, "s": season}).fetchall())
    injured = {p for (p,) in conn.execute(
        """select distinct i.player_id from injuries i join fixtures f using (fixture_id)
           where f.status_short in ('NS', 'TBD') and f.kickoff > now()""")}
    keepers = {p for p, _, label, _ in got["current"] if label == "GK"}
    # the season model gives a season with no minutes a row with minutes 0 and his club that season
    return {p: team for p, y, _, mins, team in got["season_rows"]
            if y == season and mins == 0 and team and p in keepers and p not in injured
            and games.get(team, 0) >= BACKUP_GAMES}


def main():
    conn = db.connect()
    live = replay(conn, pr.WEIGHTS)
    agreed(conn)                         # everything the owner chose, for the candidate run only
    cand = replay(conn, CANDIDATE)
    marked = backups(conn, cand)
    # the candidate run as the model would write it: the reference a built version has to reproduce
    with open(Path(__file__).parent / "reference.pickle", "wb") as fh:
        pickle.dump({"current": cand["current"], "season_rows": cand["season_rows"], "marked": marked,
                     "position_ranks": cand["position_ranks"], "projections": cand["projections"],
                     "team_out": cand["team_out"], "lineups": cand["lineups"]}, fh)
    names = dict(conn.execute("select player_id, name from players").fetchall())
    teams = dict(conn.execute("select team_id, name from teams").fetchall())
    stored = dict(conn.execute("select player_id, current_rank::float8 from players where current_rank is not null").fetchall())
    club = dict(conn.execute("""select distinct on (fp.player_id) fp.player_id, fp.team_id from fixture_players fp
                                join fixtures f using (fixture_id) order by fp.player_id, f.kickoff desc""").fetchall())
    upcoming = {f for (f,) in conn.execute("select fixture_id from fixtures where status_short in ('NS', 'TBD') and kickoff > now()")}
    conn.rollback()

    a = {p: (r, label, m) for p, r, label, m in live["current"]}
    b = {p: (r * (1 - pr.SQUAD_MARKDOWN) if p in marked else r, label, m) for p, r, label, m in cand["current"]}
    both = sorted(set(a) & set(b))
    group = lambda p: pr.role_group(a[p][1]) or a[p][1]

    out = {"players": len(both), "candidate_weights": CANDIDATE, "backup_games": BACKUP_GAMES}
    # the live replay against what the nightly run stored (they should agree, bar matches since)
    d0 = [abs(a[p][0] - stored[p]) for p in both if p in stored]
    out["live_replay_vs_stored"] = {"players": len(d0), "mean_abs": sum(d0) / len(d0), "max_abs": max(d0),
                                    "share_same": sum(x < 0.05 for x in d0) / len(d0)}
    by = defaultdict(list)
    for p in both:
        if p not in marked:
            by[group(p)].append(b[p][0] - a[p][0])
    out["current_rank_moved"] = {
        g: {"players": len(v), "mean_abs": sum(map(abs, v)) / len(v), "p95_abs": quantile(list(map(abs, v)), .95),
            "max_abs": max(map(abs, v)), "share_2plus": sum(abs(x) >= 2 for x in v) / len(v),
            "mean": sum(v) / len(v)}
        for g, v in sorted(by.items())}
    outfield = [p for p in both if group(p) != "GK"]
    out["outfield_same_order"] = spearman([a[p][0] for p in outfield], [b[p][0] for p in outfield])
    row = lambda p, src: {"player": names.get(p, p), "club": teams.get(club.get(p)), "group": group(p),
                          "live": a[p][0], "candidate": round(b[p][0], 1)}
    top = lambda ps, src, n: [row(p, src) for p in sorted(ps, key=lambda p: -src[p][0])[:n]]
    keepers = [p for p in both if group(p) == "GK"]
    out["top_outfield_live"], out["top_outfield_candidate"] = top(outfield, a, 20), top(outfield, b, 20)
    out["top_keepers_live"], out["top_keepers_candidate"] = top(keepers, a, 20), top(keepers, b, 20)
    out["backups_marked_down"] = sorted(
        ({"player": names.get(p, p), "club": teams.get(t), "live": a[p][0], "candidate": round(b[p][0], 1)}
         for p, t in marked.items() if p in a), key=lambda r: -r["live"])
    # every listed player, so a list for any role can be read from replay.json without a re-run
    out["all"] = [[p, names.get(p), teams.get(club.get(p)), a[p][1], group(p), a[p][0], round(b[p][0], 1), a[p][2]]
                  for p in both]
    movers = sorted(outfield, key=lambda p: b[p][0] - a[p][0])
    out["outfield_biggest_falls"] = [row(p, a) for p in movers[:10]]
    out["outfield_biggest_rises"] = [row(p, a) for p in movers[-10:][::-1]]

    # team line ratings for upcoming fixtures: predictions.XI_LINE_WEIGHTS x (home - away) goals of margin
    ta = {(r[0], r[1]): r for r in live["team_out"]}
    tb = {(r[0], r[1]): r for r in cand["team_out"]}
    lines = defaultdict(list)
    xi = []
    for k in set(ta) & set(tb):
        if k[0] not in upcoming:
            continue
        if ta[k][2] is not None and tb[k][2] is not None:
            xi.append(abs(tb[k][2] - ta[k][2]))
        for name, x, y in zip(("GK", "DEF", "MID", "FWD"), ta[k][-4:], tb[k][-4:]):
            if x is not None and y is not None:
                lines[name].append(abs(y - x))
    out["upcoming_team_ratings_moved"] = {
        "team_fixtures": len(xi), "predicted_xi_mean_abs": sum(xi) / len(xi) if xi else None,
        "predicted_xi_max_abs": max(xi) if xi else None,
        "lines": {k: {"mean_abs": sum(v) / len(v), "max_abs": max(v)} for k, v in lines.items()}}
    la = Counter((f, t, p) for f, t, p, _, _ in live["lineups"])
    lb = Counter((f, t, p) for f, t, p, _, _ in cand["lineups"])
    out["predicted_lineups"] = {"slots": sum(la.values()), "same_player": sum((la & lb).values())}
    (Path(__file__).parent / "replay_final.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if not k.startswith(("top_", "outfield_big", "candidate_", "all", "backups"))}, indent=1, default=str))
    for key in ("top_keepers_candidate", "top_outfield_candidate", "outfield_biggest_falls", "outfield_biggest_rises"):
        print("==", key)
        for i, r in enumerate(out[key], 1):
            print(f"{i:2} {str(r['player'])[:24]:24} {str(r['club'])[:20]:20} {r['group']:3} live {r['live']:5.1f} -> {r['candidate']:5.1f}")


if __name__ == "__main__":
    main()
