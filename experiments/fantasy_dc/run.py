"""Defensive contributions and bonus from FPL's own GW results (DESIGN.md): fit on GW1-3, test
on GW4-5. Offline: reads the two frozen extracts, writes results.json and, from v1.2's frozen
parameters, thecornerfc/fantasy_games/fantasy_params_v1_3.json. Never touches the database."""
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from thecornerfc.fantasy_games import fantasy as fm

ROOT = Path(__file__).parent
DC_INPUTS = Path('.cache/fantasy_dc_inputs.json.gz')
V12_PARAMS = Path('thecornerfc/fantasy_games/fantasy_params_v1_2.json')
V13_PARAMS = Path('thecornerfc/fantasy_games/fantasy_params_v1_3.json')
_spec = importlib.util.spec_from_file_location('v12run', ROOT.parent / 'fantasy_v1_2' / 'run.py')
v12 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v12)

FIT, TEST = (1, 2, 3), (4, 5)
FPL_POS = {'GKP': 'G', 'DEF': 'D', 'MID': 'M', 'FWD': 'F'}


def nb_logpmf(x, mean, r):
    return (gammaln(x + r) - gammaln(r) - gammaln(x + 1) + r * np.log(r / (r + mean)) + x * np.log(mean / (r + mean)))


def fit_counts(rows):
    """c, k, r maximising the NegBin likelihood of FPL's count given minutes and API rate."""
    x = np.array([r['count'] for r in rows], float)
    m90 = np.array([r['minutes'] / 90 for r in rows])
    rate = np.array([r['cbit90'] for r in rows])

    def nll(t):
        c, k, r = np.exp(t)
        return -nb_logpmf(x, np.maximum(m90 * (c + k * rate), 1e-6), r).sum()
    t = minimize(nll, np.log([2.0, 1.0, 5.0]), method='Nelder-Mead', options={'maxiter': 4000, 'xatol': 1e-6, 'fatol': 1e-8}).x
    c, k, r = np.exp(t)
    return {'c': float(c), 'k': float(k), 'r': float(r)}


def main():
    raw = gzip.decompress(DC_INPUTS.read_bytes())
    dc = json.loads(raw)
    d = json.loads(gzip.decompress(v12.INPUTS.read_bytes()))
    v12doc = json.loads(V12_PARAMS.read_text())
    params = v12doc['params']

    # v1.2's replay, for every universe row's pre-match minutes model and API history
    rows, teams, _ = v12.v1.replay(d)
    for x in (*rows, *teams):
        x['split'] = v12.v1.split_of(x['kickoff'])
    rows = [r for r in rows if r['split'] == 'test' and r['season'] == 2026 and r['lam_for'] is not None]
    v12.augment(d, rows, teams)
    preds = v12.predict(rows, params)
    by_key = {(r['pid'], r['fid']): (r, p) for r, p in zip(rows, preds)}

    # API-Football lines for 2026 PL matches and every player's (tackles + blocks + interceptions) history
    fx = {f[0]: dict(kickoff=datetime.fromisoformat(f[3]), season=f[1]) for f in d['fixtures']}
    L = dict((k, i) for i, k in enumerate(v12.LINE))
    hist = defaultdict(list)
    lines = defaultdict(list)
    for raw_line in d['players']:
        f = fx.get(raw_line[0])
        if f is None or raw_line[L['minutes']] <= 0:
            continue
        cbit = sum(raw_line[L[k]] or 0 for k in ('tackles', 'blocks', 'interceptions'))
        hist[raw_line[L['pid']]].append((f['kickoff'], raw_line[L['minutes']], cbit))
        if f['season'] == 2026:
            lines[raw_line[L['pid']]].append((f['kickoff'], raw_line[0], raw_line[L['minutes']], cbit))
    for v in hist.values():
        v.sort()
    keys = {p: [a[0] for a in v] for p, v in hist.items()}

    def window(pid, k):
        lo, hi = bisect_left(keys.get(pid, []), k - fm.WINDOW), bisect_left(keys.get(pid, []), k)
        apps = hist.get(pid, [])[lo:hi]
        return sum(a[1] for a in apps), sum(a[2] for a in apps)

    deadlines = sorted((e, datetime.fromisoformat(t)) for s, e, t in dc['gameweeks'] if s == 2026)
    api = {fpl: a for s, fpl, a in dc['map'] if s == 2026}
    pos = {p: FPL_POS.get(x) for p, x in dc['positions']}
    data, skipped = [], defaultdict(int)
    for season, event, fpl_id, minutes, stats, explain in dc['results']:
        if not minutes:
            continue
        if len(explain) != 1:
            skipped['double_or_blank'] += 1
            continue
        a = api.get(fpl_id)
        start = dict(deadlines)[event]
        end = dict(deadlines).get(event + 1)
        match = [l for l in lines.get(a, []) if l[0] >= start and (end is None or l[0] < end)]
        if a is None or len(match) != 1:
            skipped['unmatched'] += 1
            continue
        kickoff, fid, api_min, api_cbit = match[0]
        mins, cb = window(a, kickoff)
        dc_pts = sum(s['points'] for s in explain[0]['stats'] if s['identifier'] == 'defensive_contribution')
        data.append(dict(event=event, fpl_id=fpl_id, pid=a, fid=fid, position=pos.get(fpl_id), minutes=minutes,
                         api_minutes=api_min, api_cbit=api_cbit, count=stats.get('defensive_contribution', 0),
                         dc_points=dc_pts, bonus=stats.get('bonus', 0), bps=stats.get('bps', 0),
                         hist_minutes=mins, hist_cbit=cb, row=by_key.get((a, fid))))
    fit = [x for x in data if x['event'] in FIT]
    test = [x for x in data if x['event'] in TEST]

    # API rate, shrunk toward the position's (fit split, pre-match histories)
    pseudo = params['rate_pseudo_minutes'] / 90
    prior = {}
    for p in 'DMF':
        h = [x for x in fit if x['position'] == p]
        prior[p] = sum(x['hist_cbit'] for x in h) / (sum(x['hist_minutes'] for x in h) / 90)
    for x in data:
        if x['position'] in prior:
            x['cbit90'] = (x['hist_cbit'] + prior[x['position']] * pseudo) / (x['hist_minutes'] / 90 + pseudo)

    thresholds = {'D': 10, 'M': 12, 'F': 12}
    dcp = {'thresholds': thresholds, 'cbit_priors': prior, 'points': 2}
    for p in 'DMF':
        dcp[p] = fit_counts([x for x in fit if x['position'] == p])
    results = {'input_sha256': hashlib.sha256(raw).hexdigest(), 'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'matched': {'fit': len(fit), 'test': len(test)}, 'skipped': dict(skipped), 'dc_params': dcp}

    # sanity: how FPL's count relates to API's tackles + blocks + interceptions in the same match
    results['count_vs_api'] = {p: {'fpl_mean': float(np.mean([x['count'] for x in fit if x['position'] == p])),
                                   'api_mean': float(np.mean([x['api_cbit'] for x in fit if x['position'] == p])),
                                   'corr': float(np.corrcoef([x['count'] for x in fit if x['position'] == p],
                                                             [x['api_cbit'] for x in fit if x['position'] == p])[0, 1])}
                               for p in 'DMF'}

    # test: calibration given actual minutes (the count model alone) and pre-match (with v1.2's minutes)
    def p_reach(p, minutes, rate):
        q = dcp[p]
        mean = max(minutes / 90 * (q['c'] + q['k'] * rate), 1e-6)
        return 1 - float(np.exp(nb_logpmf(np.arange(thresholds[p]), mean, q['r'])).sum())
    # pre-match, over everyone v1.2 predicted for a GW4-5 fixture (0 points for those who didn't play)
    fpl_of = {a: f for f, a in api.items()}
    actual = {(x[1], x[2]): x for x in dc['results']}
    event_of = lambda k: max((e for e, t in deadlines if t <= k), default=None)
    pre = defaultdict(lambda: ([], []))
    for r, pr in zip(rows, preds):
        e, f = event_of(r['kickoff']), fpl_of.get(r['pid'])
        p = pos.get(f)
        if e not in TEST or p not in thresholds:
            continue
        res = actual.get((e, f))
        if res and len(res[5]) > 1:
            continue                                  # a double gameweek's points aren't per fixture
        mins, cb = window(r['pid'], r['kickoff'])
        rate = (cb + prior[p] * pseudo) / (mins / 90 + pseudo)
        got = sum(s['points'] for s in res[5][0]['stats'] if s['identifier'] == 'defensive_contribution') if res and res[5] else 0
        pre[p][0].append(2 * fm.dc_probability(p, dict(pr, cbit90=rate), dcp))
        pre[p][1].append(got)
    prematch = {p: {'prematch_n': len(v[0]), 'prematch_mean_points': float(np.mean(v[0])),
                    'prematch_actual_points': float(np.mean(v[1]))} for p, v in pre.items()}
    results['test'] = {}
    for p in 'DMF':
        t = [x for x in test if x['position'] == p]
        f = [x for x in fit if x['position'] == p]
        y = np.array([x['dc_points'] > 0 for x in t], float)
        given = np.array([p_reach(p, x['minutes'], x['cbit90']) for x in t])
        base_rate = np.mean([x['dc_points'] > 0 for x in f if x['minutes'] >= 60])
        base = np.array([base_rate if x['minutes'] >= 60 else 0.0 for x in t])
        cuts = np.linspace(0, 1, 6)
        idx = np.minimum((given * 5).astype(int), 4)
        results['test'][p] = {
            'n': len(t), 'actual_rate': float(y.mean()), 'given_minutes_mean_p': float(given.mean()),
            'brier_model': float(((given - y) ** 2).mean()), 'brier_baseline': float(((base - y) ** 2).mean()),
            'calibration': [{'bin': f'{cuts[b]:.1f}-{cuts[b + 1]:.1f}', 'n': int((idx == b).sum()),
                             'mean_p': float(given[idx == b].mean()) if (idx == b).any() else None,
                             'rate': float(y[idx == b].mean()) if (idx == b).any() else None} for b in range(5)],
            **prematch.get(p, {})}

    # bonus: FPL's real bonus against the reconstructed one and v1.2's prediction, same player-matches
    bonus = {}
    for split, sel in (('fit', fit), ('test', test)):
        bonus[split] = {}
        for p in 'GDMF':
            s = [x for x in sel if x['position'] == p and x['row']]
            bonus[split][p] = {'n': len(s), 'fpl': float(np.mean([x['bonus'] for x in s])) if s else None,
                               'reconstructed': float(np.mean([x['row'][0]['actual_bonus'] for x in s])) if s else None,
                               'v1_2_pred': float(np.mean([x['row'][1]['bonus_points'] for x in s])) if s else None,
                               'corr_recon_fpl': float(np.corrcoef([x['bonus'] for x in s], [x['row'][0]['actual_bonus'] for x in s])[0, 1]) if len(s) > 2 else None}
    results['bonus'] = bonus
    # frozen v1.3: v1.2 plus DC refitted on GW1-5 (the checks above are on the GW1-3 fit); bonus
    # stays v1.2's, since rescaling it on GW1-3 made GW4-5 worse for three positions of four
    final = {'thresholds': thresholds, 'cbit_priors': prior, 'points': 2,
             **{p: fit_counts([x for x in data if x['position'] == p]) for p in 'DMF'}}
    results['final_dc_params'] = final
    V13_PARAMS.write_text(json.dumps({
        'version_name': 'fantasy-v1.3', 'saves': True, 'params': dict(params, dc=final),
        'fitted_on': v12doc['fitted_on'], 'input_sha256': v12doc['input_sha256'], 'dc_input_sha256': results['input_sha256'],
        'notes': 'v1.2 + defensive contributions fitted on FPL 2026/27 GW1-5 results (experiments/fantasy_dc/). '
                 'Only prospective snapshots can validate it.'}, indent=1, sort_keys=True) + '\n')
    (ROOT / 'results.json').write_text(json.dumps(results, indent=1, default=str))
    print(json.dumps({k: results[k] for k in ('matched', 'skipped', 'count_vs_api', 'dc_params', 'test', 'bonus')}, indent=1, default=str))


if __name__ == '__main__':
    main()
