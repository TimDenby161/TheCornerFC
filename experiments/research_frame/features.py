"""Pre-match features for every fixture, built in one pass in kickoff order so that each one
uses only matches that kicked off before it. Shared by the architecture experiment and the
market analysis. Needs numpy; reads the research frame only.

Groups (the names are used for ablations):

    form       how each side has done against the model lately (goal-difference and total-goals
               residuals over its last 5 and 10 matches) and the gap between its current and
               long-term rank
    shots_xg   xG and shots over each side's last 10 matches with statistics: xG difference
               minus goal difference ("luck"), shot, on-target and in-box shot differences
    schedule   days since each side's last match and its matches in the last 14 and 30 days
               (matches in this database only: friendlies and uncovered cups are not seen)
    movers     whether each side changed division, which way, and its league matches since
    manager    matches since each side's manager last changed, from the manager named on its
               earlier line-ups (never this match's)
    injuries   the stored missing-player strength of each side
    venue      the home side's recent residual at home and the away side's away
"""
from collections import defaultdict, deque

import numpy as np

GROUPS = {
    "form": ["h_res5", "a_res5", "h_res10", "a_res10", "h_tot5", "a_tot5", "h_momentum", "a_momentum"],
    "shots_xg": ["h_luck10", "a_luck10", "h_shots10", "a_shots10", "h_sot10", "a_sot10", "h_box10", "a_box10",
                 "h_xgd10", "a_xgd10"],
    "schedule": ["h_rest", "a_rest", "h_last14", "a_last14", "h_last30", "a_last30"],
    "movers": ["h_moved", "a_moved", "h_since_move", "a_since_move"],
    "manager": ["h_manager_matches", "a_manager_matches"],
    "injuries": ["home_missing", "away_missing"],
    "venue": ["h_home_res10", "a_away_res10"],
}
BASE = ["exp_diff", "pred_total", "rank_gap", "least_played", "is_league", "is_europe", "level", "month"]
LEAGUE_WINDOW = 400


def _mean(dq, k):
    if len(dq) < min(k, 3):
        return np.nan
    vals = list(dq)[-k:]
    return sum(vals) / len(vals)


def build(data, rep, home_xg, away_xg):
    """{name: array over fixtures}. rep is the production replay; home_xg / away_xg the
    projected goals the residuals are measured against (the replayed baseline)."""
    n = data.n
    f = {name: np.full(n, np.nan) for names in GROUPS.values() for name in names}
    exp = home_xg - away_xg
    resid = (data.ft_home - data.ft_away) - exp
    tot = (data.ft_home + data.ft_away) - (home_xg + away_xg)
    scored = ~np.isnan(resid)
    res, totals = defaultdict(lambda: deque(maxlen=10)), defaultdict(lambda: deque(maxlen=10))
    luck, shots, sot, box, xgd = (defaultdict(lambda: deque(maxlen=10)) for _ in range(5))
    at_home, at_away = defaultdict(lambda: deque(maxlen=10)), defaultdict(lambda: deque(maxlen=10))
    dates = defaultdict(lambda: deque(maxlen=12))
    league_of, seen_on, since, direction = {}, {}, {}, {}
    coach, coach_matches = {}, {}
    coach_at = {}
    fc = data.doc["formations"]["rows"]
    for fixture_id, team_id, _, coach_id in fc:
        if coach_id is not None:
            coach_at[(fixture_id, team_id)] = coach_id

    for i in range(n):
        th, ta, day = data.home[i], data.away[i], data.ordinal[i]
        for side, t in (("h", th), ("a", ta)):
            f[f"{side}_res5"][i], f[f"{side}_res10"][i] = _mean(res[t], 5), _mean(res[t], 10)
            f[f"{side}_tot5"][i] = _mean(totals[t], 5)
            f[f"{side}_luck10"][i], f[f"{side}_shots10"][i] = _mean(luck[t], 10), _mean(shots[t], 10)
            f[f"{side}_sot10"][i], f[f"{side}_box10"][i] = _mean(sot[t], 10), _mean(box[t], 10)
            f[f"{side}_xgd10"][i] = _mean(xgd[t], 10)
            past = dates[t]
            if past:
                f[f"{side}_rest"][i] = min(day - past[-1], 60)
            f[f"{side}_last14"][i] = sum(day - p <= 14 for p in past)
            f[f"{side}_last30"][i] = sum(day - p <= 30 for p in past)
            f[f"{side}_manager_matches"][i] = coach_matches.get(t, np.nan)
        f["h_home_res10"][i], f["a_away_res10"][i] = _mean(at_home[th], 10), _mean(at_away[ta], 10)
        if data.is_league[i]:
            here = data.league[i]
            for side, t in (("h", th), ("a", ta)):
                was = league_of.get(t)
                if was != here:
                    gap = 0.0
                    if was is not None and day - seen_on[t] <= LEAGUE_WINDOW \
                            and data.leagues[was]["country"] == data.leagues[here]["country"]:
                        a, b = data.leagues[here]["starting_rank"], data.leagues[was]["starting_rank"]
                        gap = (a - b) if a is not None and b is not None else 0.0
                    direction[t], since[t] = float(np.sign(gap)), 0
                    league_of[t] = here
                f[f"{side}_moved"][i] = direction.get(t, 0.0) if since.get(t, 99) < 20 else 0.0
                f[f"{side}_since_move"][i] = min(since.get(t, 99), 40)
                since[t] = since.get(t, 0) + 1
                seen_on[t] = day
        # after the match: update every running record
        if scored[i]:
            res[th].append(resid[i]); res[ta].append(-resid[i])
            totals[th].append(tot[i]); totals[ta].append(tot[i])
            at_home[th].append(resid[i]); at_away[ta].append(-resid[i])
        gd = data.home_goals[i] - data.away_goals[i]
        if not np.isnan(data.home_xg[i]) and not np.isnan(data.away_xg[i]):
            x = data.home_xg[i] - data.away_xg[i]
            luck[th].append(gd - x); luck[ta].append(x - gd)
            xgd[th].append(x); xgd[ta].append(-x)
        for store, hv, av in ((shots, data.home_shots[i], data.away_shots[i]), (sot, data.home_sot[i], data.away_sot[i]),
                              (box, data.home_box[i], data.away_box[i])):
            if not np.isnan(hv) and not np.isnan(av):
                store[th].append(hv - av); store[ta].append(av - hv)
        for t in (th, ta):
            dates[t].append(day)
            now = coach_at.get((data.fixture_id[i], t))
            if now is not None:
                if coach.get(t) is not None and coach[t] != now:
                    coach_matches[t] = 0
                elif t in coach_matches:
                    coach_matches[t] = min(coach_matches[t] + 1, 60)
                elif coach.get(t) is not None:
                    coach_matches[t] = 60        # first seen with the same manager twice: settled
                coach[t] = now

    h, a = rep.match_rank()
    f["h_momentum"], f["a_momentum"] = rep.h_now - rep.h_lt, rep.a_now - rep.a_lt
    f["exp_diff"], f["pred_total"] = exp, home_xg + away_xg
    f["rank_gap"] = h - a
    f["least_played"] = np.minimum(np.minimum(rep.h_played, rep.a_played), 150).astype(float)
    f["is_league"] = data.is_league.astype(float)
    f["is_europe"] = np.isin(data.league, [2, 3, 848]).astype(float)
    f["level"] = np.array([data.leagues[l]["starting_rank"] or np.nan for l in data.league], dtype=float)
    f["month"] = np.array([int(d[5:7]) for d in data.day], dtype=float)
    f["home_missing"], f["away_missing"] = data.pred["home_missing"], data.pred["away_missing"]
    return f
