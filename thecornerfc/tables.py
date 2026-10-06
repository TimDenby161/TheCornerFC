"""League tables worked out from the results the site holds, not copied from API-Football's
standings.

API-Football's standings give only the shape of a competition: which clubs are in which group
(a conference, an Apertura group, a cup's league stage) and what a finishing place leads to
(its description, e.g. "Relegation"). Played, won, drawn, lost, goals, points, form and the
order come from the finished fixtures.

Which matches count for a group (`group_rounds`), from the fixtures' round names
("Regular Season - 12": the part before " - " is the stage):
    1. a stage the group is named after ("Clausura - Group A": the Clausura's numbered rounds)
    2. else a cup's "League Stage" or "Group Stage" (a cup counts nothing else: its qualifying
       and knockout rounds never go in a table)
    3. else "Regular Season" when there is one. Where clubs sit in two groups (a league that
       splits: Finland's "Champion Additional"), only the biggest group is the regular season
       and the others count every match
    4. else every match

What results can't show is kept by hand in table_adjustments.json, by API-Football league id
and season: points deducted or awarded ({"points": {team: -4}}) and clubs whose results were
annulled ({"void": [team]}: their matches count for nobody). `differences` lists where a
computed table still disagrees with API-Football's, for the export's log.

Order: points, goal difference, goals scored, then name, except in the competitions listed in
ORDER, which put wins first or separate level clubs by the matches between them. Form is the
last FORM_GAMES results, newest first.
"""
import json
from collections import defaultdict
from pathlib import Path

PATH = Path(__file__).with_name("table_adjustments.json")
STAGES = ("League Stage", "Group Stage")
REGULAR = "Regular Season"
FORM_GAMES = 5
# How a competition separates clubs level on points, where it isn't goal difference first:
# "wins": most wins, then goal difference, goals scored
# "h2h": points, then goal difference, in the matches between the level clubs; then overall
# (API-Football league ids; checked against its standings on 2026-10-06)
ORDER = {135: "h2h", 136: "h2h", 235: "h2h", 312: "h2h", 333: "h2h", 419: "h2h",    # Italy, Russia, Andorra, Ukraine, Azerbaijan
         144: "wins", 253: "wins"}                                                  # Belgium, MLS
FIELDS = ["group", "rank", "team", "played", "win", "draw", "lose", "gf", "ga", "gd", "points", "form", "description"]


def adjustments(league_id, season, path=PATH):
    """{"points": {team: points}, "void": {teams}} for one competition's season."""
    try:
        entry = json.loads(Path(path).read_text(encoding="utf-8")).get(f"{league_id}:{season}", {})
    except FileNotFoundError:
        entry = {}
    return {"points": {int(t): int(n) for t, n in entry.get("points", {}).items()},
            "void": {int(t) for t in entry.get("void", [])}}


def _stage(round_name):
    """("Regular Season", numbered?) of "Regular Season - 12"."""
    stage, _, rest = (round_name or "").partition(" - ")
    return stage, not rest or rest.strip().isdigit()


def group_rounds(groups, stages, cup=False):
    """{group: test(round name) -> whether its matches count for the group}. groups:
    {group: {teams}}; stages: the stage names among the competition's fixtures."""
    overlap = len({t for teams in groups.values() for t in teams}) < sum(len(t) for t in groups.values())
    biggest = max(groups, key=lambda g: len(groups[g])) if groups else None
    out = {}
    for group in groups:
        named = [s for s in stages if s and (group or "").startswith(s)]
        if named:
            out[group] = lambda r, named=named: _stage(r)[0] in named and _stage(r)[1]
        elif cup or any(s in stages for s in STAGES):
            out[group] = lambda r: _stage(r)[0] in STAGES
        elif REGULAR in stages and (not overlap or group == biggest):
            out[group] = lambda r: _stage(r)[0] == REGULAR
        else:
            out[group] = lambda r: True
    return out


def _head_to_head(level, played, counts):
    """{team: (points, goal difference)} in the counted matches among the level clubs."""
    out = {t: [0, 0] for t in level}
    for _, rnd, home, away, hg, ag in played:
        if home in out and away in out and counts(rnd):
            out[home][0] += 3 if hg > ag else 1 if hg == ag else 0
            out[away][0] += 3 if ag > hg else 1 if hg == ag else 0
            out[home][1] += hg - ag
            out[away][1] += ag - hg
    return {t: tuple(v) for t, v in out.items()}


def league_table(standing, fixtures, adjust=None, names=None, order=None, cup=False):
    """A competition's table rows (FIELDS order), every group, each in finishing order.

    standing: API-Football's rows as (group, team, rank, description), used for the groups'
    members and for what each place leads to. fixtures: the season's finished matches as
    (kickoff, round, home, away, home goals, away goals), any order. adjust: adjustments().
    names: {team: name}, to order clubs level on everything else. order: the competition's
    ORDER entry. cup: the competition is a cup (leagues.type)."""
    adjust = adjust or {"points": {}, "void": set()}
    names = names or {}
    groups, place = defaultdict(set), {}
    for group, team, rank, description in standing:
        groups[group].add(team)
        place[(group, rank)] = description
    counts = group_rounds(groups, {_stage(f[1])[0] for f in fixtures}, cup)
    played = sorted((f for f in fixtures if f[4] is not None and f[5] is not None
                     and f[2] not in adjust["void"] and f[3] not in adjust["void"]), key=lambda f: f[0])
    rows = []
    for group, teams in groups.items():
        tally = {t: [0, 0, 0, 0, 0, 0, ""] for t in teams}      # played, W, D, L, for, against, form
        for _, rnd, home, away, hg, ag in played:
            if not counts[group](rnd):
                continue
            for team, scored, conceded in ((home, hg, ag), (away, ag, hg)):
                if team in tally:
                    x = tally[team]
                    x[0] += 1
                    x[1] += scored > conceded
                    x[2] += scored == conceded
                    x[3] += scored < conceded
                    x[4] += scored
                    x[5] += conceded
                    x[6] = (("W" if scored > conceded else "D" if scored == conceded else "L") + x[6])[:FORM_GAMES]
        points = {t: 3 * x[1] + x[2] + adjust["points"].get(t, 0) for t, x in tally.items()}
        between = {}
        if order == "h2h":
            level = defaultdict(list)
            for t in teams:
                level[points[t]].append(t)
            for tied in level.values():
                if len(tied) > 1:
                    between.update(_head_to_head(tied, played, counts[group]))
        ranked = sorted(teams, key=lambda t: (
            -points[t], *(-v for v in between.get(t, (0, 0))), -tally[t][1] if order == "wins" else 0,
            -(tally[t][4] - tally[t][5]), -tally[t][4], str(names.get(t, "")), t))
        for i, team in enumerate(ranked):
            n, w, d, l, gf, ga, form = tally[team]
            rows.append([group, i + 1, team, n, w, d, l, gf, ga, gf - ga, points[team], form or None,
                         place.get((group, i + 1))])
    rows.sort(key=lambda r: (r[0] or "", r[1]))
    return rows


def differences(computed, feed):
    """Where a computed table disagrees with API-Football's on played, won, drawn, lost, goals or
    points: [(group, team, computed, API-Football's)]. feed: rows as (group, team, played, win,
    draw, lose, goals for, against, points)."""
    ours = {(r[0], r[2]): (r[3], r[4], r[5], r[6], r[7], r[8], r[10]) for r in computed}
    return [(g, t, ours.get((g, t)), tuple(rest)) for g, t, *rest in feed if ours.get((g, t)) != tuple(rest)]
