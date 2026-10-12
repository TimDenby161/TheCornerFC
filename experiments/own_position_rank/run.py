"""Is a player's rank in the position the site lists him in his Ability, has he one in every
outfield position, and has nothing else moved? (DESIGN.md, as amended 2026-10-12: the first
version of this file, at 7440a0923, judged a rule inside the model and its answer is
results_first.json.)

Runs player_ratings.compute_player_ratings once as it now is, on a read-only connection, with
the database write and the line-up capture replaced. What season_model was given is kept and
given again to the model file as it was at BASE (read from git, checked against its
fingerprint), and the two answers are compared. Nothing is written to the database and no API is
called; the local .cache is refreshed as any local run does.

Writes results.json next to this file and prints the verdict.

    python experiments/own_position_rank/run.py
"""
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc import config; from thecornerfc.pipeline import db; from thecornerfc.evidence import lineup_snapshots; from thecornerfc.models import player_ratings as pr  # noqa: E402
from thecornerfc.models.positions import GROUPS  # noqa: E402
from thecornerfc.publish.site_players import shown_position_ranks  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results.json"
BASE = "07363e9c9"         # the commit the change is made from
BASE_SHA256 = "01914fea926d946632b5b14bf2d7a8dcef8479b3510fa7393b71fa8cc3bde5be"   # player_ratings.py there
TOP = 10


def base_model():
    """player_ratings.py as it was at BASE, as a module of its own beside the live one."""
    source = subprocess.check_output(["git", "show", f"{BASE}:thecornerfc/models/player_ratings.py"], cwd=ROOT)
    if hashlib.sha256(source).hexdigest() != BASE_SHA256:
        raise SystemExit(f"player_ratings.py at {BASE} is not the file this was registered against")
    spec = importlib.util.spec_from_loader("thecornerfc.models.player_ratings_base", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, f"player_ratings.py@{BASE}", "exec"), module.__dict__)
    return module


def both(conn):
    """One run of the live routine. Returns (base answer, new answer, the players it lists as
    {player: role label}); an answer is {"rows", "positions", "projections"}."""
    call, listed = {}, {}
    live_model = pr.season_model

    def season_model(*args, **kwargs):
        call.update(args=args, kwargs=dict(kwargs))
        return live_model(*args, **kwargs)

    def capture(conn, appearance_scores, to_rank, team_out, lineups, current, season_rows, position_ranks,
                projections, components=None, history=None):
        listed.update({p: label for p, _, label, _ in current})

    saved = pr.season_model, pr._write, lineup_snapshots.capture_predictions
    pr.season_model, pr._write, lineup_snapshots.capture_predictions = season_model, capture, lambda *a, **k: None
    try:
        pr.compute_player_ratings(conn)
    finally:
        pr.season_model, pr._write, lineup_snapshots.capture_predictions = saved
    conn.rollback()

    def answer(model):
        got = {"positions": {}, "projections": {}}
        kwargs = dict(call["kwargs"], position_ranks=got["positions"], projections=got["projections"])
        got["rows"] = model.season_model(*call["args"], **kwargs)
        return got
    return answer(base_model()), answer(pr), listed


def shown_positions(conn, listed):
    """{player: the position the site lists him in}: where he has started most minutes over the
    last 12 months, else his latest rating window's most common start
    (site_players.export_players)."""
    mins = defaultdict(dict)
    for player, role, m in conn.execute(
            """select fp.player_id, fp.role, sum(fp.minutes) from fixture_players fp join fixtures f using (fixture_id)
               where fp.player_id = any(%s) and fp.role is not null and fp.minutes > 0
                 and f.status_short = any(%s) and f.kickoff > now() - interval '365 days'
               group by 1, 2""", [list(listed), list(config.FINISHED_STATUSES)]):
        mins[player][role] = m
    conn.rollback()
    return {p: max(mins[p], key=mins[p].get) if p in mins else label for p, label in listed.items()}


def moves(pairs):
    d = sorted(abs(a - b) for a, b in pairs)
    if not d:
        return {"n": 0}
    return {"n": len(d), "mean": round(sum(d) / len(d), 2), "p95": round(d[int(.95 * (len(d) - 1))], 1),
            "largest": round(d[-1], 1), "two_or_more": round(sum(x >= 2 for x in d) / len(d), 4)}


def evaluate(base, new, listed, shown):
    season = max(y for _, y, _, _, _ in new["rows"])
    rows = lambda got: {(p, y): (r, m, t) for p, y, r, m, t in got["rows"]}
    flat = lambda d: {(p, k): v for p, inner in d.items() for k, v in inner.items()}
    different = lambda a, b: len(set(a) ^ set(b)) + sum(a[k] != b[k] for k in set(a) & set(b))
    ability = {p: r for p, y, r, _, _ in new["rows"] if y == season}
    was, now = flat(base["positions"]), flat(new["positions"])
    # the listed outfield players, by the role group of the position the site lists them in,
    # and their position ranks as the export publishes them
    on_site = {p: GROUPS[role] for p, role in shown.items() if GROUPS.get(role) not in (None, "GK") and p in ability}
    published = flat({p: shown_position_ranks(shown[p], ability[p], new["positions"].get(p, {})) for p in on_site})
    broken = sorted(p for p, g in on_site.items() if published.get((p, g)) != ability[p])
    checks = {
        "season_ranks_untouched": different(rows(base), rows(new)) == 0,
        "projected_ranks_untouched": different(flat(base["projections"]), flat(new["projections"])) == 0,
        "every_position_ranked_none_lost": set(was) <= set(now) and all(
            set(inner) == set(pr.OUTFIELD_GROUPS) for inner in new["positions"].values()),
        "listed_position_is_ability": bool(on_site) and not broken,
    }

    whole = lambda r: math.floor(r + 0.5)                # as the site rounds a rank
    same_whole = lambda ranks: round(sum((p, g) in ranks and whole(ranks[(p, g)]) == whole(ability[p])
                                         for p, g in on_site.items()) / len(on_site), 4) if on_site else None
    # what the rule covers over: the model's own rank for him in the position he is listed in
    covered = sorted(abs(now[(p, g)] - ability[p]) for p, g in on_site.items() if (p, g) in now)
    unplayed = sorted(ability[p] - r for (p, g), r in now.items() if (p, g) not in was and p in ability)
    spread = {"n": len(unplayed)}
    if unplayed:
        spread.update(mean_below_ability=round(sum(unplayed) / len(unplayed), 1),
                      p5=round(unplayed[int(.05 * (len(unplayed) - 1))], 1),
                      p95=round(unplayed[int(.95 * (len(unplayed) - 1))], 1), above_ability=sum(d < 0 for d in unplayed))
    top = {}
    for group in pr.OUTFIELD_GROUPS:
        best = lambda ranks: {p for _, p in sorted(((ranks[(p, group)], p) for p, g in on_site.items()
                                                    if g == group and (p, group) in ranks), reverse=True)[:TOP]}
        top[group] = len(best(was) & best(published))
    return {
        "season": season,
        "checks": checks,
        "passed": all(checks.values()),
        "counts": {
            "season_rows": len(new["rows"]), "position_ranks": len(now), "players_listed": len(listed),
            "listed_outfield": len(on_site), "listed_position_not_ability": len(broken),
            "listed_with_no_model_rank_there": sum((p, g) not in now for p, g in on_site.items()),
        },
        "listed_position_rounds_to_ability": {"base": same_whole(was), "model": same_whole(now), "published": same_whole(published)},
        "model_rank_against_ability_in_listed_position": {
            **moves([(now[(p, g)], ability[p]) for p, g in on_site.items() if (p, g) in now]),
            "five_or_more": sum(d >= 5 for d in covered), "ten_or_more": sum(d >= 10 for d in covered)},
        "moves": {"positions_the_base_ranked": moves([(was[k], now[k]) for k in set(was) & set(now)])},
        "unplayed_positions": spread,
        f"top_{TOP}_kept": top,
    }


def main():
    conn = db.connect()
    conn.read_only = True                # whatever this machine is switched to, this run writes nothing
    said = conn.execute("select site.environment()").fetchone()[0]
    conn.rollback()
    base, new, listed = both(conn)
    result = {"database": said, "base": BASE, **evaluate(base, new, listed, shown_positions(conn, listed))}
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))
    print("PASSED" if result["passed"] else "FAILED")


if __name__ == "__main__":
    main()
