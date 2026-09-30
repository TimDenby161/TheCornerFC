"""Prospective evaluation of fantasy v1.5 against v1.4 (PROTOCOLS.md, P11).

Read-only: one READ ONLY / REPEATABLE READ transaction, no API calls, nothing written to the
database or read by production. Blinded by default: without --unblind the output is accrual only.
--unblind refuses until the registered target; --interim overrides that and labels the output a
protocol deviation that cannot support a decision.

Target: FPL's own final gameweek results. Attacking points = goal points at FPL's position x goals
+ 3 x assists - 2 x penalties missed (FPL's assists include the ones API-Football doesn't record).
Predictions are rescored at FPL's position from their stored parts. A player-fixture counts when
both versions' chosen snapshots have him, his club plays once that gameweek, and FPL has a final
(data_checked) result for him.
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
from thecornerfc import fantasy as fm

ROOT = Path(__file__).parent
# Registered in PROTOCOLS.md (P11); change only by a dated amendment there.
TARGET_ROUNDS, TARGET_ROWS = 10, 3000
OLD, NEW = 'fantasy-v1.4', 'fantasy-v1.5'
DEADLINE_BEFORE = timedelta(minutes=90)
SEED, DRAWS = 20260930, 2000
MAE_MARGIN = 0.02                 # all-points MAE may be at most this much worse (upper end of the interval)
TAKER_SHARE = 0.5                 # the takers' subgroup: predicted share of the club's penalties above this
FPL_POSITIONS = {'GKP': 'G', 'DEF': 'D', 'MID': 'M', 'FWD': 'F'}


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
                                    mv.version_name, f.season, f.round, f.home_team_id, f.away_team_id
                             from fantasy_fixture_snapshots s join fixtures f using (fixture_id)
                             join model_versions mv using (model_version_id)
                             where mv.version_name = any(%s)
                               and s.source = 'prospective' and s.captured_at < s.effective_at
                               and s.created_at < s.effective_at and f.status_short = 'FT' ''', [[OLD, NEW]]).fetchall()
        fids = sorted({s[0] for s in snaps})
        seasons = sorted({s[7] for s in snaps})
        rounds = c.execute('''select season, round, min(kickoff) from fixtures where league_id = 39
                              and (season, round) in (select season, round from fixtures where fixture_id = any(%s))
                              group by 1, 2''', [fids]).fetchall()
        pens = c.execute('''select fixture_id, team_id, player_id, coalesce(penalties_scored, 0) + coalesce(penalties_missed, 0)
                            from fixture_players where fixture_id = any(%s)''', [fids]).fetchall()
        fpl = {}
        for season in seasons:
            cap = c.execute('''select capture_id, fixtures from fpl_captures where season = %s
                               order by captured_at desc, capture_id desc limit 1''', [season]).fetchone()
            if not cap:
                continue
            teams = dict(c.execute('''select fpl_id, api_id from fpl_id_map_current
                                      where kind = 'team' and season = %s and api_id is not null''', [season]).fetchall())
            players = dict(c.execute('''select fpl_id, api_id from fpl_id_map_current
                                        where kind = 'player' and season = %s and api_id is not null''', [season]).fetchall())
            positions = dict(c.execute('select fpl_player_id, position from fpl_player_states where capture_id = %s',
                                       [cap[0]]).fetchall())
            results = c.execute('''select c.event_id, r.fpl_player_id, r.minutes, r.stats
                                   from (select distinct on (event_id) event_id, result_capture_id from fpl_result_captures
                                         where season = %s and data_checked
                                         order by event_id, captured_at desc, result_capture_id desc) c
                                   join fpl_player_results r using (result_capture_id)''', [season]).fetchall()
            fpl[season] = {'fixtures': cap[1], 'teams': teams, 'players': players, 'positions': positions,
                           'results': results}
    return snaps, rounds, pens, fpl


def fpl_targets(fpl):
    """{(season, api home, api away): event}, {(season, event, api team): fixtures that gameweek},
    {(season, event, api player): (FPL position letter, goals, assists, penalties missed, total points)}."""
    event_of, count, target = {}, defaultdict(int), {}
    for season, f in fpl.items():
        for x in f['fixtures']:
            h, a = f['teams'].get(x.get('fpl_team_h')), f['teams'].get(x.get('fpl_team_a'))
            if x.get('event_id') and h and a:
                event_of[(season, h, a)] = x['event_id']
                count[(season, x['event_id'], h)] += 1
                count[(season, x['event_id'], a)] += 1
        for event, fpl_id, minutes, stats in f['results']:
            api, pos = f['players'].get(fpl_id), FPL_POSITIONS.get(f['positions'].get(fpl_id))
            if api and pos:
                target[(season, event, api)] = (pos, stats.get('goals_scored', 0), stats.get('assists', 0),
                                                stats.get('penalties_missed', 0), stats.get('total_points', 0))
    return event_of, count, target


def attacking(p, pos):
    """Predicted attacking points at FPL's position from a stored prediction (either version)."""
    fpl_assists = p.get('exp_fpl_pen_assists', 0.0) + p.get('exp_fpl_other_assists', 0.0)
    return (fm.GOAL_POINTS[pos] * p['exp_goals'] + fm.ASSIST_POINTS * (p['exp_assists'] + fpl_assists)
            + fm.PENALTY_MISS_POINTS * p.get('exp_pen_misses', 0.0))


def build(snaps, rounds, pens, fpl, view='kickoff'):
    """Paired rows, one per player-fixture in both versions' chosen snapshots with an FPL target, and
    the team-fixtures with penalties (for the taker secondary)."""
    first = {(s, r): dt(k) for s, r, k in rounds}
    chosen = {}
    for s in snaps:
        fid, team, captured, created, kickoff, version = s[0], s[1], dt(s[2]), dt(s[3]), dt(s[4]), s[6]
        cutoff = kickoff if view == 'kickoff' else first[(s[7], s[8])] - DEADLINE_BEFORE
        key = (fid, team, version)
        if max(captured, created) < cutoff and (key not in chosen or captured > dt(chosen[key][2])):
            chosen[key] = s
    event_of, count, target = fpl_targets(fpl)
    attempts = defaultdict(dict)
    for fid, team, pid, n in pens:
        if n:
            attempts[(fid, team)][pid] = n
    rows, takers = [], []
    for (fid, team, version), s in chosen.items():
        if version != NEW or (fid, team, OLD) not in chosen:
            continue
        old = {p['player_id']: p for p in chosen[(fid, team, OLD)][5]}
        new = {p['player_id']: p for p in s[5]}
        season = s[7]
        event = event_of.get((season, s[9], s[10]))
        if event is None or count[(season, event, team)] != 1:
            continue                     # FPL has no gameweek for it, or a double gameweek
        team_pen = sum(p.get('exp_pen_goals', 0.0) for p in new.values())
        for pid in sorted(set(old) & set(new)):
            t = target.get((season, event, pid))
            if t is None:
                continue
            pos, goals, assists, missed, total = t
            actual = fm.GOAL_POINTS[pos] * goals + fm.ASSIST_POINTS * assists + fm.PENALTY_MISS_POINTS * missed
            a_old, a_new = attacking(old[pid], pos), attacking(new[pid], pos)
            # all points: stored expected points with the attacking part moved to FPL's position
            all_old = old[pid]['expected_points'] - attacking(old[pid], old[pid]['position']) + a_old
            all_new = new[pid]['expected_points'] - attacking(new[pid], new[pid]['position']) + a_new
            rows.append({'round': (season, event), 'actual': actual, 'total': total, 'old': a_old, 'new': a_new,
                         'all_old': all_old, 'all_new': all_new,
                         'share': new[pid].get('exp_pen_goals', 0.0) / team_pen if team_pen else 0.0})
        took = attempts.get((fid, team))
        if took:
            takers.append({'round': (season, event), 'took': took,
                           'new': {pid: p.get('exp_pen_goals', 0.0) for pid, p in new.items()},
                           'old': {pid: p['exp_goals'] for pid, p in old.items()}})
    return rows, takers


def paired(rows, loss, rng):
    """Mean of loss(row) (v1.5 minus v1.4) with a 95% round-cluster bootstrap."""
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


def taker_log_loss(takers, version):
    """Mean -log(predicted share of the player who took each penalty) among the snapshot's players;
    takers outside the snapshot count at a floor of 1e-6."""
    total = n = 0
    for t in takers:
        weights = t[version]
        s = sum(weights.values())
        for pid, k in t['took'].items():
            total -= k * math.log(max(weights.get(pid, 0.0) / s if s else 0.0, 1e-6))
            n += k
    return {'penalties': n, 'log_loss': total / n if n else None}


def analyse(rows, takers):
    rng = random.Random(SEED)
    att_mae = lambda r: abs(r['new'] - r['actual']) - abs(r['old'] - r['actual'])
    att_mse = lambda r: (r['new'] - r['actual']) ** 2 - (r['old'] - r['actual']) ** 2
    all_mae = lambda r: abs(r['all_new'] - r['total']) - abs(r['all_old'] - r['total'])
    all_mse = lambda r: (r['all_new'] - r['total']) ** 2 - (r['all_old'] - r['total']) ** 2
    sub = [r for r in rows if r['share'] > TAKER_SHARE]
    res = {'attacking': {'mae': paired(rows, att_mae, rng), 'mse': paired(rows, att_mse, rng)},
           'all_points': {'mae': paired(rows, all_mae, rng), 'mse': paired(rows, all_mse, rng)},
           'takers_subgroup': {'mae': paired(sub, att_mae, rng), 'mse': paired(sub, att_mse, rng)} if sub else None,
           'taker_log_loss': {'v1_5': taker_log_loss(takers, 'new'), 'v1_4_goal_share': taker_log_loss(takers, 'old')},
           'bias': {'actual': sum(r['actual'] for r in rows) / len(rows),
                    'v1_4': sum(r['old'] for r in rows) / len(rows), 'v1_5': sum(r['new'] for r in rows) / len(rows)}}
    res['criteria'] = {'attacking_mae_better': res['attacking']['mae']['hi'] < 0,
                       'all_points_mae_not_worse': res['all_points']['mae']['hi'] <= MAE_MARGIN}
    res['criteria']['supported'] = all(res['criteria'].values())
    return res


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--unblind', action='store_true', help='Outcome metrics, once the target is reached')
    parser.add_argument('--interim', action='store_true', help='Allow --unblind early; labelled a protocol deviation')
    args = parser.parse_args()
    data = extract()
    if data is None:
        print(json.dumps({'P11': 'fantasy_fixture_snapshots does not exist yet'}))
        return
    rows, takers = build(*data)
    status = {'rounds': len({r['round'] for r in rows}), 'player_rows': len(rows),
              'team_fixtures_with_penalties': len(takers), 'target_rounds': TARGET_ROUNDS, 'target_rows': TARGET_ROWS}
    status['target_reached'] = status['rounds'] >= TARGET_ROUNDS and status['player_rows'] >= TARGET_ROWS
    print(json.dumps(status, indent=1))
    (ROOT / 'status_P11.json').write_text(json.dumps(status, indent=2) + '\n')
    if not args.unblind:
        return
    if not status['target_reached'] and not args.interim:
        sys.exit('P11 target not reached; refusing to unblind (use --interim for a labelled protocol deviation)')
    out = {'status': status, 'deviation': None if status['target_reached'] else 'interim look before target',
           'kickoff_view': analyse(rows, takers)}
    deadline = build(*data, view='deadline')
    if deadline[0]:
        out['deadline_view'] = analyse(*deadline)
    name = 'results_P11.json' if status['target_reached'] else 'interim_P11.json'
    (ROOT / name).write_text(json.dumps(out, indent=2, default=str) + '\n')
    print(json.dumps(out['kickoff_view']['criteria'], indent=1))


if __name__ == '__main__':
    main()
