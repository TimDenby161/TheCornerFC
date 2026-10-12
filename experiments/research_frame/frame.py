"""The research frame: the frozen inputs, the production model re-run offline, the periods, the
measures and the intervals that every experiment in this research round shares.

Nothing here reads the database or imports the production package: the ranking replay and the
probability step are copied from thecornerfc/models/ranking.py and predictions.py and checked
against the stored predictions (reproduction()), so an experiment can change one of their
numbers and re-run years of matches in seconds. Needs numpy.

Periods (fixed 2026-10-12, before any research result was seen):

    burn-in       kickoff before 2021-07-01   ratings settle; never scored
    development   2021-07-01 to 2024-06-30    diagnostics, model selection, every tuned number
    final         2024-07-01 to 2026-10-11    scored once per registered candidate

Inside development everything is walk-forward: a prediction for a match uses only matches that
kicked off before it. A setting is chosen on development and then frozen.
"""
import gzip
import json
import math
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
INPUTS = HERE / "inputs.json.gz"

BURN_IN_END, DEVELOPMENT_END, FINAL_END = "2021-07-01", "2024-07-01", "2026-10-12"
SEED, DRAWS = 20261012, 2000

# production settings (ranking.py, predictions.py), as at commit 0346aae80
PRODUCTION = dict(
    home_advantage=30.0, k=6.0, k_xg=10.0, max_goal_diff=3, goals_weight=0.3,
    default_start=650.0, now_weight=0.6,
)
COMPETITION_WEIGHT = {528: 1 / 3, 531: 1 / 3}
DRAW_INFLATION, DRAW_FADE_MARGIN = 1.1, 1.5
MAX_GOALS = 10
OVER25 = (0.514, 0.85)
BTTS = (0.519, 0.60)
GOAL_LINE_CALIBRATION = {1.5: (0.76, 0.9), 3.5: (0.36, 0.9), 4.5: (0.04, 1.0)}


# ---- inputs ----------------------------------------------------------------------------------

def load():
    with gzip.open(INPUTS, "rt", encoding="utf-8") as fh:
        return json.load(fh)


class Data:
    """The fixtures as columns, in replay order (kickoff, fixture_id), with the stored projection
    of each where there is one."""

    def __init__(self, doc=None):
        doc = doc or load()
        self.doc = doc
        cols = doc["fixtures"]["columns"]
        rows = doc["fixtures"]["rows"]
        rows.sort(key=lambda r: (r[1], r[0]))
        n = self.n = len(rows)
        get = lambda i: [r[i] for r in rows]
        num = lambda i: np.array([np.nan if r[i] is None else r[i] for r in rows], dtype=float)
        self.fixture_id = np.array(get(0))
        self.kickoff = get(1)
        self.day = np.array([k[:10] for k in self.kickoff])
        self.league = np.array(get(2))
        self.season_field = np.array(get(3))
        self.round = get(4)
        self.home = np.array(get(5))
        self.away = np.array(get(6))
        self.status = np.array(get(7))
        self.home_goals, self.away_goals = num(8), num(9)
        self.ft_home, self.ft_away = num(10), num(11)
        self.venue = get(12)
        self.home_xg, self.away_xg = num(13), num(14)
        self.home_shots, self.away_shots = num(15), num(16)
        self.home_sot, self.away_sot = num(17), num(18)
        self.home_box, self.away_box = num(19), num(20)
        self.home_possession = num(21)
        self.home_reds, self.away_reds = num(22), num(23)
        self.home_corners, self.away_corners = num(24), num(25)
        assert cols[13] == "expected_goals" and cols[2] == "league_id"

        self.leagues = {r[0]: {"name": r[1], "country": r[2], "type": r[3], "starting_rank": r[4]}
                        for r in doc["leagues"]["rows"]}
        self.is_league = np.array([self.leagues[l]["type"] == "League" for l in self.league])

        index = {f: i for i, f in enumerate(self.fixture_id)}
        self.index = index
        pc = doc["predictions"]["columns"]
        self.pred = {name: np.full(n, np.nan) for name in pc[1:11] + pc[12:]}
        self.pred_source = np.array([None] * n, dtype=object)
        for r in doc["predictions"]["rows"]:
            i = index.get(r[0])
            if i is None:
                continue
            for j, name in enumerate(pc):
                if name == "source":
                    self.pred_source[i] = r[j]
                elif j and r[j] is not None:
                    self.pred[name][i] = r[j]

        ord_day = np.array([date.fromisoformat(d).toordinal() for d in self.day])
        self.ordinal = ord_day
        iso = [date.fromisoformat(d).isocalendar() for d in self.day]
        self.week = np.array([y * 100 + w for y, w, _ in iso])
        self.season = np.array([(int(d[:4]) if int(d[5:7]) >= 7 else int(d[:4]) - 1) for d in self.day])
        # scored: finished in 90 minutes, a regulation score and a stored projection
        self.scored = ((self.status == "FT") & ~np.isnan(self.ft_home) & ~np.isnan(self.ft_away)
                       & ~np.isnan(self.pred["home_xg"]) & ~np.isnan(self.pred["p_home"])
                       & (self.day >= BURN_IN_END) & (self.day < FINAL_END))
        self.development = self.scored & (self.day < DEVELOPMENT_END)
        self.final = self.scored & (self.day >= DEVELOPMENT_END)
        self.result = np.where(self.ft_home > self.ft_away, 0, np.where(self.ft_home == self.ft_away, 1, 2))

    def season_label(self, s):
        return f"{s}/{str(s + 1)[2:]}"


# ---- the club rank replay (ranking.run and the LT ALGO of ranking.summarise) ------------------

def starting_ranks(data, default=PRODUCTION["default_start"]):
    """{team: starting rank}: the first League-type competition it plays in, else its first
    competition, as ranking.update_rankings works it out (it looks over all fixtures, so a
    club's start can come from a league it joins later; kept, because it is production)."""
    first_league, first_comp = {}, {}
    for i in range(data.n):
        lg = data.league[i]
        for team in (data.home[i], data.away[i]):
            first_comp.setdefault(team, lg)
            if data.is_league[i]:
                first_league.setdefault(team, lg)
    out = {}
    for team, lg in first_comp.items():
        level = data.leagues[first_league.get(team, lg)]["starting_rank"]
        out[team] = float(default if level is None else level)
    return out, first_league, first_comp


class Replay:
    """Pre-match current rank and LT ALGO of both sides of every fixture, and the expected
    margin from the raw ranks, after a replay with the given settings."""

    def __init__(self, n):
        self.h_now, self.a_now = np.zeros(n), np.zeros(n)
        self.h_lt, self.a_lt = np.zeros(n), np.zeros(n)
        self.h_played, self.a_played = np.zeros(n, dtype=int), np.zeros(n, dtype=int)

    def match_rank(self, now_weight=PRODUCTION["now_weight"]):
        return (now_weight * self.h_now + (1 - now_weight) * self.h_lt,
                now_weight * self.a_now + (1 - now_weight) * self.a_lt)


def _lt(hist, cs):
    """LT ALGO from a team's history list (starting rank, then the rank after each match) and
    its running sums: ranking.summarise on the last 101 values."""
    played = min(len(hist) - 1, 100)
    if played == 0:
        return hist[-1]
    m = len(hist)
    window = min(m, 101)                       # production trims the list to 101 values
    last = lambda k: (cs[m] - cs[m - min(k, window)]) / min(k, window)
    r30, r100 = last(30), last(100)
    st = 0.6 * hist[-1] + 0.2 * last(3) + 0.1 * r30 + 0.1 * r100
    return 0.1 * st + 0.3 * r30 + 0.6 * r100


def replay(data, settings=None, hook=None):
    """Replay every fixture in order. settings overrides PRODUCTION. hook, when given, is an
    object with before(i, home, away, h, a) -> (h, a) ranks to predict and update from, and
    after(i, home, away, change, surprise) -> None, for experiments that add state to the
    replay; with no hook this is production's ranking.run."""
    s = {**PRODUCTION, **(settings or {})}
    start, _, _ = starting_ranks(data, s["default_start"])
    cur, hist, sums = {}, {}, {}
    out = Replay(data.n)
    hfa, k0, kx, cap, gw = s["home_advantage"], s["k"], s["k_xg"], s["max_goal_diff"], s["goals_weight"]
    home, away, hg, ag, hx, ax, lg = (data.home, data.away, data.home_goals, data.away_goals,
                                      data.home_xg, data.away_xg, data.league)
    for i in range(data.n):
        th, ta = home[i], away[i]
        for t in (th, ta):
            if t not in cur:
                cur[t] = start[t]
                hist[t] = [cur[t]]
                sums[t] = [0.0, cur[t]]
        h, a = cur[th], cur[ta]
        out.h_now[i], out.a_now[i] = h, a
        out.h_lt[i], out.a_lt[i] = _lt(hist[th], sums[th]), _lt(hist[ta], sums[ta])
        out.h_played[i], out.a_played[i] = len(hist[th]) - 1, len(hist[ta]) - 1
        if hook is not None:
            adj = hook.before(i, th, ta, h, a)
            if adj is not None:
                out.h_now[i] += adj[0]
                out.a_now[i] += adj[1]
                out.h_lt[i] += adj[0]
                out.a_lt[i] += adj[1]
                h_eff, a_eff = h + adj[0], a + adj[1]
            else:
                h_eff, a_eff = h, a
        else:
            h_eff, a_eff = h, a
        exp_diff = (h_eff - a_eff + hfa) / 100
        capped = max(-cap, min(cap, hg[i] - ag[i]))
        if math.isnan(hx[i]) or math.isnan(ax[i]):
            result, k = capped, k0
        else:
            result, k = gw * capped + (1 - gw) * (hx[i] - ax[i]), kx
        weight = COMPETITION_WEIGHT.get(lg[i], 1.0)
        surprise = result - exp_diff
        kh = ka = k
        if hook is not None:
            scale = hook.k_scale(i, th, ta)
            if scale is not None:
                kh, ka = k * scale[0], k * scale[1]
        cur[th], cur[ta] = h + surprise * kh * weight, a - surprise * ka * weight
        for t in (th, ta):
            hist[t].append(cur[t])
            sums[t].append(sums[t][-1] + cur[t])
        if hook is not None:
            hook.after(i, th, ta, surprise, k * weight)
    out.current = cur
    return out


# ---- the probability step (predictions.outcome_probabilities, goal_lines), on arrays ----------

_K = np.arange(MAX_GOALS + 1)
_LOGFACT = np.array([math.lgamma(k + 1) for k in _K])


def pmf(lam):
    lam = np.maximum(np.asarray(lam, dtype=float), 0.01)[:, None]
    return np.exp(-lam + _K * np.log(lam) - _LOGFACT)


def grid(home_xg, away_xg):
    """(n, 11, 11) score probabilities from two independent Poisson rates, truncated at 10 goals
    and rescaled to one, as production does."""
    ph, pa = pmf(home_xg), pmf(away_xg)
    g = ph[:, :, None] * pa[:, None, :]
    return g / g.sum(axis=(1, 2), keepdims=True)


_LOWER = np.tril(np.ones((MAX_GOALS + 1, MAX_GOALS + 1)), -1)      # home goals > away goals
_TOTAL = _K[:, None] + _K[None, :]


def outcomes_from_grid(g, exp_diff, inflation=DRAW_INFLATION, fade=DRAW_FADE_MARGIN):
    """(n, 3) home, draw, away with the draw boost."""
    home = (g * _LOWER).sum(axis=(1, 2))
    draw = np.einsum("nii->n", g)
    away = 1 - home - draw
    boost = 1 + (inflation - 1) * np.maximum(0.0, 1 - np.abs(exp_diff) / fade)
    draw_adj = np.minimum(draw * boost, 0.9)
    scale = (1 - draw_adj) / (home + away)
    return np.stack([home * scale, draw_adj, away * scale], axis=1)


def outcome_probabilities(home_xg, away_xg, inflation=DRAW_INFLATION, fade=DRAW_FADE_MARGIN):
    home_xg, away_xg = np.asarray(home_xg, dtype=float), np.asarray(away_xg, dtype=float)
    return outcomes_from_grid(grid(home_xg, away_xg), home_xg - away_xg, inflation, fade)


def goal_markets_from_grid(g, calibrated=True):
    """(n, 5): P(over 1.5), P(over 2.5), P(over 3.5), P(over 4.5), P(both score), with
    production's calibration towards a base rate unless calibrated=False."""
    out = []
    for line in (1.5, 2.5, 3.5, 4.5):
        over = (g * (_TOTAL > line)).sum(axis=(1, 2))
        if calibrated:
            base, shrink = OVER25 if line == 2.5 else GOAL_LINE_CALIBRATION[line]
            over = base + shrink * (over - base)
            if line != 2.5:
                over = np.clip(over, 0.005, 0.995)
        out.append(over)
    btts = g[:, 1:, 1:].sum(axis=(1, 2))
    if calibrated:
        btts = BTTS[0] + BTTS[1] * (btts - BTTS[0])
    out.append(btts)
    return np.stack(out, axis=1)


def goal_markets(home_xg, away_xg):
    return goal_markets_from_grid(grid(np.asarray(home_xg, float), np.asarray(away_xg, float)))


GOAL_MARKETS = ("over15", "over25", "over35", "over45", "btts")


def goal_events(data, rows):
    total = data.ft_home[rows] + data.ft_away[rows]
    return np.stack([total > 1.5, total > 2.5, total > 3.5, total > 4.5,
                     (data.ft_home[rows] > 0) & (data.ft_away[rows] > 0)], axis=1)


def moved(home_xg, away_xg, by):
    """Projected goals with the expected margin moved by `by` goals and the product of the two
    kept: what predictions.project returns for the new margin from the same base goals."""
    d = home_xg - away_xg + by
    home = (d + np.sqrt(d * d + 4 * home_xg * away_xg)) / 2
    return home, home - d


def reprojected(data, rep, settings=None):
    """Projected goals of every fixture when its ranks come from `rep`: the stored projection
    with the rank term of the expected margin swapped for the replayed one and everything else
    in it (injuries, line-ups, home edges, the European bonus) kept as stored."""
    s = {**PRODUCTION, **(settings or {})}
    h, a = rep.match_rank(s["now_weight"])
    new_gap = (h - a + s["home_advantage"]) / 100
    old_gap = (data.pred["home_rank"] - data.pred["away_rank"] + PRODUCTION["home_advantage"]) / 100
    return moved(data.pred["home_xg"], data.pred["away_xg"], new_gap - old_gap)


# ---- measures --------------------------------------------------------------------------------

def log_loss(p, result):
    return -np.log(np.clip(p[np.arange(len(result)), result], 1e-15, 1.0))


def brier(p, result):
    y = np.eye(3)[result]
    return ((p - y) ** 2).sum(axis=1)


def rps(p, result):
    """Ranked probability score over home / draw / away (lower is better)."""
    y = np.eye(3)[result]
    c = np.cumsum(p, axis=1)[:, :2] - np.cumsum(y, axis=1)[:, :2]
    return (c ** 2).sum(axis=1) / 2


def binary_log_loss(p, event):
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return -np.where(event, np.log(p), np.log(1 - p))


def calibration_error(p, result, bands=10):
    """Per outcome, the match-weighted |mean predicted - observed| over ten equal bands,
    averaged over the three outcomes (as experiments/ends_and_draws defines it)."""
    total = 0.0
    for k in range(3):
        band = np.minimum((p[:, k] * bands).astype(int), bands - 1)
        gap = 0.0
        for b in range(bands):
            m = band == b
            if m.any():
                gap += abs(p[m, k].sum() - (result[m] == k).sum())
        total += gap / len(result)
    return total / 3


def calibration_slope(p, result):
    """The one-number sharpness check: the power a that minimises the log loss of p ** a
    rescaled. 1 means neither too flat nor too sharp; above 1 means too flat."""
    logp = np.log(np.clip(p, 1e-12, 1))
    best, best_loss = 1.0, None
    for a in np.arange(0.70, 1.41, 0.01):
        z = a * logp
        z = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
        loss = -z[np.arange(len(result)), result].mean()
        if best_loss is None or loss < best_loss:
            best, best_loss = float(a), loss
    return round(best, 2)


def cluster_sums(values, clusters):
    """Sum of each column of values within each cluster: (unique clusters, sums)."""
    keys, inv = np.unique(clusters, return_inverse=True)
    values = np.asarray(values, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    sums = np.zeros((len(keys), values.shape[1]))
    np.add.at(sums, inv, values)
    counts = np.bincount(inv, minlength=len(keys)).astype(float)
    return keys, sums, counts


def paired_interval(diff, clusters, level=0.95, draws=DRAWS, seed=SEED):
    """Mean of a per-match difference with a bootstrap interval that resamples whole clusters
    (ISO weeks). level is the coverage: pass 1 - 0.05 / m for a family of m comparisons."""
    _, sums, counts = cluster_sums(diff, clusters)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(counts), size=(draws, len(counts)))
    means = sums[pick, 0].sum(axis=1) / counts[pick].sum(axis=1)
    lo, hi = np.quantile(means, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(np.mean(diff)), float(lo), float(hi)


def summary(p, result):
    return {"n": int(len(result)), "log_loss": float(log_loss(p, result).mean()),
            "brier": float(brier(p, result).mean()), "rps": float(rps(p, result).mean()),
            "accuracy": float((p.argmax(axis=1) == result).mean()),
            "calibration_error": float(calibration_error(p, result)),
            "sharpness_power": calibration_slope(p, result)}


def compare(data, rows, p_base, p_cand, level=0.95):
    """Candidate against baseline on the same rows (boolean mask over the fixtures; the two
    probability arrays are already cut to those rows)."""
    result, weeks = data.result[rows], data.week[rows]
    out = {"baseline": summary(p_base, result), "candidate": summary(p_cand, result), "level": level}
    for name, fn in (("log_loss", log_loss), ("brier", brier), ("rps", rps)):
        d = fn(p_cand, result) - fn(p_base, result)
        out[name] = paired_interval(d, weeks, level)
    d = log_loss(p_cand, result) - log_loss(p_base, result)
    seasons = data.season[rows]
    out["by_season"] = {data.season_label(s): {"n": int((seasons == s).sum()),
                                               "log_loss": float(d[seasons == s].mean())}
                        for s in np.unique(seasons)}
    leagues = data.league[rows]
    by = {}
    for lg in np.unique(leagues):
        m = leagues == lg
        if m.sum() >= 300:
            by[int(lg)] = {"name": data.leagues[lg]["name"], "country": data.leagues[lg]["country"],
                           "type": data.leagues[lg]["type"], "n": int(m.sum()), "log_loss": float(d[m].mean())}
    out["by_competition"] = by
    out["competitions_no_worse"] = [sum(v["log_loss"] <= 0 for v in by.values()), len(by)]
    kinds = data.is_league[rows]
    out["leagues"] = {"n": int(kinds.sum()), "log_loss": float(d[kinds].mean())}
    out["cups"] = {"n": int((~kinds).sum()), "log_loss": float(d[~kinds].mean())}
    return out


def baseline_probabilities(data, rows):
    """Production's result probabilities from the stored projected goals."""
    return outcome_probabilities(data.pred["home_xg"][rows], data.pred["away_xg"][rows])


def reproduction(data):
    """How closely this file's copies give back what production stored."""
    rows = data.scored
    p = baseline_probabilities(data, rows)
    stored = np.stack([data.pred[k][rows] for k in ("p_home", "p_draw", "p_away")], axis=1)
    rep = replay(data)
    h, a = rep.match_rank()
    back = (data.pred_source == "backfill") & rows
    dh, da = np.abs(h - data.pred["home_rank"])[back], np.abs(a - data.pred["away_rank"])[back]
    gm = goal_markets(data.pred["home_xg"][rows], data.pred["away_xg"][rows])
    return {
        "scored": int(rows.sum()),
        "probabilities_largest_difference": float(np.abs(p - stored).max()),
        "probabilities_within_1e-6": float((np.abs(p - stored).max(axis=1) < 1e-6).mean()),
        "over25_largest_difference": float(np.nanmax(np.abs(gm[:, 1] - data.pred["p_over25"][rows]))),
        "btts_largest_difference": float(np.nanmax(np.abs(gm[:, 4] - data.pred["p_btts"][rows]))),
        "reconstructed_rows": int(back.sum()),
        "match_rank_within_0.01": float(((dh < 0.01) & (da < 0.01)).mean()),
        "match_rank_within_1": float(((dh < 1) & (da < 1)).mean()),
        "match_rank_median_difference": float(np.median(np.concatenate([dh, da]))),
        "match_rank_largest_difference": float(max(dh.max(), da.max())),
    }


if __name__ == "__main__":
    d = Data()
    print(json.dumps(reproduction(d), indent=1))
    print("development", int(d.development.sum()), "final", int(d.final.sum()))
