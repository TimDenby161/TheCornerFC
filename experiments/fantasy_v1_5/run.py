"""Fantasy v1.5 (DESIGN.md): penalty takers, misses and FPL-only assists on top of v1.4.
Fit on 2024-25, test on 2025-26 and 2026-27 to date (actual minutes: who takes / scores, not how
many play). Reads the database once (read-only) into inputs.json.gz; rerun with --refresh to
rebuild it. Writes results.json and thecornerfc/fantasy_games/fantasy_params_v1_5.json. Plain Python."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from thecornerfc.fantasy_games import fantasy as fm

ROOT = Path(__file__).parent
INPUTS = ROOT / 'inputs.json.gz'
V14_PARAMS = Path('thecornerfc/fantasy_games/fantasy_params_v1_4.json')
V15_PARAMS = Path('thecornerfc/fantasy_games/fantasy_params_v1_5.json')
FIT, TEST = (2024,), (2025, 2026)
START = '2024-07-01'
ALPHAS = [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]
DECAYS = [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
POWERS = [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2]
SHRINK = [10, 25, 50, 100, 200, 400, 1000]
# FPL's penalty order has no history to fit on: fixed before any v1.5 prediction, judged prospectively
ORDER_WEIGHT, ORDER_RATIO = 0.75, 0.15


def extract(params):
    """Team-matches of Premier League fixtures since START, each player on the pitch with his
    features as known before kickoff, plus league rates and FPL GW assist totals."""
    from datetime import datetime, timezone
    from thecornerfc.pipeline import db
    from thecornerfc.fantasy_games import fantasy_snapshots as fs
    conn = db.connect()
    history = fs.History(fs._pl_lines(conn))
    start = datetime.fromisoformat(START).replace(tzinfo=timezone.utc)
    teams_of = defaultdict(list)
    for team, ms in history.team_matches.items():
        for fid, _ in ms:
            teams_of[fid].append(team)
    rows, league = [], Counter()
    for team, ms in history.team_matches.items():
        for fid, players in ms:
            kickoff = history.kickoffs[fid]
            if kickoff < start:
                continue
            season = history.season_of[fid]
            opp = [t for t in teams_of[fid] if t != team]
            recent = history.team_recent(team, kickoff)
            team_recent = [{p: (l['started'], l['minutes']) for p, l in ps.items()} for _, ps in recent]
            on = []
            for pid, l in players.items():
                if l['minutes'] <= 0:
                    continue
                position = history.label(pid, season)
                if position is None:
                    continue
                r = dict(fm.player_features(pid, kickoff, team_recent, [a for a in history.appearances[pid] if a[0] < kickoff],
                                            team=team), position=position)
                on.append({'player': pid, 'position': position, 'minutes': l['minutes'], 'goals': l['goals'], 'assists': l['assists'],
                           'pens_scored': l['pens_scored'], 'pens_missed': l['pens_missed'], 'pens_won': l['pens_won'],
                           'np_rate': fm.goal_rate(r, params, non_penalty=True), 'rate': fm.goal_rate(r, params),
                           'pen_hist': r.get('pen_hist', [])})
                league[(position, 'minutes')] += l['minutes']
                for k in ('shots', 'fouls_drawn', 'pens_won', 'pens_scored', 'pens_missed', 'goals'):
                    league[(position, k)] += l[k]
            # a team's penalties won earlier this year = the other side's committed; attempts are its own
            won_before = [sum(l.get('pens_scored', 0) + l.get('pens_missed', 0) for l in ps.values()) for _, ps in recent]
            rows.append({'fixture': fid, 'team': team, 'season': season, 'kickoff': kickoff.isoformat(),
                         'lam': history.lam_against.get((fid, opp[0])) if opp else None,
                         'team_attempts_before': sum(won_before), 'team_matches_before': len(won_before),
                         'players': on})
    gw = conn.execute("select event_id, min(deadline) from fpl_gameweeks where season = 2026 group by 1 order by 1").fetchall()
    checked = [e for e, in conn.execute("""select distinct event_id from fpl_result_captures
                                          where season = 2026 and data_checked order by 1""")]
    end = next(d for e, d in gw if e == max(checked) + 1)
    fpl_assists, fpl_goals = conn.execute(
        """select sum((r.stats->>'assists')::int), sum((r.stats->>'goals_scored')::int)
           from (select distinct on (event_id) result_capture_id from fpl_result_captures where season = 2026 and data_checked
                 order by event_id, captured_at desc) c join fpl_player_results r using (result_capture_id)""").fetchone()
    per_player = conn.execute(
        """with f as (select m.api_id, sum((r.stats->>'assists')::int) a
                      from (select distinct on (event_id) result_capture_id from fpl_result_captures
                            where season = 2026 and data_checked order by event_id, captured_at desc) c
                      join fpl_player_results r using (result_capture_id)
                      join fpl_id_map_current m on m.kind = 'player' and m.season = 2026 and m.fpl_id = r.fpl_player_id
                      where m.api_id is not null group by 1),
                a as (select player_id, sum(coalesce(assists, 0)) a, sum(coalesce(shots, 0)) s, sum(coalesce(key_passes, 0)) kp,
                             sum(minutes) m
                      from fixture_players p join fixtures x using (fixture_id)
                      where league_id = 39 and season = 2026 and kickoff < %s group by 1)
           select a.player_id, f.a, a.a, a.s, a.kp, a.m from a join f on f.api_id = a.player_id""", [end]).fetchall()
    # aggregates only: per-player FPL figures stay out of the (public) extract
    pl = [(fa - aa, s / m * 90, kp / m * 90) for _, fa, aa, s, kp, m in per_player if m and m >= 180]
    fpl = {'gameweeks': checked, 'fpl_assists': fpl_assists, 'fpl_goals': fpl_goals, 'before': end.isoformat(),
           'players': len(pl), 'corr_extra_with_shots90': corr([x[0] for x in pl], [x[1] for x in pl]),
           'corr_extra_with_key_passes90': corr([x[0] for x in pl], [x[2] for x in pl])}
    conn.close()
    return {'rows': rows, 'league': [[k[0], k[1], v] for k, v in league.items()], 'fpl': fpl}


def corr(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    c = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return c / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))


def taker_loglik(rows, score):
    """Sum over penalties of log P(the taker), P proportional to score x minutes over players on the pitch."""
    total, n = 0.0, 0
    for row in rows:
        ps = row['players']
        w = [score(p, row) * p['minutes'] for p in ps]
        s = sum(w)
        for p, x in zip(ps, w):
            k = p['pens_scored'] + p['pens_missed']
            if k:
                total += k * math.log(max(x / s if s > 0 else 1 / len(ps), 1e-9))
                n += k
    return total, n


def v15_score(alpha, decay):
    return lambda p, row: sum(decay ** (d / 365) * n for d, n in p['pen_hist']) + alpha * p['np_rate']


def last_taker_score(eps):
    def score(p, row):
        on = [q for q in row['players'] if q['pen_hist']]
        last = min(on, key=lambda q: min(d for d, _ in q['pen_hist']))['player'] if on else None
        return (p['player'] == last) + eps * p['np_rate']
    return score


def best(grid, f):
    return max(grid, key=f)


def pens_of(row):
    return sum(p['pens_scored'] + p['pens_missed'] for p in row['players'])


def poisson_ll(y, mu):
    mu = max(mu, 1e-9)
    return y * math.log(mu) - mu - math.lgamma(y + 1)


def fit_rate(rows, powers=POWERS):
    """(rate, power, mean lambda) by maximum likelihood over the power grid; rows with a lambda."""
    rows = [r for r in rows if r['lam']]
    mlam = sum(r['lam'] for r in rows) / len(rows)
    out = []
    for pw in powers:
        x = [(r['lam'] / mlam) ** pw for r in rows]
        rate = sum(pens_of(r) for r in rows) / sum(x)
        out.append((sum(poisson_ll(pens_of(r), rate * xi) for r, xi in zip(rows, x)), rate, pw))
    ll, rate, pw = max(out)
    return rate, pw, mlam


def rate_candidates(fit, test):
    """Test log-likelihood of penalties per team-match: (a) league rate, (b) x lambda^power, (c) team rate shrunk."""
    fit, test = [r for r in fit if r['lam']], [r for r in test if r['lam']]
    rate0 = sum(map(pens_of, fit)) / len(fit)
    rate, pw, mlam = fit_rate(fit)
    shrunk = lambda k, r: (r['team_attempts_before'] + rate0 * k) / (r['team_matches_before'] + k)
    k = best(SHRINK, lambda k: sum(poisson_ll(pens_of(r), shrunk(k, r)) for r in fit))
    ll = lambda f: sum(poisson_ll(pens_of(r), f(r)) for r in test) / len(test)
    test_ll = {'a_league': ll(lambda r: rate0), 'b_lambda': ll(lambda r: rate * (r['lam'] / mlam) ** pw),
               'c_team_shrunk': ll(lambda r: shrunk(k, r))}
    chosen = max(test_ll, key=test_ll.get)
    if chosen == 'c_team_shrunk' and k == SHRINK[-1]:
        chosen = 'a_league'       # shrunk as far as the grid goes: the league rate
    return {'n_fit': len(fit), 'n_test': len(test), 'league_rate': rate0, 'power': pw, 'power_rate': rate, 'shrink_k': k,
            'test_ll_per_match': test_ll, 'chosen': chosen}


def scorer_test(rows, pen, og, seed=7):
    """Log-likelihood per goal of who scored (players' own goals, penalties included), v1.5 vs
    v1.4, given the team's lambda and actual minutes; 95% bootstrap over team-matches."""
    per = []
    for row in rows:
        goals = sum(p['goals'] for p in row['players'])
        if not row['lam'] or not goals:
            continue
        ps, total = row['players'], row['lam'] * (1 - og)
        pen_goals = min(fm.team_penalties(row['lam'], pen) * pen['conversion'], total)
        old = fm.allocate(1.0, [p['rate'] * p['minutes'] for p in ps])
        nps = fm.allocate(1.0, [p['np_rate'] * p['minutes'] for p in ps])
        tk = fm.allocate(1.0, [v15_score(pen['alpha'], pen['decay'])(p, row) * p['minutes'] for p in ps])
        new = [((total - pen_goals) * a + pen_goals * b) / total for a, b in zip(nps, tk)]
        lo = sum(p['goals'] * math.log(max(x, 1e-9)) for p, x in zip(ps, old))
        ln = sum(p['goals'] * math.log(max(x, 1e-9)) for p, x in zip(ps, new))
        per.append((ln - lo, goals, sum(p['pens_scored'] for p in ps)))
    rng = random.Random(seed)
    diff = lambda xs: sum(d for d, _, _ in xs) / sum(g for _, g, _ in xs)
    boots = sorted(diff([rng.choice(per) for _ in per]) for _ in range(2000))
    with_pen = [x for x in per if x[2]]
    return {'team_matches': len(per), 'goals': sum(g for _, g, _ in per),
            'll_per_goal_v15_minus_v14': diff(per), 'ci95': [boots[49], boots[1949]],
            'in_matches_with_a_penalty_goal': diff(with_pen) if with_pen else None,
            'in_matches_without': diff([x for x in per if not x[2]])}


def calibration(rows, pen):
    bins = [(0, .1), (.1, .3), (.3, .6), (.6, 1.01)]
    out = []
    agg = {b: [0.0, 0, 0] for b in bins}
    for row in rows:
        att = pens_of(row)
        if not att:
            continue
        ps = row['players']
        tk = fm.allocate(1.0, [v15_score(pen['alpha'], pen['decay'])(p, row) * p['minutes'] for p in ps])
        for p, x in zip(ps, tk):
            b = next(b for b in bins if b[0] <= x < b[1])
            agg[b][0] += x * att
            agg[b][1] += p['pens_scored'] + p['pens_missed']
            agg[b][2] += 1
    for b, (pred, act, n) in agg.items():
        out.append({'share': f'{b[0]:.1f}-{min(b[1], 1):.1f}', 'player_matches': n, 'expected_attempts': round(pred, 1), 'actual_attempts': act})
    return out


def league_rates(data):
    L = {(p, k): v for p, k, v in data['league']}
    n90 = {p: L[(p, 'minutes')] / 90 for p in fm.GOAL_POINTS}
    tot = lambda k: sum(L[(p, k)] for p in fm.GOAL_POINTS)
    won_rows = [(p, r) for r in data['rows'] for p in r['players']]
    scored = sum(p['pens_scored'] for p, _ in won_rows)
    self_won = sum(min(p['pens_scored'], p['pens_won']) for p, _ in won_rows)
    return {'won_per_foul': tot('pens_won') / tot('fouls_drawn'),
            'fouls_drawn_prior': {p: L[(p, 'fouls_drawn')] / n90[p] for p in n90},
            'shots_prior': {p: L[(p, 'shots')] / n90[p] for p in n90},
            'self_won': self_won / scored, 'won_recorded_share': tot('pens_won') / (tot('pens_scored') + tot('pens_missed'))}


def fpl_extra(data):
    """FPL-only assists per non-penalty goal, GWs so far: FPL assists - API assists - penalty-won
    assists (a teammate's scored penalty that another player won), over non-penalty goals."""
    f = data['fpl']
    rows = [r for r in data['rows'] if r['kickoff'] < f['before'] and r['season'] == 2026]
    api_assists = sum(p['assists'] for r in rows for p in r['players'])
    pen_won_assists = 0
    for r in rows:
        for p in r['players']:
            others = sum(q['pens_won'] for q in r['players'] if q['player'] != p['player'])
            pen_won_assists += min(p['pens_scored'], others)
    pens = sum(p['pens_scored'] for r in rows for p in r['players'])
    goals = sum(p['goals'] for r in rows for p in r['players'])
    extra = f['fpl_assists'] - api_assists
    return {'gameweeks': f['gameweeks'], 'fpl_assists': f['fpl_assists'], 'fpl_goals': f['fpl_goals'],
            'api_assists': api_assists,
            'pen_won_assists_api': pen_won_assists, 'penalty_goals': pens, 'goals': goals,
            'extra_per_np_goal': max(extra - pen_won_assists, 0) / (goals - pens),
            'corr_extra_with_shots90': f['corr_extra_with_shots90'],
            'corr_extra_with_key_passes90': f['corr_extra_with_key_passes90'], 'players': f['players']}


def main():
    doc = json.loads(V14_PARAMS.read_text())
    params = doc['params']
    if '--refresh' in sys.argv or not INPUTS.exists():
        INPUTS.write_bytes(gzip.compress(json.dumps(extract(params), separators=(',', ':')).encode(), mtime=0))
    raw = gzip.decompress(INPUTS.read_bytes())
    data = json.loads(raw)
    rows = data['rows']
    fit = [r for r in rows if r['season'] in FIT]
    test = [r for r in rows if r['season'] in TEST]
    pen_rows = lambda rs: [r for r in rs if pens_of(r)]

    # taker model on 2024-25, against last-taker and v1.4's implied shares on the test seasons
    a, d = max(((a, d) for a in ALPHAS for d in DECAYS), key=lambda ad: taker_loglik(pen_rows(fit), v15_score(*ad))[0])
    eps = best(ALPHAS, lambda e: taker_loglik(pen_rows(fit), last_taker_score(e))[0])
    ll = lambda s: (lambda t: {'log_loss_per_penalty': -t[0] / t[1], 'penalties': t[1]})(taker_loglik(pen_rows(test), s))
    taker = {'alpha': a, 'decay': d, 'last_taker_eps': eps,
             'test': {'v1_5': ll(v15_score(a, d)), 'last_taker': ll(last_taker_score(eps)),
                      'v1_4_goal_share': ll(lambda p, r: p['rate'])}}
    rates = rate_candidates(fit, test)
    conv_fit = sum(p['pens_scored'] for r in fit for p in r['players']) / sum(map(pens_of, fit))
    rate, pw, mlam = fit_rate(fit, [0] if rates['chosen'] == 'a_league' else POWERS)
    lr = league_rates(data)
    fx = fpl_extra(data)
    pen_fit = {'rate': rate, 'lambda_power': pw, 'mean_lambda': mlam, 'conversion': conv_fit, 'alpha': a, 'decay': d}
    scorer = scorer_test(test, pen_fit, params['own_goal_share'])
    checks = {'taker_beats_last_taker': taker['test']['v1_5']['log_loss_per_penalty'] < taker['test']['last_taker']['log_loss_per_penalty'],
              'taker_beats_v1_4': taker['test']['v1_5']['log_loss_per_penalty'] < taker['test']['v1_4_goal_share']['log_loss_per_penalty'],
              'scorer_ll_better': scorer['ci95'][0] > 0}

    # frozen v1.5: everything refitted on all seasons to date
    a_f, d_f = max(((a, d) for a in ALPHAS for d in DECAYS), key=lambda ad: taker_loglik(pen_rows(rows), v15_score(*ad))[0])
    assert rates['chosen'] in ('a_league', 'b_lambda'), 'team-shrunk rates are not in fantasy.team_penalties'
    rate_f, pw_f, mlam_f = fit_rate(rows, [0] if rates['chosen'] == 'a_league' else POWERS)
    conv_f = sum(p['pens_scored'] for r in rows for p in r['players']) / sum(map(pens_of, rows))
    pen = {'rate': rate_f, 'lambda_power': pw_f, 'mean_lambda': mlam_f, 'conversion': conv_f, 'alpha': a_f, 'decay': d_f,
           'order_weight': ORDER_WEIGHT, 'order_ratio': ORDER_RATIO, 'self_won': lr['self_won'],
           'won_per_foul': lr['won_per_foul'], 'fouls_drawn_prior': lr['fouls_drawn_prior'], 'shots_prior': lr['shots_prior'],
           'extra_assists_per_goal': fx['extra_per_np_goal']}
    results = {'input_sha256': hashlib.sha256(raw).hexdigest(), 'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'team_matches': len(rows), 'penalties': sum(map(pens_of, rows)),
               'taker': taker, 'rate': rates, 'conversion_fit': conv_fit, 'scorer': scorer,
               'calibration_test': calibration(test, pen_fit), 'league': lr, 'fpl_assists': fx,
               'checks_pass': checks, 'final': pen}
    V15_PARAMS.write_text(json.dumps({
        'version_name': 'fantasy-v1.5', 'saves': True, 'params': dict(params, penalties=pen),
        'fitted_on': doc['fitted_on'], 'input_sha256': doc['input_sha256'], 'dc_input_sha256': doc['dc_input_sha256'],
        'penalty_input_sha256': results['input_sha256'],
        'notes': 'v1.4 + penalty takers, misses and FPL-only assists (experiments/fantasy_v1_5/). '
                 'Only prospective snapshots can validate it.'}, indent=1, sort_keys=True) + '\n')
    (ROOT / 'results.json').write_text(json.dumps(results, indent=1) + '\n')
    print(json.dumps({k: v for k, v in results.items() if k not in ('input_sha256', 'code_sha256')}, indent=1))


if __name__ == '__main__':
    main()
