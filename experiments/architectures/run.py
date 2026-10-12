"""Architectures: other ways of building the prediction, against production (DESIGN.md).

    dc       a hierarchical, time-weighted Poisson model with separate attack and defence for
             every club, a level for every league and a Dixon-Coles low-score term, refitted
             every week on everything before that week (the Dixon-Coles family, with clubs
             shrunk towards their league: "dynamic attack/defence" and "hierarchical" in one)
    gb       gradient-boosted trees that correct production's expected margin and total goals
             from pre-match features (form, xG and shots, schedule, division changes, managers,
             injuries, venue), retrained every half-season on everything before it
    pool2    production and dc combined
    pool3    production, dc and gb combined

Two stages. `develop` chooses every setting on the development period and writes chosen.json
and the development predictions; `final` refits forward through the final period with those
settings and scores it once.

    python experiments/architectures/run.py develop
    python experiments/architectures/run.py final

Offline: reads experiments/research_frame/inputs.json.gz only. Needs numpy, scipy, scikit-learn.
"""
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_frame"))
import features  # noqa: E402
import frame  # noqa: E402

HERE = Path(__file__).parent
CHOSEN, OUT, DEV_PREDICTIONS = HERE / "chosen.json", HERE / "results.json", HERE / "development.npz"

SELECTION_START = "2022-07-01"
FAMILY = 13
LEVEL = 1 - 0.05 / FAMILY
REFIT_DAYS = 7
LEAGUE_WINDOW = 400

DC_START = dict(half_life=500.0, ridge_team=25.0, use_xg=1)
DC_GRID = {"ridge_team": (1.0, 3.0, 10.0, 25.0), "half_life": (250.0, 500.0, 1000.0), "use_xg": (0, 1)}
RIDGE_LEAGUE, RIDGE_GOALS, RIDGE_HOME = 2.0, 100.0, 400.0
RHO_GRID = tuple(round(-0.20 + 0.01 * i, 2) for i in range(31))          # Dixon-Coles rho
GB_GRID = [dict(max_depth=2, max_iter=150), dict(max_depth=3, max_iter=150), dict(max_depth=3, max_iter=300)]
GB_SHRINK = (0.5, 0.75, 1.0)
GB_BLOCKS_DEV = ("2022-07-01", "2023-01-01", "2023-07-01", "2024-01-01")
GB_BLOCKS_FINAL = ("2024-07-01", "2025-01-01", "2025-07-01", "2026-01-01", "2026-07-01")
POOL_STEP = 0.1


# ---- dc: the weekly-refitted hierarchical Poisson model --------------------------------------

class DC:
    """Walk-forward fits. For each refit day, parameters are estimated from matches that
    kicked off before it, and used for the matches of the next REFIT_DAYS days."""

    def __init__(self, data, half_life, ridge_team, use_xg):
        self.d, self.half_life, self.ridge_team = data, half_life, ridge_team
        d = data
        teams = np.unique(np.concatenate([d.home, d.away]))
        self.team_index = {t: j for j, t in enumerate(teams)}
        self.h = np.array([self.team_index[t] for t in d.home])
        self.a = np.array([self.team_index[t] for t in d.away])
        comps = np.unique(d.league)
        self.comp_index = {c: j for j, c in enumerate(comps)}
        self.c = np.array([self.comp_index[c] for c in d.league])
        self.nt, self.nc = len(teams), len(comps)
        # goals: the regulation score where there is one; blended with xG like production's rank
        gh = np.where(np.isnan(d.ft_home), d.home_goals, d.ft_home)
        ga = np.where(np.isnan(d.ft_away), d.away_goals, d.ft_away)
        if use_xg:
            has = ~np.isnan(d.home_xg) & ~np.isnan(d.away_xg)
            gh = np.where(has, 0.3 * np.minimum(gh, 5) + 0.7 * d.home_xg, gh)
            ga = np.where(has, 0.3 * np.minimum(ga, 5) + 0.7 * d.away_xg, ga)
        self.yh, self.ya = gh, ga
        # each club's group on each day: its league (last league match within the window), or
        # the country of the first competition it was seen in for a club with no league
        self.groups = {}
        self.group_at = self._group_history()
        self.theta = None

    def _group_history(self):
        """[(ordinal, team index, group index)] changes in kickoff order."""
        d = self.d
        changes, current = [], {}

        def group(key):
            return self.groups.setdefault(key, len(self.groups))

        for i in range(d.n):
            for t in (self.h[i], self.a[i]):
                if d.is_league[i]:
                    g = group(("league", int(d.league[i])))
                elif t not in current:
                    g = group(("none", d.leagues[d.league[i]]["country"]))
                else:
                    continue
                if current.get(t) != g:
                    current[t] = g
                    changes.append((d.ordinal[i], t, g))
        return changes

    def run(self, first_day, last_day, verbose=True):
        """(lam, mu) arrays over fixtures, filled for kickoffs in [first_day, last_day)."""
        d = self.d
        lam, mu = np.full(d.n, np.nan), np.full(d.n, np.nan)
        start, stop = date.fromisoformat(first_day).toordinal(), date.fromisoformat(last_day).toordinal()
        team_group = np.zeros(self.nt, dtype=int)
        seen = np.zeros(self.nt, dtype=bool)
        pos, t0 = 0, time.time()
        fits = 0
        for day in range(start, stop, REFIT_DAYS):
            while pos < len(self.group_at) and self.group_at[pos][0] < day:
                _, t, g = self.group_at[pos]
                team_group[t], seen[t] = g, True
                pos += 1
            train = (d.ordinal < day) & (d.ordinal >= day - 4 * self.half_life)
            self._fit(train, day, team_group)
            fits += 1
            block = np.where((d.ordinal >= day) & (d.ordinal < min(day + REFIT_DAYS, stop)))[0]
            if len(block):
                # a club first seen in this block takes the group of the competition it is in
                grp = team_group.copy()
                for i in block:
                    for t in (self.h[i], self.a[i]):
                        if not seen[t]:
                            key = ("league", int(d.league[i])) if d.is_league[i] else ("none", d.leagues[d.league[i]]["country"])
                            grp[t] = self.groups[key]
                lam[block], mu[block] = self._rates(block, grp)
        if verbose:
            print(f"  dc half-life {self.half_life:.0f} ridge {self.ridge_team:.0f}: {fits} fits in {time.time() - t0:.0f}s", flush=True)
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
        c0, home, att, dfc, g_att, g_def, goals, comp_home = self._unpack(self.theta)
        h, a, c = self.h[rows], self.a[rows], self.c[rows]
        gh, ga = team_group[h], team_group[a]
        common = c0 + goals[c]
        lam = np.exp(common + home + comp_home[c] + att[h] + g_att[gh] - dfc[a] - g_def[ga])
        mu = np.exp(common + att[a] + g_att[ga] - dfc[h] - g_def[gh])
        return lam, mu

    def _fit(self, train, day, team_group):
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
            if old is not None:                   # groups were added: keep everything else
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


def dc_grid(lam, mu, rho):
    """Score grid with the Dixon-Coles low-score term."""
    g = frame.grid(lam, mu)
    if rho:
        g = g.copy()
        g[:, 0, 0] *= 1 - lam * mu * rho
        g[:, 0, 1] *= 1 + lam * rho
        g[:, 1, 0] *= 1 + mu * rho
        g[:, 1, 1] *= 1 - rho
        g = np.clip(g, 1e-12, None)
        g /= g.sum(axis=(1, 2), keepdims=True)
    return g


def dc_probabilities(lam, mu, rho):
    g = dc_grid(lam, mu, rho)
    home = (g * frame._LOWER).sum(axis=(1, 2))
    draw = np.einsum("nii->n", g)
    return np.stack([home, draw, 1 - home - draw], axis=1)


# ---- gb: boosted corrections to production's margin and total --------------------------------

def gb_matrix(feats, names):
    return np.column_stack([feats[n] for n in names])


def gb_fit_predict(data, feats, names, base_hx, base_ax, blocks, end, params, usable):
    """Walk-forward corrections (margin, total) for fixtures in each block, from models
    trained on scored matches before the block."""
    X = gb_matrix(feats, names)
    margin_res = (data.ft_home - data.ft_away) - (base_hx - base_ax)
    total_res = (data.ft_home + data.ft_away) - (base_hx + base_ax)
    d_margin, d_total = np.zeros(data.n), np.zeros(data.n)
    edges = list(blocks) + [end]
    for start, stop in zip(edges, edges[1:]):
        train = usable & (data.day < start)
        test = (data.day >= start) & (data.day < stop) & ~np.isnan(base_hx)
        # a feature with no value yet in the training rows (xG before 2022/23) is left out of this block
        live = ~np.all(np.isnan(X[train]), axis=0)
        for target, out in ((margin_res, d_margin), (total_res, d_total)):
            model = HistGradientBoostingRegressor(
                learning_rate=0.03, min_samples_leaf=200, l2_regularization=1.0, random_state=frame.SEED, **params)
            model.fit(X[train][:, live], target[train])
            out[test] = model.predict(X[test][:, live])
    return d_margin, d_total


def gb_apply(base_hx, base_ax, d_margin, d_total, shrink):
    """Production's projected goals with the margin moved and the total scaled."""
    hx, ax = frame.moved(base_hx, base_ax, shrink * d_margin)
    scale = np.clip(1 + shrink * d_total / (hx + ax), 0.7, 1.4)
    return hx * scale, ax * scale


# ---- pools -----------------------------------------------------------------------------------

def pool(parts, weights):
    """Log-linear pool of result probabilities."""
    z = sum(w * np.log(np.clip(p, 1e-12, 1)) for p, w in zip(parts, weights))
    z = np.exp(z - z.max(axis=1, keepdims=True))
    return z / z.sum(axis=1, keepdims=True)


def simplex(k, step=POOL_STEP):
    n = round(1 / step)
    if k == 2:
        return [(1 - i / n, i / n) for i in range(n + 1)]
    return [(1 - (i + j) / n, i / n, j / n) for i in range(n + 1) for j in range(n + 1 - i)]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def loss(data, p, rows):
    return float(frame.log_loss(p[rows], data.result[rows]).mean())


def baseline(data):
    rep = frame.replay(data)
    hx, ax = frame.reprojected(data, rep)
    ok = ~np.isnan(hx)
    p = np.full((data.n, 3), np.nan)
    p[ok] = frame.outcome_probabilities(hx[ok], ax[ok])
    return rep, hx, ax, p


def feature_names(without=()):
    return features.BASE + [n for g, names in features.GROUPS.items() if g not in without for n in names]


# ---- develop ---------------------------------------------------------------------------------

def develop():
    data = frame.Data()
    rep, hx, ax, base = baseline(data)
    dev = data.development
    select = dev & (data.day >= SELECTION_START)
    report = {"selection_window": [SELECTION_START, frame.DEVELOPMENT_END], "selection_matches": int(select.sum()),
              "production_selection_log_loss": loss(data, base, select)}
    rates = np.array([(data.result[select] == k).mean() for k in range(3)])
    prior = data.development & (data.day < SELECTION_START)
    rates_prior = np.array([(data.result[prior] == k).mean() for k in range(3)])
    report["base_rate_selection_log_loss"] = float(-np.log(rates_prior[data.result[select]]).mean())

    # dc: coordinate search from DC_START, each setting scored on the selection window with rho 0
    def dc_loss(setting, keep=False):
        lam, mu = DC(data, **setting).run(frame.BURN_IN_END, frame.DEVELOPMENT_END)
        value = float(frame.log_loss(dc_probabilities(lam[select], mu[select], 0.0), data.result[select]).mean())
        return (value, lam, mu) if keep else value

    setting, trail = dict(DC_START), []
    best = dc_loss(setting)
    trail.append({**setting, "selection_log_loss": best})
    print("dc start", setting, best, flush=True)
    for name, values in DC_GRID.items():
        tried = {setting[name]}
        for v in values:
            if v in tried:
                continue
            tried.add(v)
            trial = {**setting, name: v}
            value = dc_loss(trial)
            trail.append({**trial, "selection_log_loss": value})
            print("dc", trial, value, flush=True)
            if value < best:
                best, setting = value, trial
    _, lam, mu = dc_loss(setting, keep=True)
    rho_rows = [{"rho": r, "selection_log_loss": float(frame.log_loss(dc_probabilities(lam[select], mu[select], r), data.result[select]).mean())}
                for r in RHO_GRID]
    rho = min(rho_rows, key=lambda r: r["selection_log_loss"])["rho"]
    p_dc = np.full((data.n, 3), np.nan)
    p_dc[dev] = dc_probabilities(lam[dev], mu[dev], rho)
    report["dc"] = {"setting": setting, "rho": rho, "trail": trail, "rho_grid": rho_rows,
                    "selection_log_loss": loss(data, p_dc, select),
                    "by_season": {data.season_label(s): loss(data, p_dc, dev & (data.season == s)) for s in (2021, 2022, 2023)}}
    print("dc chosen", setting, "rho", rho, report["dc"]["selection_log_loss"], flush=True)

    # gb
    feats = features.build(data, rep, hx, ax)
    feats["dc_margin"], feats["dc_total"] = lam - mu - (hx - ax), lam + mu - (hx + ax)
    usable = data.scored & ~np.isnan(hx)
    names = feature_names() + ["dc_margin", "dc_total"]
    gb_rows = []
    for params in GB_GRID:
        dm, dt = gb_fit_predict(data, feats, names, hx, ax, GB_BLOCKS_DEV, frame.DEVELOPMENT_END, params, usable & dev)
        for shrink in GB_SHRINK:
            gh, ga = gb_apply(hx[select], ax[select], dm[select], dt[select], shrink)
            value = float(frame.log_loss(frame.outcome_probabilities(gh, ga), data.result[select]).mean())
            gb_rows.append({**params, "shrink": shrink, "selection_log_loss": value})
            print("gb", gb_rows[-1], flush=True)
    gb_best = min(gb_rows, key=lambda r: r["selection_log_loss"])
    gb_params = {k: gb_best[k] for k in ("max_depth", "max_iter")}
    dm, dt = gb_fit_predict(data, feats, names, hx, ax, GB_BLOCKS_DEV, frame.DEVELOPMENT_END, gb_params, usable & dev)
    p_gb = np.full((data.n, 3), np.nan)
    gh, ga = gb_apply(hx[select], ax[select], dm[select], dt[select], gb_best["shrink"])
    p_gb[select] = frame.outcome_probabilities(gh, ga)
    report["gb"] = {"params": gb_params, "shrink": gb_best["shrink"], "grid": gb_rows,
                    "selection_log_loss": gb_best["selection_log_loss"], "features": names}
    # which feature groups carry the gain: the chosen model refitted without each group
    ablation = {}
    for group in list(features.GROUPS) + ["dc"]:
        keep = [n for n in names if n not in features.GROUPS.get(group, ["dc_margin", "dc_total"])]
        am, at = gb_fit_predict(data, feats, keep, hx, ax, GB_BLOCKS_DEV, frame.DEVELOPMENT_END, gb_params, usable & dev)
        g1, g2 = gb_apply(hx[select], ax[select], am[select], at[select], gb_best["shrink"])
        value = float(frame.log_loss(frame.outcome_probabilities(g1, g2), data.result[select]).mean())
        ablation[group] = value - gb_best["selection_log_loss"]
        print("gb without", group, f"{ablation[group]:+.5f}", flush=True)
    report["gb"]["loss_added_by_removing_group"] = ablation

    # pools, weights chosen on the selection window
    def best_pool(parts):
        rows = [(float(frame.log_loss(pool([p[select] for p in parts], w), data.result[select]).mean()), w)
                for w in simplex(len(parts))]
        return min(rows)

    v2, w2 = best_pool([base, p_dc])
    v3, w3 = best_pool([base, p_dc, p_gb])
    report["pool2"] = {"weights": {"production": w2[0], "dc": w2[1]}, "selection_log_loss": v2}
    report["pool3"] = {"weights": {"production": w3[0], "dc": w3[1], "gb": w3[2]}, "selection_log_loss": v3}
    print("pool2", report["pool2"], "\npool3", report["pool3"], flush=True)
    report["evaluator_sha256"] = digest(__file__)
    report["frame_sha256"], report["features_sha256"] = digest(frame.__file__), digest(features.__file__)
    CHOSEN.write_text(json.dumps(report, indent=1) + "\n")
    np.savez_compressed(DEV_PREDICTIONS, lam=lam, mu=mu)


# ---- final -----------------------------------------------------------------------------------

def verdict(c):
    mean, lo, hi = c["log_loss"]
    seasons = [c["by_season"].get(s, {}).get("log_loss") for s in ("2024/25", "2025/26")]
    no_worse, listed = c["competitions_no_worse"]
    bar = {"log_loss_better_by_0.002": mean <= -0.002, "adjusted_interval_excludes_zero": hi < 0,
           "brier_agrees": c["brier"][0] < 0,
           "better_in_2024/25_and_2025/26": all(s is not None and s < 0 for s in seasons),
           "no_goal_market_worse_by_0.0005": all(v <= 0.0005 for v in c["goal_markets"].values()),
           "60_percent_of_competitions_no_worse": listed > 0 and no_worse / listed >= 0.6}
    label = "meets the bar" if all(bar.values()) else \
        "a real gain below the bar" if hi < 0 and mean < 0 else "no gain shown"
    return {"conditions": bar, "label": label}


def final():
    if not CHOSEN.exists():
        raise SystemExit("run `develop` first: chosen.json is missing")
    chosen = json.loads(CHOSEN.read_text())
    data = frame.Data()
    rep, hx, ax, base = baseline(data)
    rows = data.final
    t0 = time.time()
    lam, mu = DC(data, **chosen["dc"]["setting"]).run(frame.BURN_IN_END, frame.FINAL_END)
    rho = chosen["dc"]["rho"]
    ok = ~np.isnan(lam)
    p_dc = np.full((data.n, 3), np.nan)
    p_dc[ok] = dc_probabilities(lam[ok], mu[ok], rho)
    feats = features.build(data, rep, hx, ax)
    feats["dc_margin"], feats["dc_total"] = lam - mu - (hx - ax), lam + mu - (hx + ax)
    usable = data.scored & ~np.isnan(hx)
    dm, dt = gb_fit_predict(data, feats, chosen["gb"]["features"], hx, ax, GB_BLOCKS_FINAL, frame.FINAL_END,
                            chosen["gb"]["params"], usable)
    gh, ga = gb_apply(hx, ax, dm, dt, chosen["gb"]["shrink"])
    p_gb = np.full((data.n, 3), np.nan)
    p_gb[rows] = frame.outcome_probabilities(gh[rows], ga[rows])
    w2, w3 = chosen["pool2"]["weights"], chosen["pool3"]["weights"]
    cands = {
        "dc": (p_dc, lam, mu, "dc"),
        "gb": (p_gb, gh, ga, "production"),
        "pool2": (pool([base[rows], p_dc[rows]], [w2["production"], w2["dc"]]), None, None, None),
        "pool3": (pool([base[rows], p_dc[rows], p_gb[rows]], [w3["production"], w3["dc"], w3["gb"]]), None, None, None),
    }
    events = frame.goal_events(data, rows)
    base_goal = frame.binary_log_loss(frame.goal_markets(hx[rows], ax[rows]), events).mean(axis=0)
    rates = np.array([(data.result[data.development] == k).mean() for k in range(3)])
    report = {"level": LEVEL, "family": FAMILY, "final_matches": int(rows.sum()),
              "chosen_sha256": digest(CHOSEN), "evaluator_sha256": digest(__file__),
              "frame_sha256": digest(frame.__file__), "features_sha256": digest(features.__file__),
              "seconds": None, "base_rate_log_loss": float(-np.log(rates[data.result[rows]]).mean()),
              "candidates": {}}
    for name, (p, g_home, g_away, kind) in cands.items():
        p_rows = p if len(p) == rows.sum() else p[rows]
        c = frame.compare(data, rows, base[rows], p_rows, LEVEL)
        c["interval_95"] = frame.paired_interval(
            frame.log_loss(p_rows, data.result[rows]) - frame.log_loss(base[rows], data.result[rows]), data.week[rows], 0.95)
        if kind == "production":
            goal = frame.binary_log_loss(frame.goal_markets(g_home[rows], g_away[rows]), events).mean(axis=0) - base_goal
        elif kind == "dc":
            # the model's own goal lines, uncalibrated: it has no base-rate shrink fitted
            own = frame.goal_markets_from_grid(dc_grid(lam[rows], mu[rows], rho), calibrated=False)
            goal = frame.binary_log_loss(own, events).mean(axis=0) - base_goal
        else:
            goal = np.zeros(5)                    # pools change the result probabilities only
        c["goal_markets"] = dict(zip(frame.GOAL_MARKETS, map(float, goal)))
        c["verdict"] = verdict(c)
        report["candidates"][name] = c
        m = c["log_loss"]
        print(f"{name:6s} final log loss {c['baseline']['log_loss']:.5f} -> {c['candidate']['log_loss']:.5f}"
              f" ({m[0]:+.5f}, {m[1]:+.5f} to {m[2]:+.5f}) | Brier {c['brier'][0]:+.5f} | leagues {c['leagues']['log_loss']:+.5f}"
              f" cups {c['cups']['log_loss']:+.5f} | no worse {c['competitions_no_worse']} | {c['verdict']['label']}")
        print("   by season", {k: round(v["log_loss"], 5) for k, v in c["by_season"].items()},
              "| goal markets", {k: round(v, 5) for k, v in c["goal_markets"].items()}, flush=True)
    report["seconds"] = time.time() - t0
    OUT.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    {"develop": develop, "final": final}[sys.argv[1] if len(sys.argv) > 1 else ""]()
