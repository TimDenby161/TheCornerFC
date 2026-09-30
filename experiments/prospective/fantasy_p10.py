"""Prospective evaluation of fantasy v1.4 against v1.3 (PROTOCOLS.md, P10).

Read-only and blinded as fantasy_p9.py, whose extraction, target and pairing it reuses (target:
the reconstructed total plus FPL's own bonus and defensive-contribution points). Primary: the
Brier score of P(DC) (a version's DC points / 2) against FPL's own DC points, for FPL defenders and
midfielders; then points MAE and MSE.
"""
import argparse
import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).parent
_spec = importlib.util.spec_from_file_location('fantasy_p9', ROOT / 'fantasy_p9.py')
p9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p9)

# Registered in PROTOCOLS.md (P10); change only by a dated amendment there.
TARGET_ROUNDS, TARGET_ROWS = 10, 3000
OLD, NEW = 'fantasy-v1.3', 'fantasy-v1.4'
SEED = 20260930
MAE_MARGIN = 0.02
DC_POINTS = 2
RECORD_BINS = ((0, 1), (1, 270), (270, 540), (540, 10 ** 6))   # his FPL minutes behind the record


def build(data, view='kickoff'):
    return p9.build(*data, view=view, old_version=OLD, new_version=NEW)


def brier(rows, key):
    return sum((r[key] / DC_POINTS - (r['dc'] > 0)) ** 2 for r in rows) / len(rows)


def analyse(rows):
    rng = random.Random(SEED)
    dm = [r for r in rows if r['fpl_position'] in ('D', 'M')]
    hit = lambda r: float(r['dc'] > 0)
    brier_diff = lambda r: (r['new_dc'] / DC_POINTS - hit(r)) ** 2 - (r['old_dc'] / DC_POINTS - hit(r)) ** 2
    mae = lambda r: abs(r['new'] - r['actual']) - abs(r['old'] - r['actual'])
    mse = lambda r: (r['new'] - r['actual']) ** 2 - (r['old'] - r['actual']) ** 2
    res = {'dc_brier': p9.p11.paired(dm, brier_diff, rng) if dm else None,
           'dc_brier_by_position': {p: {'n': len(rs), 'v1_4': brier(rs, 'new_dc'), 'v1_3': brier(rs, 'old_dc')}
                                    for p in 'DM' if (rs := [r for r in dm if r['fpl_position'] == p])},
           'mae': p9.p11.paired(rows, mae, rng), 'mse': p9.p11.paired(rows, mse, rng),
           'dc_by_record': [{'minutes': f'{lo}-{hi}', 'n': len(rs), 'v1_4_mean_p': sum(r['new_dc'] for r in rs) / DC_POINTS / len(rs),
                             'fpl_rate': sum(hit(r) for r in rs) / len(rs)}
                            for lo, hi in RECORD_BINS if (rs := [r for r in dm if lo <= (r['fpl_dc_minutes'] or 0) < hi])]}
    res['p9_secondary'] = {k: v for k, v in p9.analyse(rows).items() if k in ('bias_pct', 'bonus_dc_by_position', 'gk_start_ece')}
    res['criteria'] = {'dc_brier_better': bool(res['dc_brier'] and res['dc_brier']['hi'] < 0),
                       'points_mae_not_worse': res['mae']['hi'] <= MAE_MARGIN}
    res['criteria']['supported'] = all(res['criteria'].values())
    return res


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--unblind', action='store_true', help='Outcome metrics, once the target is reached')
    parser.add_argument('--interim', action='store_true', help='Allow --unblind early; labelled a protocol deviation')
    args = parser.parse_args()
    data = p9.extract((OLD, NEW))
    if data is None:
        print(json.dumps({'P10': 'fantasy_fixture_snapshots does not exist yet'}))
        return
    rows = build(data)
    status = {'rounds': len({r['round'] for r in rows}), 'player_rows': len(rows),
              'target_rounds': TARGET_ROUNDS, 'target_rows': TARGET_ROWS}
    status['target_reached'] = status['rounds'] >= TARGET_ROUNDS and status['player_rows'] >= TARGET_ROWS
    print(json.dumps(status, indent=1))
    (ROOT / 'status_P10.json').write_text(json.dumps(status, indent=2) + '\n')
    if not args.unblind:
        return
    if not status['target_reached'] and not args.interim:
        sys.exit('P10 target not reached; refusing to unblind (use --interim for a labelled protocol deviation)')
    out = {'status': status, 'deviation': None if status['target_reached'] else 'interim look before target',
           'kickoff_view': analyse(rows)}
    deadline = build(data, view='deadline')
    if deadline:
        out['deadline_view'] = analyse(deadline)
    name = 'results_P10.json' if status['target_reached'] else 'interim_P10.json'
    (ROOT / name).write_text(json.dumps(out, indent=2, default=str) + '\n')
    print(json.dumps(out['kickoff_view']['criteria'], indent=1))


if __name__ == '__main__':
    main()
