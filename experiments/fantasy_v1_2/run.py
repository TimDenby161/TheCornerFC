"""Fantasy v1.2 backtest (DESIGN.md): v1's replay and splits plus bonus, cards, penalty saves,
goalkeeper minutes and team-adjusted saves. Fit on train, select M on validation, refit on
train + validation, test once against frozen v1.1. Offline: reads the frozen extract, writes
results.json and thecornerfc/fantasy_params_v1_2.json. Never touches the database."""
from bisect import bisect_left
from collections import Counter, defaultdict
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from thecornerfc import fantasy as fm

ROOT = Path(__file__).parent
INPUTS = Path('.cache/fantasy_v1_2_inputs.json.gz')
V11_PARAMS = Path('thecornerfc/fantasy_params.json')
PARAMS = Path('thecornerfc/fantasy_params_v1_2.json')
_spec = importlib.util.spec_from_file_location('v1run', ROOT.parent / 'fantasy_v1' / 'run.py')
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)

DECAY, K = 0.85, 450                  # v1.1's
SAVE_PSEUDO = (5, 10, 20)
RATE_PSEUDO_MINUTES = 900
STATS = ('tackles', 'blocks', 'interceptions', 'dribbles_won', 'passes', 'passes_accurate', 'fouls', 'pens_committed')
LINE = v1.LINE + STATS


def ts(s):
    return v1.ts(s)


# ---- Second pass over the replay: what v1.2 adds to each row ----

def augment(d, rows, teams):
    """Adds to every row his recent base BPS / cards (as fantasy.player_features computes them),
    his team's save history, and the actual bonus / cards / full target; and benchmarks on the
    full target. Uses only matches before each row's kickoff for the inputs."""
    fixtures = {r[0]: dict(zip(('fid', 'season', 'round', 'kickoff', 'status', 'home', 'away', 'hg', 'ag'), r))
                for r in d['fixtures']}
    for f in fixtures.values():
        f['kickoff'] = ts(f['kickoff'])
    lines = defaultdict(dict)
    counts = defaultdict(Counter)
    for raw in d['players']:
        l = dict(zip(LINE, raw))
        for k in v1.COUNTS + STATS:
            l[k] = l[k] or 0
        f = fixtures.get(l['fid'])
        if f is None or f['status'] not in v1.FINISHED or f['hg'] is None:
            continue
        l['conceded'] = f['ag'] if l['team'] == f['home'] else f['hg']
        lines[l['fid']][l['pid']] = l
        if l['minutes'] > 0 and l['position'] in fm.GOAL_POINTS:
            counts[(l['pid'], f['season'])][l['position']] += 1
    labels = defaultdict(dict)
    for (pid, season), c in counts.items():
        labels[pid][season] = c.most_common(1)[0][0]

    def label(pid, season):          # v1's season position
        seasons = labels.get(pid, {})
        for s in sorted(seasons, reverse=True):
            if s <= season:
                return seasons[s]
        return min(seasons.items())[1] if seasons else None

    bonus, bps_line, apps, team_saves, team_pens = {}, {}, defaultdict(list), defaultdict(int), defaultdict(int)
    for fid, ls in lines.items():
        f = fixtures[fid]
        scores = {}
        for pid, l in ls.items():
            team_saves[(fid, l['team'])] += l['saves']
            team_pens[(fid, l['team'])] += l['pens_saved']
            if l['minutes'] <= 0:
                continue
            pos = label(pid, f['season']) or 'M'      # position only sets goal / clean-sheet BPS
            b = fm.bps(pos, l['minutes'], l['goals'], l['assists'], l['conceded'], l['saves'], l['pens_saved'],
                       l['yellow'], l['red'], l['key_passes'], l['tackles'], l['blocks'], l['interceptions'],
                       l['dribbles_won'], l['passes'], l['passes_accurate'], l['shots'], l['shots_on'], l['fouls'],
                       l['pens_committed'])
            scores[pid] = b['bps']
            bps_line[(fid, pid)] = b
            apps[pid].append((f['kickoff'], l['minutes'], b['base'], l['yellow'], l['red']))
        bonus.update({(fid, p): v for p, v in fm.match_bonus(scores).items()})
    for v in apps.values():
        v.sort(key=lambda a: a[0])
    app_keys = {p: [a[0] for a in v] for p, v in apps.items()}
    prefix = {p: np.cumsum([[0, 0, 0, 0]] + [[a[1], a[2], a[3], a[4]] for a in v], axis=0) for p, v in apps.items()}

    lam_against = {(t['fid'], t['team']): t['lam_against'] for t in teams}
    team_games = defaultdict(list)
    for t in sorted(teams, key=lambda t: (t['kickoff'], t['fid'])):
        team_games[t['team']].append((t['kickoff'], t['fid']))
    team_keys = {tm: [g[0] for g in v] for tm, v in team_games.items()}

    def window(pid, k):
        keys = app_keys.get(pid, [])
        lo, hi = bisect_left(keys, k - fm.WINDOW), bisect_left(keys, k)
        s = prefix[pid][hi] - prefix[pid][lo] if pid in prefix else np.zeros(4)
        return float(s[0]), float(s[1]), float(s[2]), float(s[3])

    full, mismatched = {}, 0
    for r in rows:
        line = lines.get(r['fid'], {}).get(r['pid'])
        r['actual_bonus'] = bonus.get((r['fid'], r['pid']), 0)
        r['actual_cards'] = (fm.YELLOW_POINTS * line['yellow'] + fm.RED_POINTS * line['red']) if line and line['minutes'] > 0 else 0
        r['actual_pen_saves'] = fm.PENALTY_SAVE_POINTS * line['pens_saved'] if line and line['minutes'] > 0 else 0
        r['actual_full'] = r['actual_total'] + r['actual_bonus']
        r['actual_yellow'] = line['yellow'] if line and line['minutes'] > 0 else 0
        r['actual_red'] = line['red'] if line and line['minutes'] > 0 else 0
        r['actual_base'] = bps_line[(r['fid'], r['pid'])]['base'] if (r['fid'], r['pid']) in bps_line else 0
        mins, r['bps_base'], r['yellow'], r['red'] = window(r['pid'], r['kickoff'])
        # v1's replay also counts an appearance elsewhere at the very same kickoff (a player who has
        # just moved clubs); production and this window don't. Counted, not corrected.
        mismatched += abs(mins - r['att_min']) > 1e-6
        full[(r['fid'], r['pid'])] = r['actual_full']
        tk = team_keys[r['team']]
        lo, hi = bisect_left(tk, r['kickoff'] - fm.WINDOW), bisect_left(tk, r['kickoff'])
        r['save_history'] = [(team_saves[(fid, r['team'])], lam_against.get((fid, r['team'])))
                             for _, fid in team_games[r['team']][lo:hi]]
    # benchmarks on the full target, as v1 defines them: points per appearance this season before
    # the fixture (else last season's), and the mean over his team's last 5 league matches
    season_pts = defaultdict(lambda: [0.0, 0])
    by_fixture = defaultdict(list)
    for r in rows:
        by_fixture[r['kickoff'], r['fid']].append(r)
    for key in sorted(by_fixture):
        group = by_fixture[key]
        for r in group:
            cur, prev = season_pts[(r['pid'], r['season'])], season_pts[(r['pid'], r['season'] - 1)]
            r['ppg_full'] = cur[0] / cur[1] if cur[1] else prev[0] / prev[1] if prev[1] else 0.0
            tk = team_keys[r['team']]
            last5 = team_games[r['team']][max(0, bisect_left(tk, r['kickoff']) - 5):bisect_left(tk, r['kickoff'])]
            r['recent5_full'] = sum(full.get((fid, r['pid']), 0) for _, fid in last5) / len(last5) if last5 else 0.0
        for r in group:
            if r['minutes'] > 0:
                sp = season_pts[(r['pid'], r['season'])]
                sp[0] += r['actual_full']
                sp[1] += 1
    return {'team_pens': team_pens, 'window_mismatches': mismatched}


# ---- Fitting ----

def predict(rows, params):
    """Every v1.2 component for every row, with the production function fm.predict_team."""
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r['fid'], r['team'])].append(i)
    preds = [None] * len(rows)
    for idx in groups.values():
        r0 = rows[idx[0]]
        factor = fm.save_multiplier(r0['save_history'], params['save_intercept'], params['save_slope'],
                                    params['save_pseudo_matches'])
        for i, p in zip(idx, fm.predict_team([rows[i] for i in idx], r0['lam_for'], r0['lam_against'], params,
                                             saves=True, save_factor=factor)):
            p['save_factor'] = factor
            preds[i] = p
    return preds


def fit(rows, teams, mask, save_pseudo, extra):
    params = v1.fit(rows, teams, mask, DECAY, K, availability=True)
    fr = [r for r, m in zip(rows, mask) if m]
    gk = [r for r in fr if r['position'] == 'G']
    Xs, Xb = v1.minute_matrices(gk, DECAY, availability=True)
    ys = np.array([r['started'] for r in gk], float)
    bench = ys == 0
    yb = np.array([r['minutes'] > 0 for r in gk], float)[bench]
    splits = {r['split'] for r in fr}
    tm = [t for t in teams if t['split'] in splits]
    played = [r for r in fr if r['minutes'] > 0]
    priors = {}
    for pos in fm.GOAL_POINTS:
        pr = [r for r in played if r['position'] == pos]
        n90 = sum(r['minutes'] for r in pr) / 90
        priors[pos] = {'yellow90': sum(r['actual_yellow'] for r in pr) / n90, 'red90': sum(r['actual_red'] for r in pr) / n90,
                       'base_bps90': sum(r['actual_base'] for r in pr) / n90}
    params.update(gk_start_beta=v1.fit_logistic(Xs, ys).tolist(), gk_sub_beta=v1.fit_logistic(Xb[bench], yb).tolist(),
                  save_pseudo_matches=save_pseudo, rate_pseudo_minutes=RATE_PSEUDO_MINUTES, rate_priors=priors,
                  penalty_saves_per_team_match=sum(extra['team_pens'][(t['fid'], t['team'])] for t in tm) / len(tm),
                  bonus_beta={pos: [0.0] * 7 for pos in fm.GOAL_POINTS})
    preds = predict(fr, params)
    for pos in fm.GOAL_POINTS:
        idx = [i for i, r in enumerate(fr) if r['position'] == pos]
        X = np.array([fm.bonus_features(pos, preds[i]) for i in idx])
        y = np.array([fr[i]['actual_bonus'] for i in idx], float)
        keep = X.any(axis=0)            # e.g. saves for outfielders: an all-zero column stays 0
        beta = np.zeros(X.shape[1])
        beta[keep] = np.linalg.lstsq(X[:, keep], y, rcond=None)[0]
        params['bonus_beta'][pos] = beta.tolist()
    return params


# ---- Evaluation ----

def evaluate(rows, v12, v11, rng):
    actual = np.array([r['actual_full'] for r in rows], float)
    cands = {'v1_2': [p['expected_points'] for p in v12], 'v1_1': [p['expected_points'] for p in v11],
             'recent5': [r['recent5_full'] for r in rows], 'ppg': [r['ppg_full'] for r in rows]}
    clusters = np.array([f"{r['season']}|{r['round']}" for r in rows])
    abs_err = {k: np.abs(np.asarray(v) - actual) for k, v in cands.items()}
    sq_err = {k: (np.asarray(v) - actual) ** 2 for k, v in cands.items()}
    res = {'overall': {k: v1.point_metrics(v, actual) for k, v in cands.items()},
           'vs': {k: {'mae': v1.paired_bootstrap(abs_err['v1_2'], abs_err[k], clusters, rng),
                      'mse': v1.paired_bootstrap(sq_err['v1_2'], sq_err[k], clusters, rng)} for k in cands if k != 'v1_2'},
           'total_target': {k: v1.point_metrics(cands[k], [r['actual_total'] for r in rows]) for k in ('v1_2', 'v1_1')}}
    res['position'] = {}
    for pos in fm.GOAL_POINTS:
        idx = [i for i, r in enumerate(rows) if r['position'] == pos]
        res['position'][pos] = {k: v1.point_metrics([v[i] for i in idx], actual[idx]) for k, v in cands.items()}
        res['position'][pos]['vs_v1_1_mae'] = v1.paired_bootstrap(abs_err['v1_2'][idx], abs_err['v1_1'][idx], clusters[idx], rng)
        res['position'][pos]['components'] = {
            c: {'pred': float(np.mean([v12[i][c] for i in idx])), 'actual': float(np.mean([rows[i][a] for i in idx]))}
            for c, a in (('bonus_points', 'actual_bonus'), ('card_points', 'actual_cards'),
                         ('penalty_save_points', 'actual_pen_saves'), ('save_points', 'actual_save_points'),
                         ('appearance_points', 'actual_appearance_points'))}
    # regular starting keepers (3+ starts in the last 5), the Pickford question
    reg = [i for i, r in enumerate(rows) if r['position'] == 'G' and sum(h[0] for h in r['history'][:5]) >= 3]
    res['regular_gk'] = {k: v1.point_metrics([v[i] for i in reg], actual[reg]) for k, v in cands.items()}
    res['regular_gk']['p_start'] = {'v1_2': float(np.mean([v12[i]['p_start'] for i in reg])),
                                    'v1_1': float(np.mean([v11[i]['p_start'] for i in reg])),
                                    'actual': float(np.mean([rows[i]['started'] for i in reg]))}
    res['start_calibration'] = v1.calibration([p['p_start'] for p in v12], [r['started'] for r in rows])
    gk = [i for i, r in enumerate(rows) if r['position'] == 'G']
    res['gk_start_calibration'] = {k: v1.calibration([v[i]['p_start'] for i in gk], [rows[i]['started'] for i in gk])
                                   for k, v in (('v1_2', v12), ('v1_1', v11))}
    res['bonus'] = {'mean_pred': float(np.mean([p['bonus_points'] for p in v12])),
                    'mean_actual': float(np.mean([r['actual_bonus'] for r in rows])),
                    'pearson': float(np.corrcoef([p['bonus_points'] for p in v12], [r['actual_bonus'] for r in rows])[0, 1])}
    # saves by team-multiplier tercile (starting keepers who played 60+)
    played = [i for i in gk if rows[i]['minutes'] >= 60]
    fac = np.array([v12[i]['save_factor'] for i in played])
    cuts = np.quantile(fac, [1 / 3, 2 / 3])
    res['saves_by_factor'] = []
    for lo, hi in zip([-np.inf, *cuts], [*cuts, np.inf]):
        sel = [i for i, f in zip(played, fac) if lo < f <= hi]
        res['saves_by_factor'].append({'n': len(sel), 'mean_factor': float(np.mean([v12[i]['save_factor'] for i in sel])),
                                       'v1_2': float(np.mean([v12[i]['save_points'] for i in sel])),
                                       'v1_1': float(np.mean([v11[i]['save_points'] for i in sel])),
                                       'actual': float(np.mean([rows[i]['actual_save_points'] for i in sel]))})
    return res


def criteria(res):
    vs = res['vs']['v1_1']
    bias = {p: res['position'][p]['v1_2']['bias_pct'] for p in fm.GOAL_POINTS}
    out = {'1_beats_v1_1_mae_and_rmse': vs['mae']['hi'] < 0 and vs['mse']['hi'] < 0,
           '2_bias_within_limits': abs(res['overall']['v1_2']['bias_pct']) <= 5 and all(abs(b) <= 10 for b in bias.values()),
           '2_detail': {'overall_bias_pct': res['overall']['v1_2']['bias_pct'], 'position_bias_pct': bias},
           '3_gk_mae_below_v1_1': res['position']['G']['v1_2']['mae'] < res['position']['G']['v1_1']['mae'],
           '4_start_calibration': res['start_calibration']['ece'] <= 0.03 and res['gk_start_calibration']['v1_2']['ece'] <= 0.03,
           '4_detail': {'start_ece': res['start_calibration']['ece'], 'gk_start_ece': res['gk_start_calibration']['v1_2']['ece']}}
    out['all_passed'] = all(v for k, v in out.items() if not k.endswith('detail'))
    return out


def main():
    raw = gzip.decompress(INPUTS.read_bytes())
    d = json.loads(raw)
    rows, teams, _ = v1.replay(d)
    for x in (*rows, *teams):
        x['split'] = v1.split_of(x['kickoff'])
    rows = [r for r in rows if r['split'] and r['lam_for'] is not None]
    extra = augment(d, rows, teams)
    rng = np.random.default_rng(v1.SEED)
    split = lambda names: [r['split'] in names for r in rows]
    val = [r for r in rows if r['split'] == 'validation']
    test = [r for r in rows if r['split'] == 'test']
    val_gk = [i for i, r in enumerate(val) if r['position'] == 'G']

    selection = {}
    for m in SAVE_PSEUDO:
        pv = predict(val, fit(rows, teams, split({'train'}), m, extra))
        selection[str(m)] = float(np.mean([abs(pv[i]['expected_points'] - val[i]['actual_full']) for i in val_gk]))
    m = int(min(selection, key=selection.get))

    params = fit(rows, teams, split({'train', 'validation'}), m, extra)
    v11_doc = json.loads(V11_PARAMS.read_text())
    v12 = predict(test, params)
    v11 = v1.predict(test, v11_doc['params'], saves=True)
    results = {'input_sha256': hashlib.sha256(raw).hexdigest(),
               'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'model_sha256': hashlib.sha256(Path(fm.__file__).read_bytes()).hexdigest(),
               'extracted_at': d['extracted_at'],
               'rows': {s: sum(r['split'] == s for r in rows) for s in ('train', 'validation', 'test')},
               'window_mismatches': extra['window_mismatches'],
               'selection': {'save_pseudo_matches': selection}, 'chosen': {'save_pseudo_matches': m},
               'params': params,
               'reconstructed_bonus': {s: float(np.mean([r['actual_bonus'] for r in rows if r['split'] == s]))
                                       for s in ('train', 'validation', 'test')}}
    results['test'] = evaluate(test, v12, v11, rng)
    results['success'] = criteria(results['test'])
    (ROOT / 'results.json').write_text(json.dumps(results, indent=1, default=str))
    PARAMS.write_text(json.dumps({
        'version_name': 'fantasy-v1.2', 'saves': True, 'params': params,
        'fitted_on': [str(v1.TRAIN), str(v1.TEST)], 'input_sha256': results['input_sha256'],
        'backtest_passed': results['success']['all_passed'],
        'notes': 'v1.1 + reconstructed bonus, cards, penalty saves, goalkeeper minutes and team-adjusted saves '
                 '(experiments/fantasy_v1_2/DESIGN.md). Designed after seeing v1.1 live, so only prospective '
                 'snapshots (P9) can validate it.'}, indent=1, sort_keys=True) + '\n')
    t = results['test']
    print(json.dumps({'chosen': m, 'selection': selection, 'success': results['success'],
                      'overall': {k: {x: round(v[x], 4) for x in ('mae', 'rmse', 'mean_pred', 'mean_actual', 'bias_pct')}
                                  for k, v in t['overall'].items()},
                      'regular_gk': {k: (round(v['mean_pred'], 3), round(v['mean_actual'], 3), round(v['mae'], 4))
                                     if 'mae' in v else v for k, v in t['regular_gk'].items()},
                      'bonus': t['bonus']}, indent=1))


if __name__ == '__main__':
    main()
