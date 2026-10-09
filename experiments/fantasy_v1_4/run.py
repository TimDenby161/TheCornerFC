"""Fantasy v1.4 (DESIGN.md): v1.3's defensive-contribution rate updated by each player's own FPL
record. Fit on GW1-3 (m and r on GW2-3), test on GW4-5. Offline: reads the frozen extracts of
experiments/fantasy_dc, writes results.json and thecornerfc/fantasy_games/fantasy_params_v1_4.json."""
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from scipy.optimize import minimize
from thecornerfc.fantasy_games import fantasy as fm

ROOT = Path(__file__).parent
V13_PARAMS = Path('thecornerfc/fantasy_games/fantasy_params_v1_3.json')
V14_PARAMS = Path('thecornerfc/fantasy_games/fantasy_params_v1_4.json')
_spec = importlib.util.spec_from_file_location('dcrun', ROOT.parent / 'fantasy_dc' / 'run.py')
dcrun = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dcrun)
v12 = dcrun.v12

FIT, M_FIT, TEST = (1, 2, 3), (2, 3), (4, 5)
THRESHOLDS = {'D': 10, 'M': 12, 'F': 12}


def load():
    """Player-matches with minutes (single-fixture gameweeks, matched to one API line), each with
    his pre-match API rate inputs and his FPL record from earlier gameweeks."""
    raw = gzip.decompress(dcrun.DC_INPUTS.read_bytes())
    dc = json.loads(raw)
    d = json.loads(gzip.decompress(v12.INPUTS.read_bytes()))
    fx = {f[0]: dict(kickoff=datetime.fromisoformat(f[3]), season=f[1]) for f in d['fixtures']}
    L = {k: i for i, k in enumerate(v12.LINE)}
    hist, lines = defaultdict(list), defaultdict(list)
    for line in d['players']:
        f = fx.get(line[0])
        if f is None or line[L['minutes']] <= 0:
            continue
        cbit = sum(line[L[k]] or 0 for k in ('tackles', 'blocks', 'interceptions'))
        hist[line[L['pid']]].append((f['kickoff'], line[L['minutes']], cbit))
        if f['season'] == 2026:
            lines[line[L['pid']]].append((f['kickoff'], line[0], line[L['minutes']], cbit))
    for v in hist.values():
        v.sort()
    keys = {p: [a[0] for a in v] for p, v in hist.items()}

    def window(pid, k):
        lo, hi = bisect_left(keys.get(pid, []), k - fm.WINDOW), bisect_left(keys.get(pid, []), k)
        apps = hist.get(pid, [])[lo:hi]
        return sum(a[1] for a in apps), sum(a[2] for a in apps)

    deadlines = dict((e, datetime.fromisoformat(t)) for s, e, t in dc['gameweeks'] if s == 2026)
    api = {fpl: a for s, fpl, a in dc['map'] if s == 2026}
    pos = {p: dcrun.FPL_POS.get(x) for p, x in dc['positions']}
    record = defaultdict(dict)          # fpl id -> event -> (minutes, count), doubles included
    for season, event, fpl_id, minutes, stats, explain in dc['results']:
        if minutes:
            record[fpl_id][event] = (minutes, stats.get('defensive_contribution', 0))
    data = []
    for season, event, fpl_id, minutes, stats, explain in dc['results']:
        a, p = api.get(fpl_id), pos.get(fpl_id)
        if not minutes or len(explain) != 1 or a is None or p not in THRESHOLDS:
            continue
        start, end = deadlines[event], deadlines.get(event + 1)
        match = [l for l in lines.get(a, []) if l[0] >= start and (end is None or l[0] < end)]
        if len(match) != 1:
            continue
        mins, cb = window(a, match[0][0])
        earlier = [v for e, v in record[fpl_id].items() if e < event]
        data.append(dict(event=event, fpl_id=fpl_id, position=p, minutes=minutes,
                         count=stats.get('defensive_contribution', 0),
                         hit=sum(s['points'] for s in explain[0]['stats'] if s['identifier'] == 'defensive_contribution') > 0,
                         hist_minutes=mins, hist_cbit=cb, own_minutes=sum(m for m, _ in earlier),
                         own_count=sum(c for _, c in earlier)))
    return raw, data


def rates(data, fit_events, pseudo):
    """API rate shrunk toward the position's, the prior computed on fit_events (as fantasy_dc)."""
    prior = {}
    for p in THRESHOLDS:
        h = [x for x in data if x['position'] == p and x['event'] in fit_events]
        prior[p] = sum(x['hist_cbit'] for x in h) / (sum(x['hist_minutes'] for x in h) / 90)
    for x in data:
        x['cbit90'] = (x['hist_cbit'] + prior[x['position']] * pseudo) / (x['hist_minutes'] / 90 + pseudo)
    return prior


def per90(x, q, m=None):
    base = q['c'] + q['k'] * x['cbit90']
    return base if m is None else (x['own_count'] + base * m) / (x['own_minutes'] / 90 + m)


def fit_own(rows, ck):
    """m (shared) and each position's r, maximising the NegBin likelihood given actual minutes."""
    by = {p: [x for x in rows if x['position'] == p] for p in THRESHOLDS}

    def nll(t):
        m, rs = np.exp(t[0]), dict(zip(THRESHOLDS, np.exp(t[1:])))
        total = 0.0
        for p, xs in by.items():
            if xs:
                mean = np.array([max(x['minutes'] / 90 * per90(x, ck[p], m), 1e-6) for x in xs])
                total -= dcrun.nb_logpmf(np.array([x['count'] for x in xs], float), mean, rs[p]).sum()
        return total
    t = minimize(nll, np.log([5.0, 8.0, 13.0, 13.0]), method='Nelder-Mead',
                 options={'maxiter': 8000, 'xatol': 1e-6, 'fatol': 1e-8}).x
    return float(np.exp(t[0])), {p: float(r) for p, r in zip(THRESHOLDS, np.exp(t[1:]))}


def p_reach(x, q, r, m=None):
    mean = x['minutes'] / 90 * per90(x, q, m)
    return fm.nb_tail(THRESHOLDS[x['position']], mean, r)


def main():
    raw, data = load()
    v13 = json.loads(V13_PARAMS.read_text())
    params = v13['params']
    pseudo = params['rate_pseudo_minutes'] / 90

    # fit / test: v1.3's c, k, r on GW1-3; v1.4's m and r on GW2-3
    rates(data, FIT, pseudo)
    fit = [x for x in data if x['event'] in FIT]
    base = {p: dcrun.fit_counts([x for x in fit if x['position'] == p]) for p in THRESHOLDS}
    m, r = fit_own([x for x in data if x['event'] in M_FIT], base)
    test = {}
    for p in THRESHOLDS:
        t = [x for x in data if x['event'] in TEST and x['position'] == p]
        y = np.array([x['hit'] for x in t], float)
        old = np.array([p_reach(x, base[p], base[p]['r']) for x in t])
        new = np.array([p_reach(x, base[p], r[p], m) for x in t])
        test[p] = {'n': len(t), 'actual_rate': float(y.mean()), 'v1_3_mean_p': float(old.mean()), 'v1_4_mean_p': float(new.mean()),
                   'brier_v1_3': float(((old - y) ** 2).mean()), 'brier_v1_4': float(((new - y) ** 2).mean()),
                   'mean_within_15pct': bool(abs(new.mean() - y.mean()) <= 0.15 * y.mean()) if y.mean() else None,
                   'brier_better': bool(((new - y) ** 2).mean() < ((old - y) ** 2).mean())}
    checks = {p: test[p]['brier_better'] and test[p]['mean_within_15pct'] for p in 'DM'}

    # frozen v1.4: v1.3's final c and k, m and r refitted on GW2-5
    final = params['dc']
    rates(data, (1, 2, 3, 4, 5), pseudo)
    m_final, r_final = fit_own([x for x in data if x['event'] >= 2], final)
    dc = dict(final, own_pseudo_90s=m_final, **{p: dict(final[p], r=r_final[p]) for p in THRESHOLDS})
    results = {'input_sha256': hashlib.sha256(raw).hexdigest(), 'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'rows': len(data), 'fit': {'m': m, 'r': r, 'v1_3': base}, 'test': test, 'checks_pass': checks,
               'final': {'m': m_final, 'r': r_final}}
    V14_PARAMS.write_text(json.dumps({
        'version_name': 'fantasy-v1.4', 'saves': True, 'params': dict(params, dc=dc),
        'fitted_on': v13['fitted_on'], 'input_sha256': v13['input_sha256'], 'dc_input_sha256': results['input_sha256'],
        'notes': "v1.3 + each player's own FPL defensive-contribution record (experiments/fantasy_v1_4/). "
                 'Only prospective snapshots can validate it.'}, indent=1, sort_keys=True) + '\n')
    (ROOT / 'results.json').write_text(json.dumps(results, indent=1))
    print(json.dumps({k: results[k] for k in ('rows', 'fit', 'test', 'checks_pass', 'final')}, indent=1))


if __name__ == '__main__':
    main()
