"""Record of the October 2026 tuning. It ran against player_ratings.py as it was before the result was built in
(the rating offsets and the old position ranks it patches are gone), so it no longer runs as it
is; verify.py checks the built model against reference.pickle.

Try other settings of the player rank formula and see a role's top list.

    python experiments/player_no_rating/try_settings.py FB 10 OUT_STATS_WEIGHT=0.5 POSITION_STATS.FB=1.0
    (FB@any: every player's rank in that position; FB/LWB,RWB: only those main roles;
    several lists in one run: GK+CB@any+FB@any)

Runs the candidate weights with the owner's agreed settings (replay.agreed) once on the read-only connection with the named
player_ratings constants changed (NAME=value, or DICT.KEY=value; W.ROLE.stat=value sets a
candidate stat weight), and prints the role's top N
next to the unchanged candidate from replay.json (run replay.py first). Nothing is written.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import replay  # noqa: E402
from replay import pr  # noqa: E402


def stat_columns(conn, got, group):
    """(header, {player: text}): last full season's figures on every stat weighted for the role."""
    from collections import Counter
    season = max(y for _, y, _, _, _ in got["season_rows"]) - 1
    w = {k: v for k, v in replay.CANDIDATE[group].items() if v}
    total = sum(abs(v) for v in w.values())
    keys = sorted(w, key=lambda k: -abs(w[k]))
    sums = {}
    for row in pr._appearances(conn):
        if row[8] == season and (row[3] or 0) > 0:
            e = sums.setdefault(row[2], {"sums": dict.fromkeys(pr.SUMS, 0.0), "roles": Counter(), "broad": Counter()})
            pr._add_season(e, row, None)
    head = f"{'mins':>5} " + " ".join(f"{k[:11]:>11}" for k in keys) + "\n" + " " * 67 + " ".join(
        f"{('-' if w[k] < 0 else '') + format(100 * abs(w[k]) / total, '.0f') + '%':>11}" for k in keys)
    text = {}
    for p, e in sums.items():
        m = pr.metrics(e["sums"])
        text[p] = f"{int(e['sums']['minutes']):5} " + " ".join(
            f"{'-' if m[k] is None else format(m[k], '.2f'):>11}" for k in keys)
    return f"stats: {season}/{(season + 1) % 100} league figures, per 90 or a ratio; weight under each\n" + " " * 61 + head, text


def main():
    groups, top = sys.argv[1].split("+"), int(sys.argv[2])
    conn = replay.db.connect()
    replay.agreed(conn)
    for arg in sys.argv[3:]:
        name, value = arg.split("=")
        if name == "TOP_STATS":          # TOP_STATS=2: stats count this many times more at the strongest clubs
            replay.top_stats(float(value))
        elif name.startswith("W."):      # W.FB.tackles_int=0.2: a candidate stat weight for one role
            _, role, stat = name.split(".")
            replay.CANDIDATE[role][stat] = float(value)
        elif "." in name:
            name, key = name.split(".")
            getattr(pr, name)[key] = float(value)
        else:
            setattr(pr, name, float(value))
    got = replay.replay(conn, replay.CANDIDATE)
    marked = replay.backups(conn, got)
    conn.rollback()
    base = {r[0]: r for r in json.loads((Path(__file__).parent / "replay.json").read_text())["all"]}
    for group in groups:
        roles = None                     # FB/LWB,RWB: only players whose main role is one of these
        if "/" in group:
            group, roles = group.split("/")
            roles = set(roles.split(","))
        if group.endswith("@any"):       # FB@any: everyone's rank in that position, whatever his main role
            group = group[:-4]
            rows = [(ranks[group], p) for p, ranks in got["position_ranks"].items() if group in ranks and p in base]
            print(f"{group}, every player with a rank in that position: {' '.join(sys.argv[3:]) or 'no changes'}")
        else:
            rows = [(r * (1 - pr.SQUAD_MARKDOWN) if p in marked else r, p) for p, r, label, _ in got["current"]
                    if p in base and pr.role_group(label) == group and (roles is None or label in roles)]
            print(f"{group}, players whose main role it is: {' '.join(sys.argv[3:]) or 'no changes'}")
        rows.sort(reverse=True)
        head, stats = stat_columns(conn, got, group)
        print(head)
        for i, (r, p) in enumerate(rows[:top], 1):
            b = base[p]
            print(f"{i:3} {str(b[1])[:22]:22} {str(b[2])[:18]:18} {b[3]:4} {r:5.1f} {'':5} {stats.get(p, '')}")


if __name__ == "__main__":
    main()
