"""Fantasy v1 backtest (DESIGN.md): chronological replay, fit on train, select on validation,
refit on train + validation, test once. Offline: reads the frozen extract, writes results.json
and a local snapshot archive. Never touches the database."""
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import gzip
import hashlib
import json
import math
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from scipy.stats import spearmanr
from thecornerfc.fantasy_games import fantasy as fm
from thecornerfc.evidence.model_versions import version_metadata

ROOT = Path(__file__).parent
INPUTS = Path('.cache/fantasy_v1_inputs.json.gz')
SNAPSHOTS = Path('.cache/fantasy_v1_snapshots.jsonl.gz')
PARAMS = Path('thecornerfc/fantasy_games/fantasy_params.json')
TRAIN, VAL, TEST = datetime.fromisoformat('2021-07-01T00:00:00+00:00'), \
    datetime.fromisoformat('2023-07-01T00:00:00+00:00'), datetime.fromisoformat('2024-07-01T00:00:00+00:00')
DECAYS, KS = (0.5, 0.7, 0.85), (450, 900, 1800)
FINISHED = {'FT', 'AET', 'PEN'}
SEED, DRAWS = 20260927, 2000
LINE = ('fid', 'team', 'pid', 'minutes', 'started', 'position', 'role', 'goals', 'assists', 'shots', 'shots_on',
        'key_passes', 'saves', 'gc', 'pens_saved', 'yellow', 'red')
COUNTS = ('goals', 'assists', 'shots', 'shots_on', 'key_passes', 'saves', 'pens_saved', 'yellow', 'red')
SAVE_TOLERANCE = 0.10
TOP_N = (10, 25, 50)
POSITION_TOP = {'G': 5, 'D': 10, 'M': 10, 'F': 5}


def ts(s):
    return datetime.fromisoformat(s)


# ---- Replay: pre-match sufficient statistics for every universe player-fixture ----

def replay(d):
    fixtures = [dict(zip(('fid', 'season', 'round', 'kickoff', 'status', 'home', 'away', 'hg', 'ag'), r))
                for r in d['fixtures']]
    for f in fixtures:
        f['kickoff'] = ts(f['kickoff'])
    lines = defaultdict(dict)
    for r in d['players']:
        line = dict(zip(LINE, r))
        for k in COUNTS:
            line[k] = line[k] or 0
        lines[line['fid']].setdefault(line['team'], {})[line['pid']] = line
    fx = {f['fid']: f for f in fixtures}

    counts = defaultdict(Counter)
    for fid, teams in lines.items():
        for team_lines in teams.values():
            for line in team_lines.values():
                if line['minutes'] > 0 and line['position'] in fm.GOAL_POINTS:
                    counts[(line['pid'], fx[fid]['season'])][line['position']] += 1
    by_player = defaultdict(dict)
    for (pid, season), c in counts.items():
        by_player[pid][season] = c.most_common(1)[0][0]

    def label(pid, season):
        """Season position (most appearances); earlier seasons for a player without one yet."""
        seasons = by_player.get(pid, {})
        for s in sorted(seasons, reverse=True):
            if s <= season:
                return seasons[s]
        return min(seasons.items())[1] if seasons else None

    apps = defaultdict(list)
    for fid, teams in lines.items():
        for team, team_lines in teams.items():
            for line in team_lines.values():
                if line['minutes'] > 0:
                    apps[line['pid']].append((fx[fid]['kickoff'], team))
    for pid, team, kickoff in d['elsewhere']:
        apps[pid].append((ts(kickoff), team))
    for v in apps.values():
        v.sort()
    app_keys = {p: [a[0] for a in v] for p, v in apps.items()}

    lam = {fid: (hx, ax, src) for fid, hx, ax, src in d['predictions'] if hx is not None}
    prospective = {}
    for fid, captured, created, effective, hx, ax, _ in d['prospective']:
        captured, created, effective = ts(captured), ts(created), ts(effective)
        if captured < effective and created < effective and hx is not None:
            if fid not in prospective or captured > prospective[fid][0]:
                prospective[fid] = (captured, hx, ax)
    for fid, (_, hx, ax) in prospective.items():
        lam[fid] = (hx, ax, 'prospective')
    injuries = {(fid, pid): kind for fid, _, pid, kind in d['injuries']}
    saves = {(fid, team): s for fid, team, s in d['team_saves']}
    ranks = defaultdict(list)
    for fid, pid, rank in d['ranks']:
        if fid in fx and rank is not None:
            ranks[pid].append((fx[fid]['kickoff'], rank))
    for v in ranks.values():
        v.sort()

    team_hist = defaultdict(list)
    pl_apps = defaultdict(list)        # league appearances as fm.player_features expects them
    season_pts = defaultdict(lambda: [0.0, 0])
    rows, teams_out, outside = [], [], []
    played = [f for f in fixtures if f['status'] in FINISHED and f['hg'] is not None and f['fid'] in lines]
    for f in played:
        k, fid, season = f['kickoff'], f['fid'], f['season']
        fl = lines[fid]
        for team, opp, is_home in ((f['home'], f['away'], True), (f['away'], f['home'], False)):
            conceded = f['ag'] if is_home else f['hg']
            scored = f['hg'] if is_home else f['ag']
            hx, ax, src = lam.get(fid, (None, None, None))
            lam_for, lam_against = (hx, ax) if is_home else (ax, hx)
            actual_team = fl.get(team, {})
            teams_out.append(dict(fid=fid, team=team, kickoff=k, season=season, lam_for=lam_for,
                                  lam_against=lam_against, conceded=conceded, scored=scored, is_home=is_home,
                                  saves=saves.get((fid, team)), lam_source=src,
                                  player_goals=sum(l['goals'] for l in actual_team.values()),
                                  player_assists=sum(l['assists'] for l in actual_team.values()),
                                  shots_on=sum(l['shots_on'] for l in actual_team.values()),
                                  key_passes=sum(l['key_passes'] for l in actual_team.values())))
            hist = team_hist[team]
            recent = [h for h in hist if h[0] >= k - fm.WINDOW]
            team_recent = [{p: (l['started'], l['minutes']) for p, l in h[2].items()} for h in recent]
            latest = {}
            for pid in {p for m in team_recent for p in m}:
                i = bisect_left(app_keys[pid], k) - 1
                if i >= 0:
                    latest[pid] = apps[pid][i][1]
            universe = fm.universe(team, team_recent, latest)
            for pid in universe:
                position = label(pid, season)
                if position is None:
                    continue
                feats = fm.player_features(pid, k, team_recent, pl_apps[pid])
                feats['group'] = feats['group'] or fm.POSITION_GROUPS[position]
                ri = bisect_left([r[0] for r in ranks[pid]], k) - 1
                line = actual_team.get(pid)
                minutes = line['minutes'] if line else 0
                pts = fm.actual_points(position, minutes, *(
                    (line['goals'], line['assists'], conceded, line['saves'], line['pens_saved'], line['yellow'], line['red'])
                    if line else (0, 0, conceded)))
                cur, prev = season_pts[(pid, season)], season_pts[(pid, season - 1)]
                last5 = hist[-5:]
                rows.append(dict(
                    fid=fid, team=team, pid=pid, season=season, round=f['round'], kickoff=k, is_home=is_home,
                    position=position, **feats,
                    injury=injuries.get((fid, pid)), rank=ranks[pid][ri][1] if ri >= 0 else None,
                    lam_for=lam_for, lam_against=lam_against, lam_source=src, conceded=conceded,
                    minutes=minutes, started=bool(line and line['started'] and minutes > 0),
                    goals=line['goals'] if line else 0, assists=line['assists'] if line else 0,
                    gk_saves=line['saves'] if line else 0, **{f'actual_{k2}': v for k2, v in pts.items()},
                    ppg=cur[0] / cur[1] if cur[1] else prev[0] / prev[1] if prev[1] else 0.0,
                    recent5=sum(h[2][pid]['_pts'] if pid in h[2] and '_pts' in h[2][pid] else 0 for h in last5)
                    / len(last5) if last5 else 0.0,
                    recent5_min=sum(h[2][pid]['minutes'] if pid in h[2] else 0 for h in last5) / len(last5)
                    if last5 else 0.0))
            inside = set(universe)
            for pid, line in actual_team.items():
                if line['minutes'] > 0 and pid not in inside:
                    position = label(pid, season)
                    outside.append((season, k, fm.actual_points(position, line['minutes'], line['goals'], line['assists'],
                                                                 conceded, line['saves'], line['pens_saved'],
                                                                 line['yellow'], line['red'])['total']))
        # update state with this fixture, after both sides are predicted
        for team, is_home in ((f['home'], True), (f['away'], False)):
            team_lines = fl.get(team, {})
            conceded = f['ag'] if is_home else f['hg']
            totals = tuple(sum(l[c] for l in team_lines.values()) for c in ('goals', 'shots_on', 'assists', 'key_passes'))
            for pid, line in team_lines.items():
                if line['minutes'] <= 0:
                    continue
                m = line['minutes']
                pl_apps[pid].append((k, bool(line['started']), m, line['role'], line['goals'], line['shots_on'],
                                     line['assists'], line['key_passes'], *totals))
                position = label(pid, f['season'])
                line['_pts'] = fm.actual_points(position, m, line['goals'], line['assists'], conceded, line['saves'],
                                                line['pens_saved'], line['yellow'], line['red'])['total']
                sp = season_pts[(pid, f['season'])]
                sp[0] += line['_pts']
                sp[1] += 1
            team_hist[team].append((k, fid, team_lines))
    return rows, teams_out, outside


# ---- Fitting ----

def split_of(k):
    return None if k < TRAIN else 'train' if k < VAL else 'validation' if k < TEST else 'test'


def fit_logistic(X, y, ridge=1e-3):
    beta = np.zeros(X.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ beta))
        W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + ridge * np.eye(X.shape[1])
        step = np.linalg.solve(H, X.T @ (y - p) - ridge * beta)
        beta += step
        if np.abs(step).max() < 1e-9:
            break
    return beta


def minute_matrices(rows, decay, availability=False):
    Xs, Xb = [], []
    for r in rows:
        s, b = fm.minutes_features(r['history'], r['gap'], decay)
        if availability:
            extra = [float(r['injury'] == fm.MISSING), float(r['injury'] == fm.DOUBTFUL)]
            s, b = s + extra, b + extra
        Xs.append(s)
        Xb.append(b)
    return np.array(Xs), np.array(Xb)


def fit(rows, teams, fixtures_rows, decay, K, availability=False):
    """All v1 parameters from the rows / team-matches in `fixtures_rows` (a boolean mask)."""
    fr = [r for r, m in zip(rows, fixtures_rows) if m]
    Xs, Xb = minute_matrices(fr, decay, availability)
    ys = np.array([r['started'] for r in fr], float)
    bench = ys == 0
    yb = np.array([r['minutes'] > 0 for r in fr], float)[bench]
    start_rows = [r for r in fr if r['started']]
    sub_rows = [r for r in fr if r['minutes'] > 0 and not r['started']]
    pos_prior = {p: {'start_min': float(np.mean([r['minutes'] for r in start_rows if r['position'] == p])),
                     'start_p60': float(np.mean([r['minutes'] >= 60 for r in start_rows if r['position'] == p])),
                     'sub_min': float(np.mean([r['minutes'] for r in sub_rows if r['position'] == p]))}
                 for p in fm.GOAL_POINTS}
    splits = {r['split'] for r, m in zip(rows, fixtures_rows) if m}
    ft = [t for t in teams if t['split'] in splits]
    team_goals = sum(t['scored'] for t in ft)
    c_g = sum(t['player_goals'] for t in ft) / sum(t['shots_on'] for t in ft)
    c_a = sum(t['player_assists'] for t in ft) / sum(t['key_passes'] for t in ft)
    e_g = np.mean([.5 * t['player_goals'] + .5 * c_g * t['shots_on'] for t in ft])
    e_a = np.mean([.5 * t['player_assists'] + .5 * c_a * t['key_passes'] for t in ft])
    priors = {}
    for g in set(fm.ROLE_GROUPS.values()):
        gr = [r for r in fr if r['group'] == g and r['att_min'] > 0]
        priors[g] = (sum(.5 * r['g'] + .5 * c_g * r['sot'] for r in gr) / sum(.5 * r['tg'] + .5 * c_g * r['tsot'] for r in gr),
                     sum(.5 * r['a'] + .5 * c_a * r['kp'] for r in gr) / sum(.5 * r['ta'] + .5 * c_a * r['tkp'] for r in gr))
    st = [t for t in ft if t['saves'] is not None and t['lam_against'] is not None]
    A = np.column_stack([np.ones(len(st)), [t['lam_against'] for t in st]])
    save_ab = np.linalg.lstsq(A, np.array([t['saves'] for t in st], float), rcond=None)[0]
    return dict(decay=decay, K=K, availability=availability,
                start_beta=fit_logistic(Xs, ys).tolist(), sub_beta=fit_logistic(Xb[bench], yb).tolist(),
                position_priors=pos_prior, sub_p60=float(np.mean([r['minutes'] >= 60 for r in sub_rows])),
                goals_per_shot_on=c_g, assists_per_key_pass=c_a, team_goal_evidence=float(e_g),
                team_assist_evidence=float(e_a), role_priors=priors,
                own_goal_share=1 - sum(t['player_goals'] for t in ft) / team_goals,
                assists_per_goal=sum(t['player_assists'] for t in ft) / team_goals,
                save_intercept=float(save_ab[0]), save_slope=float(save_ab[1]),
                flat_lambda={'home': float(np.mean([t['scored'] for t in ft if t['is_home']])),
                             'away': float(np.mean([t['scored'] for t in ft if not t['is_home']]))})


def predict(rows, params, flat=False, saves=True):
    """Every component for every row, with the production function fm.predict_team."""
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r['fid'], r['team'])].append(i)
    preds = [None] * len(rows)
    for idx in groups.values():
        r0 = rows[idx[0]]
        lam_for, lam_against = r0['lam_for'], r0['lam_against']
        if flat:
            lam_for = params['flat_lambda']['home' if r0['is_home'] else 'away']
            lam_against = params['flat_lambda']['away' if r0['is_home'] else 'home']
        for i, p in zip(idx, fm.predict_team([rows[i] for i in idx], lam_for, lam_against, params, saves)):
            preds[i] = p
    return preds


# ---- Metrics ----

def point_metrics(pred, actual):
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    err = pred - actual
    return {'n': int(len(pred)), 'mae': float(np.abs(err).mean()), 'rmse': float(np.sqrt((err ** 2).mean())),
            'pearson': float(np.corrcoef(pred, actual)[0, 1]) if pred.std() > 0 else None,
            'spearman': float(spearmanr(pred, actual).statistic) if pred.std() > 0 else None,
            'mean_pred': float(pred.mean()), 'mean_actual': float(actual.mean()),
            'bias_pct': float(err.mean() / actual.mean() * 100) if actual.mean() else None}


def calibration(p, y, bins=10):
    p, y = np.asarray(p, float), np.asarray(y, float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    table, ece = [], 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            table.append({'bin': f'{b / bins:.1f}-{(b + 1) / bins:.1f}', 'n': int(m.sum()),
                          'mean_p': float(p[m].mean()), 'rate': float(y[m].mean())})
            ece += m.sum() / len(p) * abs(p[m].mean() - y[m].mean())
    return {'n': int(len(p)), 'ece': float(ece), 'brier': float(((p - y) ** 2).mean()),
            'mean_p': float(p.mean()), 'rate': float(y.mean()), 'bins': table}


def paired_bootstrap(errors_a, errors_b, clusters, rng):
    """95% interval of mean(errors_a) - mean(errors_b), resampling (season, round) clusters."""
    diff = np.asarray(errors_a) - np.asarray(errors_b)
    keys, inv = np.unique(clusters, return_inverse=True)
    sums, ns = np.bincount(inv, diff), np.bincount(inv)
    draws = rng.integers(0, len(keys), (DRAWS, len(keys)))
    boot = sums[draws].sum(1) / ns[draws].sum(1)
    return {'diff': float(diff.mean()), 'lo': float(np.percentile(boot, 2.5)), 'hi': float(np.percentile(boot, 97.5))}


def top_n(rows, scores, rng):
    """Per round: share of the predicted top N whose actual points reach the actual N-th best,
    and their mean actual points; overall and by position."""
    rounds = defaultdict(list)
    for i, r in enumerate(rows):
        rounds[(r['season'], r['round'])].append(i)
    out = {}
    for name, score in scores.items():
        s = np.asarray(score, float) + rng.uniform(0, 1e-9, len(rows))    # break ties at random
        res = {}
        for label, pos, n in [(f'top{n}', None, n) for n in TOP_N] + [(f'{p}_top{n}', p, n) for p, n in POSITION_TOP.items()]:
            hits, pts = [], []
            for idx in rounds.values():
                idx = [i for i in idx if pos is None or rows[i]['position'] == pos]
                if len(idx) < n:
                    continue
                act = np.array([rows[i]['actual_total'] for i in idx], float)
                chosen = np.argsort(-s[idx])[:n]
                threshold = np.sort(act)[-n]
                hits.append(float((act[chosen] >= threshold).mean()))
                pts.append(float(act[chosen].mean()))
            res[label] = {'hit_rate': float(np.mean(hits)), 'mean_points': float(np.mean(pts)), 'rounds': len(hits)}
        out[name] = res
    return out


def ability_band(rank):
    if rank is None:
        return 'unrated'
    return '<60' if rank < 60 else '60-70' if rank < 70 else '70-80' if rank < 80 else '80+'


def round_bucket(round_name):
    n = int(round_name.rsplit('-', 1)[-1])
    return '1-5' if n <= 5 else '6-19' if n <= 19 else '20-38'


def evaluate(rows, preds, extra_preds, rng, include_top=True):
    actual = [r['actual_total'] for r in rows]
    model = [p['expected_points'] for p in preds]
    candidates = {'model': model, 'ppg': [r['ppg'] for r in rows], 'recent5': [r['recent5'] for r in rows],
                  **{k: [p['expected_points'] for p in v] for k, v in extra_preds.items()}}
    clusters = np.array([f"{r['season']}|{r['round']}" for r in rows])
    res = {'overall': {k: point_metrics(v, actual) for k, v in candidates.items()},
           'v1_scope': point_metrics(model, [r['actual_v1'] for r in rows])}
    abs_err = {k: np.abs(np.asarray(v) - actual) for k, v in candidates.items()}
    sq_err = {k: (np.asarray(v) - actual) ** 2 for k, v in candidates.items()}
    res['vs'] = {k: {'mae': paired_bootstrap(abs_err['model'], abs_err[k], clusters, rng),
                     'mse': paired_bootstrap(sq_err['model'], sq_err[k], clusters, rng)}
                 for k in candidates if k != 'model'}
    reg = np.array([sum(h[0] for h in r['history'][:5]) >= 3 for r in rows])
    res['vs_regulars'] = {k: {'mae': paired_bootstrap(abs_err['model'][reg], abs_err[k][reg], clusters[reg], rng),
                              'mse': paired_bootstrap(sq_err['model'][reg], sq_err[k][reg], clusters[reg], rng)}
                          for k in candidates if k != 'model'}
    keys, inv = np.unique(clusters, return_inverse=True)
    res['round_wins'] = {k: {'rounds': int(len(keys)), 'model_lower_mae': int(
        (np.bincount(inv, abs_err['model']) < np.bincount(inv, abs_err[k])).sum())} for k in candidates if k != 'model'}
    segments = {'position': lambda r: r['position'], 'ability_band': lambda r: ability_band(r['rank']),
                'round_bucket': lambda r: round_bucket(r['round']), 'season': lambda r: str(r['season']),
                'lambda_source': lambda r: r['lam_source'] or 'none',
                'gameweek': lambda r: r['round'].rsplit('-', 1)[-1].strip(),
                'regular': lambda r: 'regular' if sum(h[0] for h in r['history'][:5]) >= 3 else 'other'}
    res['segments'] = {}
    for seg, key in segments.items():
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            groups[key(r)].append(i)
        res['segments'][seg] = {g: {k: point_metrics([v[i] for i in idx], [actual[i] for i in idx])
                                    for k, v in candidates.items()}
                                for g, idx in sorted(groups.items(), key=lambda kv: (len(kv[0]), kv[0]))}
        if seg == 'position':
            for g, idx in groups.items():
                res['segments'][seg][g]['v1_scope'] = point_metrics([model[i] for i in idx], [rows[i]['actual_v1'] for i in idx])
    if include_top:
        res['top_n'] = top_n(rows, candidates, rng)
    # minutes, starts, clean sheets, components
    mins = np.array([p['exp_minutes'] for p in preds])
    act_min = np.array([r['minutes'] for r in rows], float)
    rec_min = np.array([r['recent5_min'] for r in rows])
    res['minutes'] = {'mae': float(np.abs(mins - act_min).mean()),
                      'recent5_mae': float(np.abs(rec_min - act_min).mean()),
                      'rmse': float(np.sqrt(((mins - act_min) ** 2).mean())),
                      'recent5_rmse': float(np.sqrt(((rec_min - act_min) ** 2).mean())),
                      'recent5_mean': float(rec_min.mean()),
                      'mean_pred': float(mins.mean()), 'mean_actual': float(act_min.mean()),
                      'by_position': {pos: {'mae': float(np.abs(mins[m] - act_min[m]).mean()),
                                            'recent5_mae': float(np.abs(np.array([r['recent5_min'] for r in rows])[m] - act_min[m]).mean())}
                                      for pos in fm.GOAL_POINTS
                                      for m in [np.array([r['position'] == pos for r in rows])]}}
    res['start_calibration'] = calibration([p['p_start'] for p in preds], [r['started'] for r in rows])
    res['play_calibration'] = calibration([p['p_play'] for p in preds], [r['minutes'] > 0 for r in rows])
    res['p60_calibration'] = calibration([p['p60'] for p in preds], [r['minutes'] >= 60 for r in rows])
    gd = [i for i, r in enumerate(rows) if r['position'] in 'GD']
    res['player_cs_calibration'] = calibration([preds[i]['p_clean_sheet'] for i in gd],
                                               [rows[i]['minutes'] >= 60 and rows[i]['conceded'] == 0 for i in gd])
    res['components'] = {c: {'mean_pred': float(np.mean([p[c] for p in preds])),
                             'mean_actual': float(np.mean([r['actual_' + c] for r in rows]))}
                         for c in fm.COMPONENT_POINTS}
    res['components']['exp_goals'] = {'mean_pred': float(np.mean([p['exp_goals'] for p in preds])),
                                      'mean_actual': float(np.mean([r['goals'] for r in rows]))}
    res['components']['exp_assists'] = {'mean_pred': float(np.mean([p['exp_assists'] for p in preds])),
                                        'mean_actual': float(np.mean([r['assists'] for r in rows]))}
    for c, act in (('exp_goals', 'goals'), ('exp_assists', 'assists')):
        res['components'][c]['by_position'] = {
            pos: {'mean_pred': float(np.mean([preds[i][c] for i in idx])), 'mean_actual': float(np.mean([rows[i][act] for i in idx])),
                  'pearson': float(np.corrcoef([preds[i][c] for i in idx], [rows[i][act] for i in idx])[0, 1])}
            for pos in fm.GOAL_POINTS for idx in [[i for i, r in enumerate(rows) if r['position'] == pos]]}
    return res


def team_checks(teams, params, split):
    t = [x for x in teams if x['split'] == split and x['lam_against'] is not None]
    lam = np.array([x['lam_against'] for x in t])
    cs = calibration(np.exp(-lam), [x['conceded'] == 0 for x in t])
    sv = [x for x in t if x['saves'] is not None]
    mu = np.maximum(params['save_intercept'] + params['save_slope'] * np.array([x['lam_against'] for x in sv]), 0.1)
    act = np.array([x['saves'] for x in sv], float)
    cuts = np.quantile(mu, [1 / 3, 2 / 3])
    terciles = []
    for lo, hi in zip([-np.inf, *cuts], [*cuts, np.inf]):
        m = (mu > lo) & (mu <= hi)
        terciles.append({'n': int(m.sum()), 'mean_pred': float(mu[m].mean()), 'mean_actual': float(act[m].mean())})
    goals = np.array([x['lam_for'] for x in t])
    return {'team_clean_sheet': cs, 'saves_terciles': terciles,
            'saves_ok': all(abs(x['mean_pred'] / x['mean_actual'] - 1) <= SAVE_TOLERANCE for x in terciles),
            'team_goals': {'mean_lambda': float(goals.mean()), 'mean_goals': float(np.mean([x['scored'] for x in t])),
                           'corr': float(np.corrcoef(goals, [x['scored'] for x in t])[0, 1])}}


def lineup_comparison(d, rows, preds):
    """2026/27: the lineup model's prospective predicted XI against v1's P(start), same rows."""
    predicted = {}
    for fid, team, captured, effective, players in d['lineup_snapshots']:
        if ts(captured) < ts(effective):
            key = (fid, team)
            if key not in predicted or ts(captured) > predicted[key][0]:
                predicted[key] = (ts(captured), {p['player'] for p in players if p.get('predicted_starter')})
    idx = [i for i, r in enumerate(rows) if (r['fid'], r['team']) in predicted]
    if not idx:
        return None
    y = np.array([rows[i]['started'] for i in idx], float)
    lineup = np.array([rows[i]['pid'] in predicted[(rows[i]['fid'], rows[i]['team'])][1] for i in idx], float)
    ps = np.array([preds[i]['p_start'] for i in idx])
    return {'rows': len(idx), 'team_fixtures': len({(rows[i]['fid'], rows[i]['team']) for i in idx}),
            'lineup_accuracy': float((lineup == y).mean()), 'v1_accuracy': float(((ps >= .5) == y).mean()),
            'lineup_brier': float(((lineup - y) ** 2).mean()), 'v1_brier': float(((ps - y) ** 2).mean())}


def main():
    raw = gzip.decompress(INPUTS.read_bytes())
    d = json.loads(raw)
    rows, teams, outside = replay(d)
    for r in rows:
        r['split'] = split_of(r['kickoff'])
    for t in teams:
        t['split'] = split_of(t['kickoff'])
    rows = [r for r in rows if r['split'] and r['lam_for'] is not None]
    rng = np.random.default_rng(SEED)
    split = lambda names: [r['split'] in names for r in rows]
    val = [r for r in rows if r['split'] == 'validation']
    test = [r for r in rows if r['split'] == 'test']

    # equivalence of the vectorised and the pure feature code is by construction (same function)
    selection = {'decay': {}, 'K': {}}
    for decay in DECAYS:
        p = fit(rows, teams, split({'train'}), decay, KS[1])
        pv = predict(val, p)
        selection['decay'][str(decay)] = float(np.mean([abs(x['exp_minutes'] - r['minutes']) for x, r in zip(pv, val)]))
    decay = float(min(selection['decay'], key=selection['decay'].get))
    for K in KS:
        p = fit(rows, teams, split({'train'}), decay, K)
        pv = predict(val, p)
        selection['K'][str(K)] = float(np.mean([abs(x['expected_points'] - r['actual_total']) for x, r in zip(pv, val)]))
    K = int(min(selection['K'], key=lambda k: selection['K'][k]))
    val_params = fit(rows, teams, split({'train'}), decay, K)
    val_checks = team_checks(teams, val_params, 'validation')
    use_saves = val_checks['saves_ok']

    params = fit(rows, teams, split({'train', 'validation'}), decay, K)
    avail = fit(rows, teams, split({'train', 'validation'}), decay, K, availability=True)
    preds = predict(test, params, saves=use_saves)
    extra = {'flat_team_goals': predict(test, params, flat=True, saves=use_saves),
             'availability_variant': predict(test, avail, saves=use_saves),
             # v1.1 = availability + saves, chosen after seeing test: its test numbers are not evidence
             'v1_1': predict(test, avail, saves=True)}
    results = {'input_sha256': hashlib.sha256(raw).hexdigest(),
               'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'model_sha256': hashlib.sha256(Path(fm.__file__).read_bytes()).hexdigest(),
               'extracted_at': d['extracted_at'], 'fpl_audit': d['audit'],
               'rows': {s: sum(r['split'] == s for r in rows) for s in ('train', 'validation', 'test')},
               'selection': selection, 'chosen': {'decay': decay, 'K': K},
               'validation_team_checks': val_checks, 'saves_included': use_saves,
               'params': params, 'availability_params': {k: avail[k] for k in ('start_beta', 'sub_beta')},
               'test_team_checks': team_checks(teams, params, 'test')}
    results['test'] = evaluate(test, preds, extra, rng)
    results['test']['availability_variant_detail'] = {
        'minutes_mae': float(np.mean([abs(p['exp_minutes'] - r['minutes']) for p, r in zip(extra['availability_variant'], test)])),
        'start_calibration': calibration([p['p_start'] for p in extra['availability_variant']], [r['started'] for r in test])}
    # Post-hoc, not preregistered: what the dropped save component would have done on test
    with_saves = predict(test, params, saves=True)
    results['posthoc_with_saves'] = {
        'overall': point_metrics([p['expected_points'] for p in with_saves], [r['actual_total'] for r in test]),
        'position_v1_bias_pct': {pos: point_metrics([p['expected_points'] for p, r in zip(with_saves, test) if r['position'] == pos],
                                                     [r['actual_v1'] for r in test if r['position'] == pos])['bias_pct']
                                 for pos in fm.GOAL_POINTS}}
    finished_2026 = {r['fid'] for r in test if r['season'] == 2026}
    results['prospective_audit'] = {
        'finished_2026_fixtures': len(finished_2026), 'last_finished_kickoff': str(max(r['kickoff'] for r in test)),
        'first_prospective_match_snapshot': min(x[1] for x in d['prospective']) if d['prospective'] else None,
        'first_prospective_lineup_snapshot': min(x[2] for x in d['lineup_snapshots']) if d['lineup_snapshots'] else None,
        'finished_with_prospective_match_input': sum(r['lam_source'] == 'prospective' for r in test)}
    prosp = [i for i, r in enumerate(test) if r['lam_source'] == 'prospective']
    if prosp:
        results['prospective_subset'] = {
            'rows': len(prosp), 'fixtures': len({test[i]['fid'] for i in prosp}),
            **{k: point_metrics([v[i] for i in prosp], [test[i]['actual_total'] for i in prosp])
               for k, v in {'model': [p['expected_points'] for p in preds], 'ppg': [r['ppg'] for r in test],
                            'recent5': [r['recent5'] for r in test]}.items()}}
    results['lineup_model_2026'] = lineup_comparison(d, test, preds)
    test_outside = [o for o in outside if o[1] >= TEST]
    in_pts = sum(r['actual_total'] for r in test)
    results['coverage'] = {'outside_appearances': len(test_outside), 'outside_points': float(sum(o[2] for o in test_outside)),
                           'inside_points': float(in_pts),
                           'outside_share': float(sum(o[2] for o in test_outside) / (in_pts + sum(o[2] for o in test_outside)))}
    results['success'] = criteria(results)

    # immutable local archive of every test component, one content-hashed record per round
    meta = version_metadata('fantasy', 'fantasy-v1', configuration=json.loads(json.dumps(
        {'params': params, 'saves_included': use_saves, 'model_sha256': results['model_sha256']})),
        notes='Backtest reconstruction; team goals are match-model reconstructions before 2026/27.')
    results['model_version_id'] = meta['model_version_id']
    by_round = defaultdict(list)
    for r, p in zip(test, preds):
        by_round[(r['season'], r['round'])].append(dict(
            player_id=r['pid'], fixture_id=r['fid'], team_id=r['team'], position=r['position'],
            lambda_for=r['lam_for'], lambda_source=r['lam_source'],
            **{k: round(v, 6) for k, v in p.items()}))
    lines = [json.dumps(fm.snapshot_record(season=s, round_name=rn, version_id=meta['model_version_id'],
                                           source='reconstruction', captured_at=d['extracted_at'], rows=rr,
                                           inputs={'input_sha256': results['input_sha256']}),
                        sort_keys=True, separators=(',', ':'))
             for (s, rn), rr in sorted(by_round.items(), key=lambda kv: (kv[0][0], int(kv[0][1].rsplit('-', 1)[-1])))]
    SNAPSHOTS.write_bytes(gzip.compress(('\n'.join(lines) + '\n').encode()))
    results['snapshot_archive'] = {'path': str(SNAPSHOTS), 'records': len(lines),
                                   'sha256': hashlib.sha256(SNAPSHOTS.read_bytes()).hexdigest()}
    (ROOT / 'results.json').write_text(json.dumps(results, indent=1, default=str))
    PARAMS.write_text(json.dumps({
        'version_name': 'fantasy-v1.1', 'saves': True, 'params': avail,
        'fitted_on': [str(TRAIN), str(TEST)], 'input_sha256': results['input_sha256'],
        'notes': 'v1 + injury-list availability + goalkeeper saves, chosen after the v1 test '
                 '(experiments/fantasy_v1/REPORT.md). Only prospective snapshots can validate it.'},
        indent=1, sort_keys=True) + '\n')
    print(json.dumps({'chosen': results['chosen'], 'saves': use_saves, 'success': results['success'],
                      'overall': {k: {m: round(v[m], 4) for m in ('mae', 'rmse', 'pearson', 'spearman')}
                                  for k, v in results['test']['overall'].items()}}, indent=1))


def criteria(res):
    t = res['test']
    beats = all(t['vs'][b][m]['hi'] < 0 for b in ('ppg', 'recent5') for m in ('mae', 'mse'))
    v1 = t['v1_scope']
    pos = {p: t['segments']['position'][p]['v1_scope']['bias_pct'] for p in fm.GOAL_POINTS}
    calib = t['start_calibration']['ece'], res['test_team_checks']['team_clean_sheet']['ece']
    out = {'1_beats_ppg_and_recent_on_mae_and_rmse': beats,
            '2_bias_within_limits': abs(v1['bias_pct']) <= 5 and all(abs(b) <= 10 for b in pos.values()),
            '2_detail': {'overall_bias_pct': v1['bias_pct'], 'position_bias_pct': pos},
            '3_calibration': calib[0] <= 0.03 and calib[1] <= 0.03,
            '3_detail': {'start_ece': calib[0], 'team_cs_ece': calib[1]},
            '4_beats_flat_team_goals': t['vs']['flat_team_goals']['mae']['hi'] < 0}
    out['all_passed'] = all(v for k, v in out.items() if not k.endswith('detail'))
    return out


if __name__ == '__main__':
    main()
