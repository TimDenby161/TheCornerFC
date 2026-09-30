"""Prospective evaluation of fantasy v1.3 against v1.1 (PROTOCOLS.md, P9).

Read-only: one READ ONLY / REPEATABLE READ transaction, no API calls, nothing written to the
database or read by production. Blinded by default: without --unblind the output is accrual only.
--unblind refuses until the registered target; --interim overrides that and labels the output a
protocol deviation that cannot support a decision.

Target: the reconstructed total (fantasy.actual_points 'total', with the snapshot's position) plus
FPL's own bonus and defensive-contribution points from its final (data_checked) gameweek results,
as FPL's explain lists them. A player-fixture counts when both versions' chosen snapshots have him,
his club plays once that gameweek, and FPL has a final result for him.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import importlib.util
import json
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from thecornerfc import fantasy as fm

ROOT = Path(__file__).parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p8, p11 = _load('fantasy_p8'), _load('fantasy_p11')

# Registered in PROTOCOLS.md (P9); change only by a dated amendment there.
TARGET_ROUNDS, TARGET_ROWS = 10, 3000
OLD, NEW = 'fantasy-v1.1', 'fantasy-v1.3'
DEADLINE_BEFORE = timedelta(minutes=90)
SEED = 20260929
FPL_EXTRA = ('bonus', 'defensive_contribution')      # FPL explain identifiers added to the target


def dt(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))


def extract(versions=(OLD, NEW)):
    from dotenv import dotenv_values
    import psycopg
    with psycopg.connect(dotenv_values('.env')['DATABASE_URL'].strip(), connect_timeout=15,
                         options='-c default_transaction_read_only=on') as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        if c.execute("select to_regclass('public.fantasy_fixture_snapshots')").fetchone()[0] is None:
            return None
        snaps = c.execute('''select s.fixture_id, s.team_id, s.captured_at, s.created_at, s.effective_at, s.predictions,
                                    mv.version_name, f.season, f.round, f.home_team_id, f.away_team_id,
                                    f.home_goals, f.away_goals
                             from fantasy_fixture_snapshots s join fixtures f using (fixture_id)
                             join model_versions mv using (model_version_id)
                             where mv.version_name = any(%s)
                               and s.source = 'prospective' and s.captured_at < s.effective_at
                               and s.created_at < s.effective_at and f.status_short = 'FT' ''', [list(versions)]).fetchall()
        fids = sorted({s[0] for s in snaps})
        seasons = sorted({s[7] for s in snaps})
        lines = c.execute('''select fixture_id, team_id, player_id, minutes, started, coalesce(goals,0), coalesce(assists,0),
                                    coalesce(saves,0), coalesce(penalties_saved,0), coalesce(yellow_cards,0), coalesce(red_cards,0)
                             from fixture_players where fixture_id = any(%s)''', [fids]).fetchall()
        rounds = c.execute('''select season, round, min(kickoff) from fixtures where league_id = 39
                              and (season, round) in (select season, round from fixtures where fixture_id = any(%s))
                              group by 1, 2''', [fids]).fetchall()
        fpl = {}
        for season in seasons:
            cap = c.execute('''select fixtures, capture_id from fpl_captures where season = %s
                               order by captured_at desc, capture_id desc limit 1''', [season]).fetchone()
            if not cap:
                continue
            teams = dict(c.execute('''select fpl_id, api_id from fpl_id_map_current
                                      where kind = 'team' and season = %s and api_id is not null''', [season]).fetchall())
            players = dict(c.execute('''select fpl_id, api_id from fpl_id_map_current
                                        where kind = 'player' and season = %s and api_id is not null''', [season]).fetchall())
            results = c.execute('''select c.event_id, r.fpl_player_id, r.explain
                                   from (select distinct on (event_id) event_id, result_capture_id from fpl_result_captures
                                         where season = %s and data_checked
                                         order by event_id, captured_at desc, result_capture_id desc) c
                                   join fpl_player_results r using (result_capture_id)''', [season]).fetchall()
            positions = dict(c.execute('select fpl_player_id, position from fpl_player_states where capture_id = %s',
                                       [cap[1]]).fetchall())
            fpl[season] = {'fixtures': cap[0], 'teams': teams, 'players': players, 'results': results,
                           'positions': positions}
    return snaps, lines, rounds, fpl


def fpl_extra_points(explain):
    """{identifier: points} over FPL's explain for one player-gameweek, for FPL_EXTRA."""
    out = dict.fromkeys(FPL_EXTRA, 0)
    for fixture in explain or []:
        for s in fixture.get('stats') or []:
            if s.get('identifier') in out:
                out[s['identifier']] += s.get('points') or 0
    return out


def build(snaps, lines, rounds, fpl, view='kickoff', old_version=OLD, new_version=NEW):
    first = {(s, r): dt(k) for s, r, k in rounds}
    chosen = {}
    for s in snaps:
        fid, team, captured, created, kickoff, version = s[0], s[1], dt(s[2]), dt(s[3]), dt(s[4]), s[6]
        cutoff = kickoff if view == 'kickoff' else first[(s[7], s[8])] - DEADLINE_BEFORE
        key = (fid, team, version)
        if max(captured, created) < cutoff and (key not in chosen or captured > dt(chosen[key][2])):
            chosen[key] = s
    event_of, count = {}, defaultdict(int)
    extra = {}
    for season, f in fpl.items():
        for x in f['fixtures']:
            h, a = f['teams'].get(x.get('fpl_team_h')), f['teams'].get(x.get('fpl_team_a'))
            if x.get('event_id') and h and a:
                event_of[(season, h, a)] = x['event_id']
                count[(season, x['event_id'], h)] += 1
                count[(season, x['event_id'], a)] += 1
        for event, fpl_id, explain in f['results']:
            api = f['players'].get(fpl_id)
            if api:
                extra[(season, event, api)] = dict(fpl_extra_points(explain),
                                                   position=p11.FPL_POSITIONS.get((f.get('positions') or {}).get(fpl_id)))
    actual = {(l[0], l[2]): l for l in lines}
    rows = []
    for (fid, team, version), s in chosen.items():
        if version != new_version or (fid, team, old_version) not in chosen:
            continue
        old = {p['player_id']: p for p in chosen[(fid, team, old_version)][5]}
        season = s[7]
        event = event_of.get((season, s[9], s[10]))
        if event is None or count[(season, event, team)] != 1:
            continue
        conceded = s[12] if team == s[9] else s[11]
        for p in s[5]:
            pid = p['player_id']
            if pid not in old or (season, event, pid) not in extra:
                continue
            l = actual.get((fid, pid))
            on = bool(l and l[1] == team)
            pts = fm.actual_points(p['position'], l[3], l[5], l[6], conceded, l[7], l[8], l[9], l[10]) if on \
                else fm.actual_points(p['position'], 0, team_conceded=conceded)
            e = extra[(season, event, pid)]
            rows.append({'round': (season, event), 'position': p['position'],
                         'actual': pts['total'] + e['bonus'] + e['defensive_contribution'],
                         'bonus': e['bonus'], 'dc': e['defensive_contribution'],
                         'new': p['expected_points'], 'old': old[pid]['expected_points'],
                         'new_bonus': p.get('bonus_points', 0.0), 'new_dc': p.get('dc_points', 0.0),
                         'old_dc': old[pid].get('dc_points', 0.0), 'fpl_position': e['position'],
                         'fpl_dc_minutes': p.get('fpl_dc_minutes'),
                         'started': bool(on and l[4] and l[3] > 0),
                         'new_start': p['p_start'], 'old_start': old[pid]['p_start']})
    return rows


def bias(rows, key):
    act = sum(r['actual'] for r in rows) / len(rows)
    return (sum(r[key] for r in rows) / len(rows) - act) / act * 100 if act else None


def analyse(rows):
    rng = random.Random(SEED)
    mae = lambda r: abs(r['new'] - r['actual']) - abs(r['old'] - r['actual'])
    mse = lambda r: (r['new'] - r['actual']) ** 2 - (r['old'] - r['actual']) ** 2
    res = {'mae': p11.paired(rows, mae, rng), 'mse': p11.paired(rows, mse, rng)}
    by_pos = {p: [r for r in rows if r['position'] == p] for p in fm.GOAL_POINTS}
    by_pos = {p: rs for p, rs in by_pos.items() if rs}
    res['bias_pct'] = {'overall': {'v1_3': bias(rows, 'new'), 'v1_1': bias(rows, 'old')},
                       **{p: {'v1_3': bias(rs, 'new'), 'v1_1': bias(rs, 'old')} for p, rs in by_pos.items()}}
    res['bonus_dc_by_position'] = {p: {'n': len(rs),
                                       'bonus_pred': sum(r['new_bonus'] for r in rs) / len(rs),
                                       'bonus_fpl': sum(r['bonus'] for r in rs) / len(rs),
                                       'dc_pred': sum(r['new_dc'] for r in rs) / len(rs),
                                       'dc_fpl': sum(r['dc'] for r in rs) / len(rs)} for p, rs in by_pos.items()}
    keepers = by_pos.get('G', [])
    if keepers:
        y = [r['started'] for r in keepers]
        res['gk_start_ece'] = {'v1_3': p8.calibration([r['new_start'] for r in keepers], y)['ece'],
                               'v1_1': p8.calibration([r['old_start'] for r in keepers], y)['ece']}
    res['criteria'] = {'mae_better': res['mae']['hi'] < 0, 'mse_better': res['mse']['hi'] < 0}
    res['criteria']['supported'] = all(res['criteria'].values())
    return res


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--unblind', action='store_true', help='Outcome metrics, once the target is reached')
    parser.add_argument('--interim', action='store_true', help='Allow --unblind early; labelled a protocol deviation')
    args = parser.parse_args()
    data = extract()
    if data is None:
        print(json.dumps({'P9': 'fantasy_fixture_snapshots does not exist yet'}))
        return
    rows = build(*data)
    status = {'rounds': len({r['round'] for r in rows}), 'player_rows': len(rows),
              'target_rounds': TARGET_ROUNDS, 'target_rows': TARGET_ROWS}
    status['target_reached'] = status['rounds'] >= TARGET_ROUNDS and status['player_rows'] >= TARGET_ROWS
    print(json.dumps(status, indent=1))
    (ROOT / 'status_P9.json').write_text(json.dumps(status, indent=2) + '\n')
    if not args.unblind:
        return
    if not status['target_reached'] and not args.interim:
        sys.exit('P9 target not reached; refusing to unblind (use --interim for a labelled protocol deviation)')
    out = {'status': status, 'deviation': None if status['target_reached'] else 'interim look before target',
           'kickoff_view': analyse(rows)}
    deadline = build(*data, view='deadline')
    if deadline:
        out['deadline_view'] = analyse(deadline)
    name = 'results_P9.json' if status['target_reached'] else 'interim_P9.json'
    (ROOT / name).write_text(json.dumps(out, indent=2, default=str) + '\n')
    print(json.dumps(out['kickoff_view']['criteria'], indent=1))


if __name__ == '__main__':
    main()
