"""Prospective evaluation of fantasy v1.6 (FPL's injury status) against v1.5 (PROTOCOLS.md, P12).

Read-only: one READ ONLY / REPEATABLE READ transaction, no API calls, nothing written to the
database or read by production. Blinded by default: without --unblind the output is accrual only.
--unblind refuses until the registered target; --interim overrides that and labels the output a
protocol deviation that cannot support a decision.

Target: whether each snapshot player played (minutes > 0) and started, from fixture_players; a
player with no match line didn't play. At target it also fits each FPL bucket's availability
factor (observed play rate / v1.5's mean P(play), capped at 1; buckets under MIN_BUCKET keep v1.6's).
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import json
import math
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from thecornerfc.fantasy_games import fantasy as fm

ROOT = Path(__file__).parent
# Registered in PROTOCOLS.md (P12); change only by a dated amendment there.
TARGET_ROUNDS, TARGET_FLAGGED = 6, 300
OLD, NEW = 'fantasy-v1.5', 'fantasy-v1.6'
DEADLINE_BEFORE = timedelta(minutes=90)
SEED, DRAWS = 20260930, 2000
ALL_MARGIN = 0.001          # all players: v1.6 may be at most this much worse (upper end of the interval)
MIN_BUCKET = 30
EPS = 1e-6


def dt(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))


def extract():
    from dotenv import dotenv_values
    import psycopg
    with psycopg.connect(dotenv_values('.env')['DATABASE_URL'].strip(), connect_timeout=15,
                         options='-c default_transaction_read_only=on') as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        if c.execute("select to_regclass('public.fantasy_fixture_snapshots')").fetchone()[0] is None:
            return None
        snaps = c.execute('''select s.fixture_id, s.team_id, s.captured_at, s.created_at, s.effective_at, s.predictions,
                                    s.inputs, mv.version_name, f.season, f.round
                             from fantasy_fixture_snapshots s join fixtures f using (fixture_id)
                             join model_versions mv using (model_version_id)
                             where mv.version_name = any(%s)
                               and s.source = 'prospective' and s.captured_at < s.effective_at
                               and s.created_at < s.effective_at and f.status_short = 'FT' ''', [[OLD, NEW]]).fetchall()
        fids = sorted({s[0] for s in snaps})
        lines = c.execute('select fixture_id, team_id, player_id, minutes, started from fixture_players where fixture_id = any(%s)',
                          [fids]).fetchall()
        rounds = c.execute('''select season, round, min(kickoff) from fixtures where league_id = 39
                              and (season, round) in (select season, round from fixtures where fixture_id = any(%s))
                              group by 1, 2''', [fids]).fetchall()
    return snaps, lines, rounds


def bucket(fpl, api, kickoff):
    """The P12 calibration bucket of one player-fixture. fpl: v1.6's stored FPL entry or None;
    api: the API-Football list type stored with the snapshot, or None."""
    if fpl and api:
        return 'both'
    if api:
        return 'api_missing' if api == fm.MISSING else 'api_questionable'
    if not fpl:
        return None
    status, chance, news = fpl['status'], fpl['chance'], fpl['news']
    back = fm.fpl_return_date(news, kickoff.date())
    if back is not None and status != 'a':
        return 'dated_before' if kickoff.date() < back else 'dated_after'
    if status in fm.FPL_OUT:
        return 'no_date'
    if status == 'd':
        return f'doubtful_{50 if chance is None else chance}' if fpl['available'] < 1 else 'doubtful_later'
    return 'other'


def build(snaps, lines, rounds, view='kickoff'):
    first = {(s, r): dt(k) for s, r, k in rounds}
    chosen = {}
    for s in snaps:
        fid, team, captured, created, kickoff, version = s[0], s[1], dt(s[2]), dt(s[3]), dt(s[4]), s[7]
        cutoff = kickoff if view == 'kickoff' else first[(s[8], s[9])] - DEADLINE_BEFORE
        key = (fid, team, version)
        if max(captured, created) < cutoff and (key not in chosen or captured > dt(chosen[key][2])):
            chosen[key] = s
    outcome = {(l[0], l[1], l[2]): (l[3] > 0, bool(l[4]) and l[3] > 0) for l in lines}
    rows = []
    for (fid, team, version), s in chosen.items():
        if version != NEW or (fid, team, OLD) not in chosen:
            continue
        old = {p['player_id']: p for p in chosen[(fid, team, OLD)][5]}
        fpl, api = s[6].get('fpl_availability', {}), chosen[(fid, team, OLD)][6].get('availability', {})
        for p in s[5]:
            pid = p['player_id']
            if pid not in old:
                continue
            played, started = outcome.get((fid, team, pid), (False, False))
            rows.append({'round': (s[8], s[9]), 'played': played, 'started': started,
                         'new_play': p['p_play'], 'old_play': old[pid]['p_play'],
                         'new_start': p['p_start'], 'old_start': old[pid]['p_start'],
                         'new_min': p['exp_minutes'], 'old_min': old[pid]['exp_minutes'],
                         'flagged': str(pid) in fpl, 'available': fpl.get(str(pid), {}).get('available', 1.0),
                         'bucket': bucket(fpl.get(str(pid)), api.get(str(pid)), dt(s[4]))})
    return rows


def log_loss(p, y):
    p = min(max(p, EPS), 1 - EPS)
    return -math.log(p if y else 1 - p)


def paired(rows, loss, rng):
    if not rows:
        return None
    by = defaultdict(list)
    for r in rows:
        by[r['round']].append(loss(r))
    keys = sorted(by)
    boot = []
    for _ in range(DRAWS):
        pick = [by[rng.choice(keys)] for _ in keys]
        boot.append(sum(map(sum, pick)) / sum(map(len, pick)))
    boot.sort()
    return {'n': len(rows), 'diff': sum(map(sum, by.values())) / len(rows),
            'lo': boot[int(.025 * DRAWS)], 'hi': boot[int(.975 * DRAWS) - 1]}


def refit(rows):
    """Each bucket's observed play rate against both versions, and its fitted factor."""
    out = {}
    by = defaultdict(list)
    for r in rows:
        if r['bucket']:
            by[r['bucket']].append(r)
    for b, rs in sorted(by.items()):
        rate = sum(r['played'] for r in rs) / len(rs)
        old = sum(r['old_play'] for r in rs) / len(rs)
        new = sum(r['new_play'] for r in rs) / len(rs)
        v16 = sum(r['available'] for r in rs) / len(rs)
        out[b] = {'n': len(rs), 'played': rate, 'v1_5_mean_p_play': old, 'v1_6_mean_p_play': new, 'v1_6_factor': v16,
                  'fitted_factor': min(rate / old, 1.0) if len(rs) >= MIN_BUCKET and old > 0 else v16}
    return out


def analyse(rows):
    rng = random.Random(SEED)
    play = lambda r: log_loss(r['new_play'], r['played']) - log_loss(r['old_play'], r['played'])
    start = lambda r: log_loss(r['new_start'], r['started']) - log_loss(r['old_start'], r['started'])
    minutes = lambda r: abs(r['new_min'] - 90 * r['played']) - abs(r['old_min'] - 90 * r['played'])
    flagged = [r for r in rows if r['flagged']]
    res = {'play_all': paired(rows, play, rng), 'play_flagged': paired(flagged, play, rng),
           'start_all': paired(rows, start, rng), 'start_flagged': paired(flagged, start, rng),
           'minutes_proxy_mae_flagged': paired(flagged, minutes, rng), 'buckets': refit(rows)}
    res['criteria'] = {'flagged_play_better': bool(res['play_flagged'] and res['play_flagged']['hi'] < 0),
                       'all_play_not_worse': bool(res['play_all'] and res['play_all']['hi'] <= ALL_MARGIN)}
    res['criteria']['supported'] = all(res['criteria'].values())
    return res


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--unblind', action='store_true', help='Outcome metrics, once the target is reached')
    parser.add_argument('--interim', action='store_true', help='Allow --unblind early; labelled a protocol deviation')
    args = parser.parse_args()
    data = extract()
    if data is None:
        print(json.dumps({'P12': 'fantasy_fixture_snapshots does not exist yet'}))
        return
    rows = build(*data)
    status = {'rounds': len({r['round'] for r in rows}), 'player_rows': len(rows),
              'flagged_rows': sum(r['flagged'] for r in rows),
              'target_rounds': TARGET_ROUNDS, 'target_flagged': TARGET_FLAGGED}
    status['target_reached'] = status['rounds'] >= TARGET_ROUNDS and status['flagged_rows'] >= TARGET_FLAGGED
    print(json.dumps(status, indent=1))
    (ROOT / 'status_P12.json').write_text(json.dumps(status, indent=2) + '\n')
    if not args.unblind:
        return
    if not status['target_reached'] and not args.interim:
        sys.exit('P12 target not reached; refusing to unblind (use --interim for a labelled protocol deviation)')
    out = {'status': status, 'deviation': None if status['target_reached'] else 'interim look before target',
           'kickoff_view': analyse(rows)}
    deadline = build(*data, view='deadline')
    if deadline:
        out['deadline_view'] = analyse(deadline)
    name = 'results_P12.json' if status['target_reached'] else 'interim_P12.json'
    (ROOT / name).write_text(json.dumps(out, indent=2, default=str) + '\n')
    print(json.dumps(out['kickoff_view']['criteria'], indent=1))


if __name__ == '__main__':
    main()
