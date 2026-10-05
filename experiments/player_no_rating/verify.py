"""Does the model as built reproduce what the owner approved?

Runs player_ratings.compute_player_ratings as it now is (read-only, the database write and the
line-up snapshot replaced by a capture) and compares it with reference.pickle, the experiment's
output on the agreed settings (replay.py). Prints the differences; nothing is written.
"""
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from thecornerfc import db, lineup_snapshots, player_ratings as pr  # noqa: E402


def main():
    got = {}

    def capture(conn, appearance_scores, to_rank, team_out, lineups, current, season_rows, position_ranks,
                projections, components=None, history=None):
        got.update(team_out=team_out, lineups=lineups, current=current, season_rows=season_rows,
                   position_ranks=position_ranks, projections=projections)
    pr._write = capture
    lineup_snapshots.capture_predictions = lambda *a, **k: None
    conn = db.connect()
    pr.compute_player_ratings(conn)
    conn.rollback()
    ref = pickle.loads((Path(__file__).parent / "reference.pickle").read_bytes())

    def compare(name, a, b, tol=0.05):
        keys = set(a) & set(b)
        diffs = sorted(((abs(a[k] - b[k]), k) for k in keys if a[k] is not None and b[k] is not None
                        and abs(a[k] - b[k]) > tol), reverse=True)
        print(f"{name}: {len(keys)} in both, {len(set(a) ^ set(b))} in one only, "
              f"{len(diffs)} differ by more than {tol}" + (f"; biggest {diffs[:5]}" if diffs else ""))
        return diffs

    mark = 1 - pr.SQUAD_MARKDOWN
    compare("current rank", {p: r for p, r, _, _ in got["current"]},
            {p: r * mark if p in ref["marked"] else r for p, r, _, _ in ref["current"]})
    compare("role label", {p: hash(l) for p, _, l, _ in got["current"]}, {p: hash(l) for p, _, l, _ in ref["current"]}, 0)
    season = max(y for _, y, _, _, _ in got["season_rows"])
    compare("season ranks, earlier seasons", {(p, y): r for p, y, r, _, _ in got["season_rows"] if y != season},
            {(p, y): r for p, y, r, _, _ in ref["season_rows"] if y != season})
    compare("position ranks", {(p, g): r for p, d in got["position_ranks"].items() for g, r in d.items()},
            {(p, g): r for p, d in ref["position_ranks"].items() for g, r in d.items()})
    compare("projections (not backups)", {(p, y): r for p, d in got["projections"].items() if p not in ref["marked"] for y, r in d.items()},
            {(p, y): r for p, d in ref["projections"].items() if p not in ref["marked"] for y, r in d.items()})
    compare("predicted XI rating", {(r[0], r[1]): r[2] for r in got["team_out"]}, {(r[0], r[1]): r[2] for r in ref["team_out"]})
    a = {(f, t, p) for f, t, p, _, _ in got["lineups"]}
    b = {(f, t, p) for f, t, p, _, _ in ref["lineups"]}
    print(f"predicted line-ups: {len(a & b)} the same, {len(a ^ b)} different")
    built = {p for p, y, _, m, t in got["season_rows"] if y == season and m == 0 and t} & {p for p, _, l, _ in got["current"] if l == "GK"}
    cur = {p: r for p, r, _, _ in got["current"]}
    was = {p: r for p, r, _, _ in ref["current"]}
    down = {p for p in cur if p in was and p in built and cur[p] < was[p] - 1}
    print(f"backup keepers marked down: built {len(down)}, experiment {len(ref['marked'])}, "
          f"in both {len(down & set(ref['marked']))}")

    # against what the live model has stored: how far the published numbers move
    stored = dict(conn.execute("select player_id, current_rank::float8 from players where current_rank is not null").fetchall())
    d = sorted(abs(cur[p] - stored[p]) for p in cur if p in stored)
    print(f"current rank against stored: {len(d)} players, mean move {sum(d) / len(d):.2f}, "
          f"95th percentile {d[int(.95 * len(d))]:.1f}, biggest {d[-1]:.1f}, 2+ points {sum(x >= 2 for x in d) / len(d):.0%}")
    upcoming = {f for (f,) in conn.execute("select fixture_id from fixtures where status_short in ('NS', 'TBD') and kickoff > now()")}
    lines = {(f, t): v for f, t, *v in conn.execute(
        """select fixture_id, team_id, predicted_gk::float8, predicted_def::float8, predicted_mid::float8,
                  predicted_fwd::float8 from fixture_team_ratings where fixture_id = any(%s)""", [list(upcoming)])}
    for i, name in enumerate(("GK", "DEF", "MID", "FWD")):
        d = sorted(abs(r[-4 + i] - lines[(r[0], r[1])][i]) for r in got["team_out"]
                   if (r[0], r[1]) in lines and r[-4 + i] is not None and lines[(r[0], r[1])][i] is not None)
        if d:
            print(f"upcoming {name} line against stored: {len(d)} team-fixtures, mean move {sum(d) / len(d):.2f}, biggest {d[-1]:.1f}")
    was_xi = {(f, t, p) for f, t, p in conn.execute("select fixture_id, team_id, player_id from predicted_lineups")}
    print(f"predicted line-ups against stored: {len(a & was_xi)} the same, {len(a - was_xi)} new, {len(was_xi - a)} gone")
    conn.rollback()


if __name__ == "__main__":
    main()
