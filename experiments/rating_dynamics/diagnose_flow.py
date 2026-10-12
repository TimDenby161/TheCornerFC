"""Rating dynamics: where do a league's rank points come from? Development seasons only.

The rank is zero-sum inside a match, so a league's average can only move through matches
against clubs outside it and through clubs joining or leaving. This adds up each league's
gains by source, per club per season, and splits the changed-league error by season.

    python experiments/rating_dynamics/diagnose_flow.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_frame"))
import frame  # noqa: E402

OUT = Path(__file__).parent / "diagnostics_flow.json"


def main():
    d = frame.Data()
    rep = frame.replay(d)
    s = frame.PRODUCTION
    exp = (rep.h_now - rep.a_now + s["home_advantage"]) / 100
    capped = np.clip(d.home_goals - d.away_goals, -3, 3)
    has_xg = ~np.isnan(d.home_xg) & ~np.isnan(d.away_xg)
    result = np.where(has_xg, 0.3 * capped + 0.7 * (d.home_xg - d.away_xg), capped)
    k = np.where(has_xg, s["k_xg"], s["k"]) * np.array([frame.COMPETITION_WEIGHT.get(l, 1.0) for l in d.league])
    change = (result - exp) * k                               # home side's rank change

    last = {}
    flows = defaultdict(lambda: defaultdict(float))            # (league, season) -> source -> points
    clubs = defaultdict(set)
    europe = {2, 3, 848}
    in_dev = (d.day < frame.DEVELOPMENT_END)
    resid = (d.ft_home - d.ft_away) - (d.pred["home_xg"] - d.pred["away_xg"])
    moved = defaultdict(list)
    prev_league, joined, direction = {}, {}, {}
    for i in range(d.n):
        sides = []
        for team in (d.home[i], d.away[i]):
            seen = last.get(team)
            sides.append(seen[1] if seen and d.ordinal[i] - seen[0] <= 400 else -1)
        if in_dev[i] and not d.is_league[i]:
            h, a = sides
            if h != a:
                if d.league[i] in europe:
                    source = "European competitions"
                elif h == -1 or a == -1:
                    source = "cups, against a club with no league"
                else:
                    source = "cups, against a club from another league"
                if h != -1:
                    flows[(h, d.season[i])][source] += change[i]
                if a != -1:
                    flows[(a, d.season[i])][source] -= change[i]
        if d.is_league[i]:
            lg = d.league[i]
            for side, team in ((0, d.home[i]), (1, d.away[i])):
                was = sides[side]
                if was != lg:
                    joined[team] = 0
                    gap = 0.0
                    if was != -1 and d.leagues[was]["country"] == d.leagues[lg]["country"]:
                        a, b = d.leagues[lg]["starting_rank"], d.leagues[was]["starting_rank"]
                        gap = (a - b) if a is not None and b is not None else 0.0
                    direction[team] = (gap, was)
                n = joined.get(team, 99)
                gap, was = direction.get(team, (0.0, -1))
                if d.development[i] and gap != 0 and n < 10:
                    sign = 1 if side == 0 else -1
                    top = max(d.leagues[was]["starting_rank"], d.leagues[lg]["starting_rank"])
                    moved[("up" if gap > 0 else "down", int(d.season[i]),
                           "top two English levels" if top >= 1100 else "elsewhere")].append(sign * resid[i])
                joined[team] = n + 1
                clubs[(lg, d.season[i])].add(team)
                last[team] = (d.ordinal[i], lg)

    out = {"points_per_club_per_season": {}, "changed_league_first_10_matches": {}}
    names = {39: "Premier League", 40: "Championship", 41: "League One", 42: "League Two", 140: "La Liga",
             135: "Serie A", 78: "Bundesliga", 61: "Ligue 1", 88: "Eredivisie", 179: "Premiership (Scotland)",
             144: "Jupiler Pro League", 203: "Super Lig", 94: "Primeira Liga"}
    for lg, name in names.items():
        for season in (2020, 2021, 2022, 2023):
            n = len(clubs.get((lg, season), ()))
            if n:
                out["points_per_club_per_season"][f"{name} {d.season_label(season)}"] = {
                    src: round(v / n, 1) for src, v in sorted(flows[(lg, season)].items())}
    # every league together: total points entering covered leagues by source, per season
    total = defaultdict(lambda: defaultdict(float))
    members = defaultdict(int)
    for (lg, season), srcs in flows.items():
        for src, v in srcs.items():
            total[season][src] += v
    for (lg, season), teams in clubs.items():
        members[season] += len(teams)
    out["all_leagues_points_per_club"] = {d.season_label(se): {src: round(v / members[se], 2) for src, v in sorted(srcs.items())}
                                          for se, srcs in sorted(total.items()) if members[se]}
    for key, v in sorted(moved.items()):
        v = np.array(v)
        out["changed_league_first_10_matches"][f"{key[0]}, {d.season_label(key[1])}, {key[2]}"] = [
            round(float(v.mean()), 3), round(float(v.std(ddof=1) / np.sqrt(len(v))), 3), len(v)]
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
