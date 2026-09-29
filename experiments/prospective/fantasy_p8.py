"""Prospective evaluation of fantasy v1.1 (PROTOCOLS.md, P8).

Read-only: one READ ONLY / REPEATABLE READ transaction, no API calls, nothing written to the
database or read by production. Blinded by default: without --unblind the output is accrual only.
--unblind refuses until the registered target; --interim overrides that and labels the output a
protocol deviation that cannot support a decision.
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
from dotenv import dotenv_values
import psycopg
from thecornerfc import fantasy as fm

ROOT = Path(__file__).parent
# Registered in PROTOCOLS.md (P8); change only by a dated amendment there.
TARGET_ROUNDS, TARGET_ROWS = 10, 3000
MODEL = 'fantasy-v1.1'             # the table also holds v1.3's rows (P9) from 2026-09-29
DEADLINE_BEFORE = timedelta(minutes=90)      # FPL-style deadline: before the round's first kickoff
SEED, DRAWS = 20260927, 2000
TOP_N = (10, 25)


def dt(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))


def extract():
    with psycopg.connect(dotenv_values('.env')['DATABASE_URL'].strip(), connect_timeout=15,
                         options='-c default_transaction_read_only=on') as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        if c.execute("select to_regclass('public.fantasy_fixture_snapshots')").fetchone()[0] is None:
            return None
        snaps = c.execute('''select s.fixture_id, s.team_id, s.captured_at, s.created_at, s.effective_at, s.predictions,
                                    s.inputs, s.model_version_id, f.season, f.round, f.home_team_id, f.home_goals, f.away_goals
                             from fantasy_fixture_snapshots s join fixtures f using (fixture_id)
                             join model_versions mv using (model_version_id)
                             where mv.version_name = %s                 -- v1.1 only (Amendment 3)
                               and s.source = 'prospective' and s.captured_at < s.effective_at
                               and s.created_at < s.effective_at and f.status_short = 'FT' ''', [MODEL]).fetchall()
        fids = sorted({s[0] for s in snaps})
        lines = c.execute('''select fixture_id, team_id, player_id, minutes, started, coalesce(goals,0), coalesce(assists,0),
                                    coalesce(saves,0), coalesce(penalties_saved,0), coalesce(yellow_cards,0), coalesce(red_cards,0)
                             from fixture_players where fixture_id = any(%s)''', [fids]).fetchall()
        rounds = c.execute('''select season, round, min(kickoff) from fixtures where league_id = 39
                              and (season, round) in (select season, round from fixtures where fixture_id = any(%s))
                              group by 1, 2''', [fids]).fetchall()
    return snaps, lines, rounds


def build(snaps, lines, rounds, view='kickoff'):
    """One row per snapshot player: prediction, stored benchmarks and reconstructed actual points."""
    first = {(s, r): dt(k) for s, r, k in rounds}
    chosen = {}
    for s in snaps:
        fid, team, captured, created, kickoff = s[0], s[1], dt(s[2]), dt(s[3]), dt(s[4])
        cutoff = kickoff if view == 'kickoff' else first[(s[8], s[9])] - DEADLINE_BEFORE
        if max(captured, created) < cutoff and ((fid, team) not in chosen or captured > dt(chosen[(fid, team)][2])):
            chosen[(fid, team)] = s
    actual = {(l[0], l[2]): l for l in lines}
    played = defaultdict(set)
    for l in lines:
        if l[3] > 0:
            played[(l[0], l[1])].add(l[2])
    rows, teams, outside = [], [], 0
    for (fid, team), s in chosen.items():
        preds, inputs = s[5], s[6]
        conceded = s[12] if team == s[10] else s[11]
        teams.append({'round': (s[8], s[9]), 'p_cs': preds[0]['team_p_clean_sheet'], 'cs': conceded == 0})
        inside = set()
        for p in preds:
            pid = p['player_id']
            inside.add(pid)
            l = actual.get((fid, pid))
            pts = fm.actual_points(p['position'], l[3], l[5], l[6], conceded, l[7], l[8], l[9], l[10]) if l and l[1] == team \
                else fm.actual_points(p['position'], 0, team_conceded=conceded)
            b = inputs['benchmarks'].get(str(pid), {})
            rows.append(dict(round=(s[8], s[9]), position=p['position'], pred=p, total=pts['total'], v1=pts['v1'],
                             minutes=l[3] if l and l[1] == team else 0, started=bool(l and l[1] == team and l[4] and l[3] > 0),
                             ppg=b.get('ppg', 0.0), recent5=b.get('recent5', 0.0), recent5_min=b.get('recent5_minutes', 0.0)))
        outside += len(played[(fid, team)] - inside)       # appearances by players the snapshot left out
    return rows, teams, outside


def ranks(x):
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def pearson(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else None


def metrics(pred, act):
    err = [p - a for p, a in zip(pred, act)]
    mean_act = sum(act) / len(act)
    return {'n': len(pred), 'mae': sum(map(abs, err)) / len(err), 'rmse': math.sqrt(sum(e * e for e in err) / len(err)),
            'pearson': pearson(pred, act), 'spearman': pearson(ranks(pred), ranks(act)),
            'bias_pct': sum(err) / len(err) / mean_act * 100 if mean_act else None}


def calibration(p, y, bins=10):
    ece, table = 0.0, []
    for b in range(bins):
        idx = [i for i, v in enumerate(p) if min(int(v * bins), bins - 1) == b]
        if idx:
            mp, my = sum(p[i] for i in idx) / len(idx), sum(y[i] for i in idx) / len(idx)
            ece += len(idx) / len(p) * abs(mp - my)
            table.append({'bin': b, 'n': len(idx), 'mean_p': mp, 'rate': my})
    return {'n': len(p), 'ece': ece, 'bins': table}


def paired(rows, a, b, loss, rng):
    by = defaultdict(list)
    for r in rows:
        by[r['round']].append(loss(r, a) - loss(r, b))
    keys = sorted(by)
    diff = sum(sum(v) for v in by.values()) / len(rows)
    boot = []
    for _ in range(DRAWS):
        pick = [by[rng.choice(keys)] for _ in keys]
        boot.append(sum(map(sum, pick)) / sum(map(len, pick)))
    boot.sort()
    return {'diff': diff, 'lo': boot[int(.025 * DRAWS)], 'hi': boot[int(.975 * DRAWS) - 1]}


def value(r, name):
    return r['pred']['expected_points'] if name == 'model' else r[name]


def top_n(rows, name, n, rng):
    by = defaultdict(list)
    for r in rows:
        by[r['round']].append(r)
    hits = []
    for rr in by.values():
        if len(rr) < n:
            continue
        threshold = sorted((r['total'] for r in rr), reverse=True)[n - 1]
        pick = sorted(rr, key=lambda r: (value(r, name), rng.random()), reverse=True)[:n]
        hits.append(sum(r['total'] >= threshold for r in pick) / n)
    return sum(hits) / len(hits) if hits else None


def analyse(rows, teams, outside):
    rng = random.Random(SEED)
    act = [r['total'] for r in rows]
    res = {name: metrics([value(r, name) for r in rows], act) for name in ('model', 'recent5', 'ppg')}
    ab = lambda r, n: abs(value(r, n) - r['total'])
    sq = lambda r, n: (value(r, n) - r['total']) ** 2
    res['vs'] = {b: {'mae': paired(rows, 'model', b, ab, rng), 'mse': paired(rows, 'model', b, sq, rng)} for b in ('recent5', 'ppg')}
    v1 = metrics([r['pred']['expected_points'] for r in rows], [r['v1'] for r in rows])
    pos = {p: metrics([r['pred']['expected_points'] for r in rows if r['position'] == p],
                      [r['v1'] for r in rows if r['position'] == p])['bias_pct'] for p in fm.GOAL_POINTS
           if any(r['position'] == p for r in rows)}
    start = calibration([r['pred']['p_start'] for r in rows], [r['started'] for r in rows])
    cs = calibration([t['p_cs'] for t in teams], [t['cs'] for t in teams])
    mins = [r['pred']['exp_minutes'] for r in rows]
    res.update(v1_scope=v1, position_bias_pct=pos, start_calibration=start, team_clean_sheet=cs,
               minutes={'mae': sum(abs(m - r['minutes']) for m, r in zip(mins, rows)) / len(rows),
                        'recent5_mae': sum(abs(r['recent5_min'] - r['minutes']) for r in rows) / len(rows),
                        'rmse': math.sqrt(sum((m - r['minutes']) ** 2 for m, r in zip(mins, rows)) / len(rows)),
                        'recent5_rmse': math.sqrt(sum((r['recent5_min'] - r['minutes']) ** 2 for r in rows) / len(rows))},
               top_n={name: {n: top_n(rows, name, n, rng) for n in TOP_N} for name in ('model', 'recent5', 'ppg')},
               outside_appearances=outside)
    res['criteria'] = {
        '1_beats_recent_and_ppg': all(res['vs'][b][m]['hi'] < 0 for b in res['vs'] for m in ('mae', 'mse')),
        '2_bias': abs(v1['bias_pct']) <= 5 and all(abs(b) <= 10 for b in pos.values()),
        '3_calibration': start['ece'] <= 0.03 and cs['ece'] <= 0.03}
    res['criteria']['all_passed'] = all(res['criteria'].values())
    return res


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--unblind', action='store_true', help='Outcome metrics, once the target is reached')
    parser.add_argument('--interim', action='store_true', help='Allow --unblind early; labelled a protocol deviation')
    args = parser.parse_args()
    data = extract()
    if data is None:
        print(json.dumps({'P8': 'fantasy_fixture_snapshots does not exist yet'}))
        return
    rows, teams, outside = build(*data)
    status = {'rounds': len({r['round'] for r in rows}), 'player_rows': len(rows), 'team_fixtures': len(teams),
              'target_rounds': TARGET_ROUNDS, 'target_rows': TARGET_ROWS,
              'model_versions': sorted({s[7] for s in data[0]})}
    status['target_reached'] = status['rounds'] >= TARGET_ROUNDS and status['player_rows'] >= TARGET_ROWS
    print(json.dumps(status, indent=1))
    (ROOT / 'status_P8.json').write_text(json.dumps(status, indent=2) + '\n')
    if not args.unblind:
        return
    if not status['target_reached'] and not args.interim:
        sys.exit('P8 target not reached; refusing to unblind (use --interim for a labelled protocol deviation)')
    out = {'status': status, 'deviation': None if status['target_reached'] else 'interim look before target',
           'kickoff_view': analyse(rows, teams, outside)}
    deadline = build(*data, view='deadline')
    if deadline[0]:
        out['deadline_view'] = analyse(*deadline)
    name = 'results_P8.json' if status['target_reached'] else 'interim_P8.json'
    (ROOT / name).write_text(json.dumps(out, indent=2, default=str) + '\n')
    print(json.dumps(out['kickoff_view']['criteria'], indent=1))


if __name__ == '__main__':
    main()
