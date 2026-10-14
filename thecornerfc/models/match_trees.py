"""A18: boosted trees correcting the base match model's projected goals, run beside it every time
the predictions are made (MC-0029, experiments/challenger/DESIGN.md; protocol P18).

The recipe is A18's as experiments/architectures fixed it (`gb` and `dc` in its chosen.json) and
experiments/a18_on_release refitted it on the released club rank: on 2024-07 to 2026-10, log loss
0.0019 better than the base model (95% 0.0012 to 0.0025).

    features   44 pre-match figures per fixture, each from matches that kicked off before it:
               the projections and ranks; each side's recent results against the base model;
               xG, shots and luck over its last 10 matches; rest and fixture load; a change of
               division; matches under its manager; missing players; home and away form; and
               the weekly Poisson model's margin and total against the base model's
    Poisson    a hierarchical Poisson model of goals (club, league-or-country and competition
               terms), refitted every REFIT_DAYS days on the matches before, each fit starting
               from the last
    trees      two gradient-boosted regressions, of the base model's margin error and total
               error, trained on every scored match before the half-season (1 January, 1 July)
               the fixture is in
    a18        the base model's projected goals with the margin moved and the total scaled by
               the trees' corrections, then production's probability step

Every part is a port of the research code (research_frame/features.py, architectures/run.py),
checked against it on every fixture of the research inputs before release
(tests/test_match_trees.py holds the small checks). Needs numpy, scipy and scikit-learn, imported
only when the model runs.

update(conn) runs after predictions.update_predictions in the nightly and match-day jobs. It
writes both models' predictions for each upcoming fixture to challenger_predictions, and when
the switch (match_model_switch) names 'a18' it writes a18's over base's in fixture_predictions.
The prospective snapshots stay the base model's.
"""
import logging
import math
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone

from .. import config
from ..pipeline.cache import cached_rows, rank_history, WEEK

log = logging.getLogger(__name__)

MODELS = ("base", "a18")
# The recipe (experiments/architectures/chosen.json), fixed
FEATURES = (
    "exp_diff", "pred_total", "rank_gap", "least_played", "is_league", "is_europe", "level", "month",
    "h_res5", "a_res5", "h_res10", "a_res10", "h_tot5", "a_tot5", "h_momentum", "a_momentum",
    "h_luck10", "a_luck10", "h_shots10", "a_shots10", "h_sot10", "a_sot10", "h_box10", "a_box10",
    "h_xgd10", "a_xgd10", "h_rest", "a_rest", "h_last14", "a_last14", "h_last30", "a_last30",
    "h_moved", "a_moved", "h_since_move", "a_since_move", "h_manager_matches", "a_manager_matches",
    "home_missing", "away_missing", "h_home_res10", "a_away_res10", "dc_margin", "dc_total")
TREES = dict(max_depth=3, max_iter=300, learning_rate=0.03, min_samples_leaf=200, l2_regularization=1.0,
             random_state=20261012)
SHRINK = 1.0
SCALE_LIMITS = (0.7, 1.4)              # the total is never scaled further than this
POISSON = dict(half_life=250.0, ridge_team=10.0, use_xg=1)
RIDGE_LEAGUE, RIDGE_GOALS, RIDGE_HOME = 2.0, 100.0, 400.0
REFIT_DAYS = 7
FIRST_DAY = "2021-07-01"               # the research frame's burn-in end: fits and training start here
NOW_WEIGHT = 0.6                       # the research frame's match rank: 0.6 x current + 0.4 x LT ALGO
HOME_ADVANTAGE = 30.0
LEAGUE_WINDOW = 400
EUROPE = (2, 3, 848)


# ---- the matches -----------------------------------------------------------------------------

class Matches:
    """Every fixture as columns, in kickoff order (kickoff, fixture_id): what the research frame's
    Data holds, built from plain rows.

    fixtures: (fixture_id, kickoff as ISO text in UTC, league_id, home, away, status, home goals,
    away goals, 90-minute home, 90-minute away, home xG, away xG, home shots, away shots, home on
    target, away on target, home in the box, away in the box); None for what is not known.
    leagues: {league_id: (country, type, starting_rank)}. coaches: {(fixture_id, team): coach}.
    stored: {fixture_id: (home match rank, away match rank, home xG, away xG, p_home, home missing,
    away missing)}, the base model's projection. ranks: {(fixture_id, is home): (rank before,
    LT ALGO before, matches played before)}, the club rank going into it."""

    def __init__(self, fixtures, leagues, coaches, stored, ranks):
        import numpy as np
        rows = sorted(fixtures, key=lambda r: (r[1], r[0]))
        nan = lambda v: np.nan if v is None else float(v)
        col = lambda i: np.array([nan(r[i]) for r in rows], dtype=float)
        self.n = len(rows)
        self.fixture_id = np.array([r[0] for r in rows])
        self.kickoff = [r[1] for r in rows]
        self.day = np.array([k[:10] for k in self.kickoff])
        self.league = np.array([r[2] for r in rows])
        self.home, self.away = np.array([r[3] for r in rows]), np.array([r[4] for r in rows])
        self.status = np.array([r[5] for r in rows])
        self.home_goals, self.away_goals, self.ft_home, self.ft_away = col(6), col(7), col(8), col(9)
        self.home_xg, self.away_xg = col(10), col(11)
        self.home_shots, self.away_shots, self.home_sot, self.away_sot = col(12), col(13), col(14), col(15)
        self.home_box, self.away_box = col(16), col(17)
        self.leagues = {lg: {"country": c, "type": t, "starting_rank": s} for lg, (c, t, s) in leagues.items()}
        self.is_league = np.array([self.leagues[lg]["type"] == "League" for lg in self.league])
        self.coaches = coaches
        self.ordinal = np.array([date.fromisoformat(d).toordinal() for d in self.day])
        self.index = {f: i for i, f in enumerate(self.fixture_id)}
        names = ("home_rank", "away_rank", "home_xg", "away_xg", "p_home", "home_missing", "away_missing")
        self.pred = {name: np.full(self.n, np.nan) for name in names}
        for fid, values in stored.items():
            i = self.index.get(fid)
            if i is not None:
                for name, v in zip(names, values):
                    if v is not None:
                        self.pred[name][i] = v
        self.h_now, self.a_now, self.h_lt, self.a_lt = (np.full(self.n, np.nan) for _ in range(4))
        self.h_played, self.a_played = np.zeros(self.n, dtype=int), np.zeros(self.n, dtype=int)
        for i, fid in enumerate(self.fixture_id):
            for home, now, lt, played in ((True, self.h_now, self.h_lt, self.h_played), (False, self.a_now, self.a_lt, self.a_played)):
                got = ranks.get((int(fid), home))
                if got is not None:
                    now[i], lt[i], played[i] = got
        # scored: finished in 90 minutes, a regulation score and a stored projection, from FIRST_DAY
        self.scored = ((self.status == "FT") & ~np.isnan(self.ft_home) & ~np.isnan(self.ft_away)
                       & ~np.isnan(self.pred["home_xg"]) & ~np.isnan(self.pred["p_home"]) & (self.day >= FIRST_DAY))

    def match_rank(self):
        return (NOW_WEIGHT * self.h_now + (1 - NOW_WEIGHT) * self.h_lt,
                NOW_WEIGHT * self.a_now + (1 - NOW_WEIGHT) * self.a_lt)


def moved(home_xg, away_xg, by):
    """Projected goals with the margin moved by `by` and the product of the two kept."""
    import numpy as np
    d = home_xg - away_xg + by
    home = (d + np.sqrt(d * d + 4 * home_xg * away_xg)) / 2
    return home, home - d


def reprojected(m):
    """The base model's stored projection of every fixture, its rank term swapped for the club
    rank going into the match (as the research frame does)."""
    h, a = m.match_rank()
    new_gap = (h - a + HOME_ADVANTAGE) / 100
    old_gap = (m.pred["home_rank"] - m.pred["away_rank"] + HOME_ADVANTAGE) / 100
    return moved(m.pred["home_xg"], m.pred["away_xg"], new_gap - old_gap)


# ---- the features ----------------------------------------------------------------------------

def _mean(dq, k):
    if len(dq) < min(k, 3):
        return float("nan")
    vals = list(dq)[-k:]
    return sum(vals) / len(vals)


def features(m, home_xg, away_xg):
    """{name: array over fixtures}, each from matches before the fixture (research_frame/
    features.py). home_xg / away_xg: the base model's projections the residuals are taken from."""
    import numpy as np
    n = m.n
    f = {name: np.full(n, np.nan) for name in FEATURES}
    exp = home_xg - away_xg
    resid = (m.ft_home - m.ft_away) - exp
    tot = (m.ft_home + m.ft_away) - (home_xg + away_xg)
    scored = ~np.isnan(resid)
    res, totals = defaultdict(lambda: deque(maxlen=10)), defaultdict(lambda: deque(maxlen=10))
    luck, shots, sot, box, xgd = (defaultdict(lambda: deque(maxlen=10)) for _ in range(5))
    at_home, at_away = defaultdict(lambda: deque(maxlen=10)), defaultdict(lambda: deque(maxlen=10))
    dates = defaultdict(lambda: deque(maxlen=12))
    league_of, seen_on, since, direction = {}, {}, {}, {}
    coach, coach_matches = {}, {}

    for i in range(n):
        th, ta, day = m.home[i], m.away[i], m.ordinal[i]
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
        if m.is_league[i]:
            here = m.league[i]
            for side, t in (("h", th), ("a", ta)):
                was = league_of.get(t)
                if was != here:
                    gap = 0.0
                    if was is not None and day - seen_on[t] <= LEAGUE_WINDOW \
                            and m.leagues[was]["country"] == m.leagues[here]["country"]:
                        a, b = m.leagues[here]["starting_rank"], m.leagues[was]["starting_rank"]
                        gap = (a - b) if a is not None and b is not None else 0.0
                    direction[t], since[t] = float(np.sign(gap)), 0
                    league_of[t] = here
                f[f"{side}_moved"][i] = direction.get(t, 0.0) if since.get(t, 99) < 20 else 0.0
                f[f"{side}_since_move"][i] = min(since.get(t, 99), 40)
                since[t] = since.get(t, 0) + 1
                seen_on[t] = day
        if scored[i]:
            res[th].append(resid[i]); res[ta].append(-resid[i])
            totals[th].append(tot[i]); totals[ta].append(tot[i])
            at_home[th].append(resid[i]); at_away[ta].append(-resid[i])
        gd = m.home_goals[i] - m.away_goals[i]
        if not np.isnan(m.home_xg[i]) and not np.isnan(m.away_xg[i]):
            x = m.home_xg[i] - m.away_xg[i]
            luck[th].append(gd - x); luck[ta].append(x - gd)
            xgd[th].append(x); xgd[ta].append(-x)
        for store, hv, av in ((shots, m.home_shots[i], m.away_shots[i]), (sot, m.home_sot[i], m.away_sot[i]),
                              (box, m.home_box[i], m.away_box[i])):
            if not np.isnan(hv) and not np.isnan(av):
                store[th].append(hv - av); store[ta].append(av - hv)
        for t in (th, ta):
            dates[t].append(day)
            now = m.coaches.get((m.fixture_id[i], t))
            if now is not None:
                if coach.get(t) is not None and coach[t] != now:
                    coach_matches[t] = 0
                elif t in coach_matches:
                    coach_matches[t] = min(coach_matches[t] + 1, 60)
                elif coach.get(t) is not None:
                    coach_matches[t] = 60
                coach[t] = now

    h, a = m.match_rank()
    f["h_momentum"], f["a_momentum"] = m.h_now - m.h_lt, m.a_now - m.a_lt
    f["exp_diff"], f["pred_total"] = exp, home_xg + away_xg
    f["rank_gap"] = h - a
    f["least_played"] = np.minimum(np.minimum(m.h_played, m.a_played), 150).astype(float)
    f["is_league"] = m.is_league.astype(float)
    f["is_europe"] = np.isin(m.league, EUROPE).astype(float)
    f["level"] = np.array([m.leagues[lg]["starting_rank"] or np.nan for lg in m.league], dtype=float)
    f["month"] = np.array([int(d[5:7]) for d in m.day], dtype=float)
    f["home_missing"], f["away_missing"] = m.pred["home_missing"], m.pred["away_missing"]
    return f


# ---- the weekly Poisson model ----------------------------------------------------------------

class Poisson:
    """Walk-forward fits (architectures/run.py, DC). For each refit day up to `today`, the
    parameters are estimated from matches with a score that kicked off before it, starting from
    the last fit, and used for the fixtures of the next REFIT_DAYS days; fixtures after the last
    refit day use the last fit."""

    def __init__(self, m, half_life, ridge_team, use_xg):
        import numpy as np
        self.d, self.half_life, self.ridge_team = m, half_life, ridge_team
        teams = np.unique(np.concatenate([m.home, m.away]))
        self.team_index = {t: j for j, t in enumerate(teams)}
        self.h = np.array([self.team_index[t] for t in m.home])
        self.a = np.array([self.team_index[t] for t in m.away])
        comps = np.unique(m.league)
        self.comp_index = {c: j for j, c in enumerate(comps)}
        self.c = np.array([self.comp_index[c] for c in m.league])
        self.nt, self.nc = len(teams), len(comps)
        gh = np.where(np.isnan(m.ft_home), m.home_goals, m.ft_home)
        ga = np.where(np.isnan(m.ft_away), m.away_goals, m.ft_away)
        if use_xg:
            has = ~np.isnan(m.home_xg) & ~np.isnan(m.away_xg)
            gh = np.where(has, 0.3 * np.minimum(gh, 5) + 0.7 * m.home_xg, gh)
            ga = np.where(has, 0.3 * np.minimum(ga, 5) + 0.7 * m.away_xg, ga)
        self.yh, self.ya = gh, ga
        self.has_score = ~np.isnan(gh) & ~np.isnan(ga)
        self.groups = {}
        self.group_at = self._group_history()
        self.theta = None

    def _group_history(self):
        m, changes, current = self.d, [], {}

        def group(key):
            return self.groups.setdefault(key, len(self.groups))

        for i in range(m.n):
            for t in (self.h[i], self.a[i]):
                if m.is_league[i]:
                    g = group(("league", int(m.league[i])))
                elif t not in current:
                    g = group(("none", m.leagues[m.league[i]]["country"]))
                else:
                    continue
                if current.get(t) != g:
                    current[t] = g
                    changes.append((m.ordinal[i], t, g))
        return changes

    def run(self, first_day, last_day, today=None):
        """(lam, mu) over fixtures, filled for kickoffs in [first_day, last_day)."""
        import numpy as np
        m = self.d
        lam, mu = np.full(m.n, np.nan), np.full(m.n, np.nan)
        start, stop = date.fromisoformat(first_day).toordinal(), date.fromisoformat(last_day).toordinal()
        last_fit = date.fromisoformat(today).toordinal() if today else stop
        team_group = np.zeros(self.nt, dtype=int)
        seen = np.zeros(self.nt, dtype=bool)
        pos = 0
        for day in range(start, stop, REFIT_DAYS):
            while pos < len(self.group_at) and self.group_at[pos][0] < day:
                _, t, g = self.group_at[pos]
                team_group[t], seen[t] = g, True
                pos += 1
            if day <= last_fit or self.theta is None:
                train = (m.ordinal < day) & (m.ordinal >= day - 4 * self.half_life) & self.has_score
                self._fit(train, day, team_group)
            block = np.where((m.ordinal >= day) & (m.ordinal < min(day + REFIT_DAYS, stop)))[0]
            if len(block):
                grp = team_group.copy()
                for i in block:
                    for t in (self.h[i], self.a[i]):
                        if not seen[t]:
                            key = ("league", int(m.league[i])) if m.is_league[i] else ("none", m.leagues[m.league[i]]["country"])
                            grp[t] = self.groups[key]
                lam[block], mu[block] = self._rates(block, grp)
        return lam, mu

    def _unpack(self, theta):
        nt, nc, ng = self.nt, self.nc, self.ng
        o = 2
        att, dfc = theta[o:o + nt], theta[o + nt:o + 2 * nt]
        o += 2 * nt
        g_att, g_def = theta[o:o + ng], theta[o + ng:o + 2 * ng]
        o += 2 * ng
        return theta[0], theta[1], att, dfc, g_att, g_def, theta[o:o + nc], theta[o + nc:o + 2 * nc]

    def _rates(self, rows, team_group):
        import numpy as np
        c0, home, att, dfc, g_att, g_def, goals, comp_home = self._unpack(self.theta)
        h, a, c = self.h[rows], self.a[rows], self.c[rows]
        gh, ga = team_group[h], team_group[a]
        common = c0 + goals[c]
        lam = np.exp(common + home + comp_home[c] + att[h] + g_att[gh] - dfc[a] - g_def[ga])
        mu = np.exp(common + att[a] + g_att[ga] - dfc[h] - g_def[gh])
        return lam, mu

    def _fit(self, train, day, team_group):
        import numpy as np
        from scipy.optimize import minimize
        rows = np.where(train)[0]
        h, a, c = self.h[rows], self.a[rows], self.c[rows]
        gh, ga = team_group[h], team_group[a]
        yh, ya = self.yh[rows], self.ya[rows]
        w = np.exp(-np.log(2) * (day - self.d.ordinal[rows]) / self.half_life)
        nt, nc = self.nt, self.nc
        self.ng = ng = max(len(self.groups), 1)
        size = 2 + 2 * nt + 2 * ng + 2 * nc
        if self.theta is None or len(self.theta) != size:
            old = self.theta
            self.theta = np.zeros(size)
            self.theta[0], self.theta[1] = np.log(1.2), 0.25
            if old is not None:
                grown = (size - len(old)) // 2
                o = 2 + 2 * nt
                old_ng = ng - grown
                self.theta[:o] = old[:o]
                self.theta[o:o + old_ng] = old[o:o + old_ng]
                self.theta[o + ng:o + ng + old_ng] = old[o + old_ng:o + 2 * old_ng]
                self.theta[o + 2 * ng:] = old[o + 2 * old_ng:]
        rt, rl, rg, rh = self.ridge_team, RIDGE_LEAGUE, RIDGE_GOALS, RIDGE_HOME

        def objective(theta):
            c0, home, att, dfc, g_att, g_def, goals, comp_home = self._unpack(theta)
            common = c0 + goals[c]
            eta_h = common + home + comp_home[c] + att[h] + g_att[gh] - dfc[a] - g_def[ga]
            eta_a = common + att[a] + g_att[ga] - dfc[h] - g_def[gh]
            lh, la = np.exp(eta_h), np.exp(eta_a)
            value = (w * (lh - yh * eta_h + la - ya * eta_a)).sum() + 0.5 * (
                rt * (att @ att + dfc @ dfc) + rl * (g_att @ g_att + g_def @ g_def) + rg * goals @ goals
                + rh * comp_home @ comp_home)
            rh_, ra_ = w * (lh - yh), w * (la - ya)
            grad = np.zeros_like(theta)
            grad[0], grad[1] = rh_.sum() + ra_.sum(), rh_.sum()
            o = 2
            grad[o:o + nt] = np.bincount(h, rh_, nt) + np.bincount(a, ra_, nt) + rt * att
            grad[o + nt:o + 2 * nt] = -np.bincount(a, rh_, nt) - np.bincount(h, ra_, nt) + rt * dfc
            o += 2 * nt
            grad[o:o + ng] = np.bincount(gh, rh_, ng) + np.bincount(ga, ra_, ng) + rl * g_att
            grad[o + ng:o + 2 * ng] = -np.bincount(ga, rh_, ng) - np.bincount(gh, ra_, ng) + rl * g_def
            o += 2 * ng
            grad[o:o + nc] = np.bincount(c, rh_ + ra_, nc) + rg * goals
            grad[o + nc:] = np.bincount(c, rh_, nc) + rh * comp_home
            return value, grad

        res = minimize(objective, self.theta, jac=True, method="L-BFGS-B", options={"maxiter": 200, "maxfun": 250})
        self.theta = res.x


# ---- the trees -------------------------------------------------------------------------------

def half_seasons(first, last):
    """The 1 January and 1 July from `first` (one of them) up to `last`, as ISO days."""
    out, year, month = [], int(first[:4]), int(first[5:7])
    while f"{year}-{month:02d}-01" <= last:
        out.append(f"{year}-{month:02d}-01")
        year, month = (year, 7) if month == 1 else (year + 1, 1)
    return out


def corrections(m, feats, base_hx, base_ax, blocks, end, usable):
    """Walk-forward (margin, total) corrections for the fixtures of each block, from trees trained
    on usable fixtures before it (architectures/run.py, gb_fit_predict)."""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingRegressor
    X = np.column_stack([feats[name] for name in FEATURES])
    margin_res = (m.ft_home - m.ft_away) - (base_hx - base_ax)
    total_res = (m.ft_home + m.ft_away) - (base_hx + base_ax)
    d_margin, d_total = np.zeros(m.n), np.zeros(m.n)
    edges = list(blocks) + [end]
    for start, stop in zip(edges, edges[1:]):
        train = usable & (m.day < start)
        test = (m.day >= start) & (m.day < stop) & ~np.isnan(base_hx)
        if not test.any():
            continue
        live = ~np.all(np.isnan(X[train]), axis=0)
        for target, out in ((margin_res, d_margin), (total_res, d_total)):
            model = HistGradientBoostingRegressor(**TREES)
            model.fit(X[train][:, live], target[train])
            out[test] = model.predict(X[test][:, live])
    return d_margin, d_total


def corrected(base_hx, base_ax, d_margin, d_total, shrink=SHRINK):
    """The base model's projected goals with the margin moved and the total scaled."""
    import numpy as np
    hx, ax = moved(base_hx, base_ax, shrink * d_margin)
    scale = np.clip(1 + shrink * d_total / (hx + ax), *SCALE_LIMITS)
    return hx * scale, ax * scale


def a18_goals(m, base_hx, base_ax, blocks, end, today=None):
    """(home, away) projected goals of a18 over every fixture with a block, and the parts."""
    poisson = Poisson(m, **POISSON)
    lam, mu = poisson.run(FIRST_DAY, end, today)
    feats = features(m, base_hx, base_ax)
    feats["dc_margin"], feats["dc_total"] = lam - mu - (base_hx - base_ax), lam + mu - (base_hx + base_ax)
    import numpy as np
    usable = m.scored & ~np.isnan(base_hx)
    dm, dt = corrections(m, feats, base_hx, base_ax, blocks, end, usable)
    gh, ga = corrected(base_hx, base_ax, dm, dt)
    return gh, ga, {"lam": lam, "mu": mu, "features": feats, "d_margin": dm, "d_total": dt}


# ---- the database ----------------------------------------------------------------------------

def _iso(kickoff):
    return kickoff.astimezone(timezone.utc).isoformat() if kickoff.tzinfo else kickoff.isoformat()


def history(conn):
    """The finished fixtures, with their statistics, the base model's stored projection of each and
    the managers on their line-ups. Cached by week (cache.cached_rows)."""
    statuses = [list(config.FINISHED_STATUSES)]
    fixtures = cached_rows(conn, "tree_fixtures", f"""
        select {WEEK.format('f.kickoff')} as part, f.fixture_id, f.kickoff, f.league_id, f.home_team_id, f.away_team_id,
               f.status_short, f.home_goals, f.away_goals, f.ft_home, f.ft_away,
               hx.expected_goals::float8, ax.expected_goals::float8, hx.total_shots, ax.total_shots,
               hx.shots_on_goal, ax.shots_on_goal, hx.shots_inside_box, ax.shots_inside_box
        from fixtures f
        left join fixture_team_stats hx on hx.fixture_id = f.fixture_id and hx.is_home
        left join fixture_team_stats ax on ax.fixture_id = f.fixture_id and not ax.is_home
        where f.status_short = any(%s) and f.home_goals is not null and f.away_goals is not null""",
        statuses, order_by="kickoff, fixture_id")
    stored = cached_rows(conn, "tree_projections", f"""
        select {WEEK.format('f.kickoff')} as part, p.fixture_id, p.home_rank, p.away_rank, p.home_xg, p.away_xg,
               p.p_home, p.home_missing, p.away_missing
        from fixture_predictions p join fixtures f using (fixture_id)
        where f.status_short = any(%s)""", statuses, order_by="fixture_id")
    coaches = cached_rows(conn, "tree_coaches", f"""
        select {WEEK.format('f.kickoff')} as part, m.fixture_id, m.team_id, m.coach_id
        from fixture_formations m join fixtures f using (fixture_id)
        where f.status_short = any(%s) and m.coach_id is not null""", statuses, order_by="fixture_id, team_id")
    return ([(r[0], _iso(r[1]), *r[2:]) for r in fixtures], {r[0]: tuple(r[1:]) for r in stored},
            {(r[0], r[1]): r[2] for r in coaches})


def live_model(conn):
    """The model the switch names, or None before the migration is applied."""
    exists = conn.execute("select to_regclass('public.match_model_switch')").fetchone()[0]
    return conn.execute("select live from match_model_switch").fetchone()[0] if exists else None


def update(conn, fixture_ids=None):
    """Work out a18 beside the base model for the upcoming fixtures (or those in fixture_ids, as
    predictions.update_predictions was just run for), store both models' predictions, and when
    the switch names a18 write its predictions over base's in fixture_predictions."""
    live = live_model(conn)
    if live is None:
        log.info("Match trees: the switch is not there yet (migration 20261014_challenger_model.sql); skipped")
        return
    import numpy as np
    from . import predictions
    from ..evidence import match_snapshots
    now = datetime.now(timezone.utc)
    upcoming = conn.execute(
        """select p.fixture_id, f.kickoff, f.league_id, f.home_team_id, f.away_team_id, p.home_rank, p.away_rank,
                  p.home_xg, p.away_xg, p.p_home, p.p_draw, p.p_away, p.p_over25, p.p_btts, p.home_missing, p.away_missing
           from fixture_predictions p join fixtures f using (fixture_id)
           where f.kickoff > %s and f.status_short = any(%s)
             and (%s::int[] is null or p.fixture_id = any(%s::int[]))""",
        [now, list(predictions.UPCOMING_STATUSES), fixture_ids, fixture_ids]).fetchall()
    if not upcoming:
        log.info("Match trees: no upcoming fixtures")
        return
    fixtures, stored, coaches = history(conn)
    # where a18 was live, fixture_predictions holds a18's projection: the base model's own is kept here
    for fid, hr, ar, hx, ax, ph in conn.execute(
            """select c.fixture_id, c.home_match_rank, c.away_match_rank, c.home_xg, c.away_xg, c.p_home
               from challenger_predictions c join fixtures f using (fixture_id)
               where c.model = 'base' and f.status_short = any(%s)""", [list(config.FINISHED_STATUSES)]):
        old = stored.get(fid)
        stored[fid] = (hr, ar, hx, ax, ph, *(old[5:] if old else (None, None)))
    leagues = {lg: (c, t, s) for lg, c, t, s in conn.execute(
        "select league_id, country, type, starting_rank::float8 from leagues")}
    ranks = {(fid, home): (before, lt, match_no - 1)
             for fid, _, match_no, _, home, _, before, _, lt, *_ in rank_history(conn)}
    current = {t: (cur, lt, played) for t, cur, lt, played in conn.execute(
        "select team_id, current_rank, lt_algo, played from team_rankings")}
    for row in upcoming:
        fid, kickoff, league_id, home, away, hr, ar, hx, ax, ph, *_rest, hm, am = row
        fixtures.append((fid, _iso(kickoff), league_id, home, away, "NS", None, None, None, None,
                         None, None, None, None, None, None, None, None))
        stored[fid] = (hr, ar, hx, ax, ph, hm, am)
        for side, team in ((True, home), (False, away)):
            cur, lt, played = current.get(team, (None, None, 0))
            if cur is not None:
                ranks[(fid, side)] = (cur, lt if lt is not None else cur, played)
    m = Matches(fixtures, leagues, coaches, stored, ranks)
    base_hx, base_ax = reprojected(m)
    for row in upcoming:                       # the upcoming fixtures' own projections, as made
        i = m.index[row[0]]
        base_hx[i], base_ax[i] = row[7], row[8]
    today = now.date().isoformat()
    block = half_seasons("2021-07-01", today)[-1]
    end = (now.date() + timedelta(days=400)).isoformat()
    gh, ga, _ = a18_goals(m, base_hx, base_ax, [block], end, today)

    version = register_version(conn)
    base_version = match_snapshots.register_version(conn)
    out, live_rows = [], []
    for row in upcoming:
        fid, kickoff, league_id, home, away, hr, ar, hx, ax, ph, pd, pa, po, pb, hm, am = row
        i = m.index[fid]
        out.append((fid, "base", base_version, kickoff, hr, ar, hx, ax, ph, pd, pa, po, pb, now))
        if np.isnan(gh[i]) or np.isnan(ga[i]):
            continue
        h, a = float(gh[i]), float(ga[i])
        p_home, p_draw, p_away, likely = predictions.outcome_probabilities(h, a)
        over25, btts = predictions.goal_markets(h, a)
        out.append((fid, "a18", version, kickoff, hr, ar, h, a, p_home, p_draw, p_away, over25, btts, now))
        live_rows.append((h - a, h, a, p_home, p_draw, p_away, likely, over25, btts, fid))
    with conn.cursor() as cur:
        cur.executemany(
            """insert into challenger_predictions (fixture_id, model, model_version_id, kickoff, home_match_rank,
                   away_match_rank, home_xg, away_xg, p_home, p_draw, p_away, p_over25, p_btts, captured_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (fixture_id, model) do update set
                 model_version_id = excluded.model_version_id, kickoff = excluded.kickoff,
                 home_match_rank = excluded.home_match_rank, away_match_rank = excluded.away_match_rank,
                 home_xg = excluded.home_xg, away_xg = excluded.away_xg, p_home = excluded.p_home,
                 p_draw = excluded.p_draw, p_away = excluded.p_away, p_over25 = excluded.p_over25,
                 p_btts = excluded.p_btts, captured_at = excluded.captured_at""", out)
        if live == "a18":
            cur.executemany(
                """update fixture_predictions set exp_diff = %s, home_xg = %s, away_xg = %s, p_home = %s,
                       p_draw = %s, p_away = %s, likely_score = %s, p_over25 = %s, p_btts = %s, updated_at = now()
                   where fixture_id = %s""", live_rows)
    conn.commit()
    log.info("Match trees: %d upcoming fixtures, a18 for %d; live model %s", len(upcoming), len(live_rows), live)


def update_safely(conn, fixture_ids=None):
    """update(), never failing the job that runs it: the base model's predictions are already
    stored, and stay live if this fails."""
    try:
        update(conn, fixture_ids)
    except Exception:
        conn.rollback()
        log.exception("Match trees failed; the base model's predictions stand")


def register_version(conn):
    """a18's model version: its recipe and the files that make its numbers."""
    from ..evidence.model_versions import ModelType, current_code_sha, register_model_version, source_digests
    settings = {"features": list(FEATURES), "trees": TREES, "shrink": SHRINK, "scale_limits": list(SCALE_LIMITS),
                "poisson": POISSON, "ridges": [RIDGE_LEAGUE, RIDGE_GOALS, RIDGE_HOME], "refit_days": REFIT_DAYS,
                "first_day": FIRST_DAY, "now_weight": NOW_WEIGHT,
                "source_digests": source_digests(("match_trees.py", "predictions.py", "ranking.py"))}
    return register_model_version(conn, ModelType.MATCH, "match-trees-a18", code_sha=current_code_sha(),
                                  configuration=settings, notes="A18 on the base match model (MC-0029).")
