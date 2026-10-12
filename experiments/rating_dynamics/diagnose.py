"""Rating dynamics: diagnostics on the development period (2021-07-01 to 2024-06-30) only.

Exploratory. It looks for where the club rank is structurally wrong, to decide which changes
are worth registering (DESIGN.md). No outcome in the final period (from 2024-07-01) is read
for any error measure here; the one table that spans every season (league levels) uses ranks
only, not prediction errors.

    python experiments/rating_dynamics/diagnose.py      # needs numpy; reads the research frame
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_frame"))
import frame  # noqa: E402

OUT = Path(__file__).parent / "diagnostics.json"
WINDOW_DAYS = 400


def se_mean(x):
    x = np.asarray(x, float)
    return (float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x))), int(len(x))) if len(x) > 1 else (None, None, len(x))


def slope(x, y, clusters=None):
    """OLS slope of y on x with a week-clustered standard error."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    xc = x - x.mean()
    b = float((xc * (y - y.mean())).sum() / (xc ** 2).sum())
    resid = y - y.mean() - b * xc
    if clusters is None:
        se = float(np.sqrt((resid ** 2).sum() / (len(x) - 2) / (xc ** 2).sum()))
    else:
        _, sums, _ = frame.cluster_sums(xc * resid, clusters)
        se = float(np.sqrt((sums[:, 0] ** 2).sum()) / (xc ** 2).sum())
    return {"slope": b, "se": se, "n": int(len(x))}


def main():
    d = frame.Data()
    rep = frame.replay(d)
    dev = d.development
    exp = d.pred["home_xg"] - d.pred["away_xg"]
    resid = (d.ft_home - d.ft_away) - exp                      # + : home did better than predicted
    tot_resid = (d.ft_home + d.ft_away) - (d.pred["home_xg"] + d.pred["away_xg"])
    p = np.full((d.n, 3), np.nan)
    p[d.scored] = frame.baseline_probabilities(d, d.scored)
    ll = np.full(d.n, np.nan)
    ll[d.scored] = frame.log_loss(p[d.scored], d.result[d.scored])
    out = {"development_matches": int(dev.sum())}

    # ---- each side's league going into each match, and what kind of match it is ---------------
    last_league = {}                      # team -> (ordinal, league)
    seen_leagues = defaultdict(list)      # team -> [league of each league match so far]
    h_lg, a_lg = np.full(d.n, -1), np.full(d.n, -1)
    h_new, a_new = np.zeros(d.n, int), np.zeros(d.n, int)       # league matches since joining this league
    h_dir, a_dir = np.zeros(d.n), np.zeros(d.n)                 # + came up, - came down (starting-rank gap)
    since_join, direction = {}, {}
    days_rest_h, days_rest_a = np.full(d.n, np.nan), np.full(d.n, np.nan)
    last_played = {}
    for i in range(d.n):
        for side, team in ((0, d.home[i]), (1, d.away[i])):
            seen = last_league.get(team)
            lg = seen[1] if seen and d.ordinal[i] - seen[0] <= WINDOW_DAYS else -1
            (h_lg if side == 0 else a_lg)[i] = lg
            if team in last_played:
                (days_rest_h if side == 0 else days_rest_a)[i] = d.ordinal[i] - last_played[team]
            if d.is_league[i]:
                here = d.league[i]
                if lg != here:
                    since_join[team] = 0
                    gap = 0.0
                    if lg != -1 and d.leagues[lg]["country"] == d.leagues[here]["country"]:
                        a, b = d.leagues[here]["starting_rank"], d.leagues[lg]["starting_rank"]
                        gap = (a - b) if a is not None and b is not None else 0.0
                    direction[team] = gap
                (h_new if side == 0 else a_new)[i] = since_join.get(team, 0)
                (h_dir if side == 0 else a_dir)[i] = direction.get(team, 0.0)
        if d.is_league[i]:
            for team in (d.home[i], d.away[i]):
                last_league[team] = (d.ordinal[i], d.league[i])
                since_join[team] = since_join.get(team, 0) + 1
        for team in (d.home[i], d.away[i]):
            last_played[team] = d.ordinal[i]

    cross = ~d.is_league & (h_lg != -1) & (a_lg != -1) & (h_lg != a_lg)
    one_sided = ~d.is_league & ((h_lg == -1) != (a_lg == -1))
    same = ~d.is_league & ~cross & ~one_sided
    kinds = {"league": d.is_league, "cup, sides from different leagues": cross,
             "cup, one side with no league": one_sided, "cup, other": same}
    out["by_kind"] = {}
    for name, m in kinds.items():
        m = m & dev
        out["by_kind"][name] = {"n": int(m.sum()), "log_loss": float(ll[m].mean()),
                                "abs_goal_error": float(np.abs(resid[m]).mean()),
                                "sharpness_power": frame.calibration_slope(p[m], d.result[m])}

    # ---- 1. league levels: are whole leagues misplaced, and does the error persist? -------------
    # In cross-league cup ties, residual ~ off[home league] - off[away league]. Fit the offsets
    # by ridge regression one season at a time and ask whether a season's offsets predict the next.
    def fit_offsets(mask, ridge=20.0):
        idx = np.where(mask)[0]
        leagues = sorted(set(h_lg[idx]) | set(a_lg[idx]))
        pos = {lg: j for j, lg in enumerate(leagues)}
        X = np.zeros((len(idx), len(leagues)))
        for r, i in enumerate(idx):
            X[r, pos[h_lg[i]]] += 1
            X[r, pos[a_lg[i]]] -= 1
        beta = np.linalg.solve(X.T @ X + ridge * np.eye(len(leagues)), X.T @ resid[idx])
        counts = np.abs(X).sum(axis=0)
        return {lg: (beta[j], counts[j]) for lg, j in pos.items()}

    seasons = [2021, 2022, 2023]
    offsets = {s: fit_offsets(cross & dev & (d.season == s)) for s in seasons}
    out["league_offsets"] = {}
    for s in seasons:
        top = sorted(offsets[s].items(), key=lambda kv: -abs(kv[1][0]))[:8]
        out["league_offsets"][d.season_label(s)] = [
            {"league": d.leagues[lg]["name"], "country": d.leagues[lg]["country"],
             "goals": round(float(b), 3), "matches": int(n)} for lg, (b, n) in top]
    persistence = {}
    for s0, s1 in ((2021, 2022), (2022, 2023)):
        common = [lg for lg in offsets[s0] if lg in offsets[s1] and offsets[s0][lg][1] >= 15 and offsets[s1][lg][1] >= 15]
        x = np.array([offsets[s0][lg][0] for lg in common])
        y = np.array([offsets[s1][lg][0] for lg in common])
        persistence[f"{d.season_label(s0)} to {d.season_label(s1)}"] = {
            "leagues": len(common), "correlation": float(np.corrcoef(x, y)[0, 1])}
        # out of sample: correct next season's cross-league margins by this season's offsets
        m = cross & dev & (d.season == s1)
        corr = np.array([offsets[s0].get(h_lg[i], (0, 0))[0] - offsets[s0].get(a_lg[i], (0, 0))[0] for i in np.where(m)[0]])
        r = resid[m]
        persistence[f"{d.season_label(s0)} to {d.season_label(s1)}"].update({
            "next_season_matches": int(m.sum()),
            "mse_before": float((r ** 2).mean()), "mse_after": float(((r - corr) ** 2).mean()),
            "slope_of_residual_on_correction": slope(corr, r, d.week[m])})
    out["league_offset_persistence"] = persistence

    # higher-league side's residual by season (the level_gaps finding), development seasons only
    gap = np.array([(d.leagues[h]["starting_rank"] or np.nan) - (d.leagues[a]["starting_rank"] or np.nan)
                    if h != -1 and a != -1 else np.nan for h, a in zip(h_lg, a_lg)], dtype=float)
    out["higher_league_side_residual"] = {}
    for s in seasons:
        m = cross & dev & (d.season == s) & (np.abs(gap) > 0)
        out["higher_league_side_residual"][d.season_label(s)] = se_mean(np.sign(gap[m]) * resid[m])
    # the same by how the two leagues are related
    europe = np.isin(d.league, [2, 3, 848])
    for label, m0 in (("European competitions", europe), ("domestic cups", ~europe)):
        for s in seasons:
            m = cross & dev & (d.season == s) & (np.abs(gap) > 0) & m0
            out["higher_league_side_residual"][f"{label} {d.season_label(s)}"] = se_mean(np.sign(gap[m]) * resid[m])

    # league mean rank by season (ranks only; every season) for the bigger leagues
    levels = defaultdict(lambda: defaultdict(list))
    for i in np.where(d.is_league)[0]:
        levels[d.league[i]][d.season[i]].append((rep.h_now[i] + rep.a_now[i]) / 2)
    table = {}
    for lg in (39, 40, 41, 42, 140, 135, 78, 61, 88, 94, 203, 253, 179, 144):
        if lg in levels:
            table[d.leagues[lg]["name"] + " (" + d.leagues[lg]["country"] + ")"] = {
                "starting_rank": d.leagues[lg]["starting_rank"],
                **{d.season_label(s): round(float(np.mean(v)), 1) for s, v in sorted(levels[lg].items()) if len(v) > 50}}
    out["league_mean_rank_by_season"] = table

    # ---- 2. clubs that changed league -----------------------------------------------------------
    team_resid = np.concatenate([resid, -resid])               # + : the side did better than predicted
    team_new = np.concatenate([h_new, a_new])
    team_dir = np.concatenate([h_dir, a_dir])
    both = np.concatenate([dev & d.is_league, dev & d.is_league])
    weeks2 = np.concatenate([d.week, d.week])
    out["changed_league"] = {}
    for label, sel in (("came up", team_dir > 0), ("came down", team_dir < 0)):
        for lo, hi in ((0, 5), (5, 10), (10, 20), (20, 46)):
            m = both & sel & (team_new >= lo) & (team_new < hi)
            out["changed_league"][f"{label}, league matches {lo + 1} to {hi}"] = se_mean(team_resid[m])

    # ---- 3. does the rank react too slowly or too fast? -----------------------------------------
    # For each side, the mean of its residuals over its previous 5 matches against its residual
    # now. A positive slope: the rank under-reacts (errors repeat). Negative: it over-reacts.
    recent = defaultdict(list)
    prev5_h, prev5_a = np.full(d.n, np.nan), np.full(d.n, np.nan)
    prev_tot_h, prev_tot_a = np.full(d.n, np.nan), np.full(d.n, np.nan)
    recent_tot = defaultdict(list)
    last_kind_change = {}
    after_cup_h, after_cup_a = np.full(d.n, np.nan), np.full(d.n, np.nan)
    after_lge_h, after_lge_a = np.full(d.n, np.nan), np.full(d.n, np.nan)
    has = ~np.isnan(resid)
    for i in range(d.n):
        th, ta = d.home[i], d.away[i]
        if len(recent[th]) >= 5:
            prev5_h[i] = np.mean(recent[th][-5:])
            prev_tot_h[i] = np.mean(recent_tot[th][-5:])
        if len(recent[ta]) >= 5:
            prev5_a[i] = np.mean(recent[ta][-5:])
            prev_tot_a[i] = np.mean(recent_tot[ta][-5:])
        for team, arr_c, arr_l in ((th, after_cup_h, after_lge_h), (ta, after_cup_a, after_lge_a)):
            if team in last_kind_change:
                was_cup, value = last_kind_change[team]
                (arr_c if was_cup else arr_l)[i] = value
        if has[i]:
            recent[th].append(resid[i]); recent[ta].append(-resid[i])
            recent_tot[th].append(tot_resid[i]); recent_tot[ta].append(tot_resid[i])
            last_kind_change[th] = (not d.is_league[i], resid[i])
            last_kind_change[ta] = (not d.is_league[i], -resid[i])
    x = np.concatenate([prev5_h, prev5_a])
    out["reaction"] = {}
    xg_match = ~np.isnan(d.home_xg)
    month = np.array([int(k[5:7]) for k in d.day])
    groups = {"all league matches": d.is_league, "leagues with xG": d.is_league & xg_match,
              "leagues without xG": d.is_league & ~xg_match,
              "league matches, August and September": d.is_league & np.isin(month, [8, 9]),
              "league matches, other months": d.is_league & ~np.isin(month, [8, 9]),
              "cup matches": ~d.is_league}
    for name, g in groups.items():
        m = np.concatenate([g & dev, g & dev]) & ~np.isnan(x)
        out["reaction"][name] = slope(x[m], team_resid[m], weeks2[m])
    xt = np.concatenate([prev_tot_h, prev_tot_a])
    tr = np.concatenate([tot_resid, tot_resid])
    m = np.concatenate([d.is_league & dev] * 2) & ~np.isnan(xt)
    out["reaction"]["total goals, league matches"] = slope(xt[m], tr[m], weeks2[m])

    # ---- 4. do cup results mislead the rank? ----------------------------------------------------
    # The side's residual in its previous match against its residual in this league match, by
    # whether the previous match was a cup tie. If cup results are noisier information the slope
    # after a cup tie is lower than after a league match.
    lge2 = np.concatenate([d.is_league & dev] * 2)
    for label, arr in (("after a cup match", np.concatenate([after_cup_h, after_cup_a])),
                       ("after a league match", np.concatenate([after_lge_h, after_lge_a]))):
        m = lge2 & ~np.isnan(arr)
        out.setdefault("cup_distortion", {})[label] = slope(arr[m], team_resid[m], weeks2[m])

    # ---- 5. uncertainty: are sides with little history predicted worse? -------------------------
    out["by_matches_played"] = {}
    least = np.minimum(rep.h_played, rep.a_played)
    for lo, hi in ((0, 10), (10, 30), (30, 60), (60, 120), (120, 10 ** 6)):
        m = dev & (least >= lo) & (least < hi)
        if m.sum() > 100:
            out["by_matches_played"][f"{lo} to {hi if hi < 10 ** 6 else 'up'}"] = {
                "n": int(m.sum()), "log_loss": float(ll[m].mean()),
                "sharpness_power": frame.calibration_slope(p[m], d.result[m]),
                "goal_error_sd": float(resid[m].std())}
    rest = np.concatenate([days_rest_h, days_rest_a])
    out["after_a_break"] = {}
    for lo, hi in ((0, 15), (15, 40), (40, 80), (80, 400)):
        m = np.concatenate([dev] * 2) & (rest >= lo) & (rest < hi)
        # is the side's rank less sure after a break? the residual's spread, and whether stronger
        # sides (rank above the opponent's) do worse after it (regression to the mean)
        fav = np.concatenate([np.sign(exp), -np.sign(exp)])
        out["after_a_break"][f"{lo} to {hi} days"] = {"n": int(m.sum()), "goal_error_sd": float(team_resid[m].std()),
                                                      "favourite_residual": se_mean((fav * team_resid)[m])}

    # ---- 6. season to season: should ranks be pulled to the league average over the summer? -----
    # A side's rank above its league's average at its first league match of a season, against
    # its mean residual over its first 10 league matches of that season.
    first10 = defaultdict(list)
    rank_gap = {}
    league_mean = {}
    for s in seasons:
        for lg in np.unique(d.league[d.is_league & (d.season == s)]):
            m = d.is_league & (d.season == s) & (d.league == lg)
            idx = np.where(m)[0]
            first = {}
            for i in idx:
                for team, r in ((d.home[i], rep.h_now[i]), (d.away[i], rep.a_now[i])):
                    first.setdefault(team, r)
            mean = np.mean(list(first.values()))
            for team, r in first.items():
                rank_gap[(s, team)] = r - mean
            count = defaultdict(int)
            for i in idx:
                if not dev[i]:
                    continue
                for team, sign in ((d.home[i], 1), (d.away[i], -1)):
                    if count[team] < 10:
                        first10[(s, team)].append(sign * resid[i])
                        count[team] += 1
    keys = [k for k, v in first10.items() if len(v) >= 8]
    x = np.array([rank_gap[k] for k in keys]) / 100
    y = np.array([np.mean(first10[k]) for k in keys])
    out["summer_regression"] = slope(x, y)

    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
