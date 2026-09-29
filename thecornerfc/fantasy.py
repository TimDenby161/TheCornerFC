"""Fantasy v1: expected FPL points per player per fixture. Deliberately simple.

    expected minutes  P(start) and P(sub | not started) from the player's recent starts and sub
                      appearances for his team (logistic), times his own minutes as a starter /
                      sub shrunk toward his position's; P(play) and P(60+) the same way
    appearance        P(play) + P(60+)
    goals             team goals from the match model (predictions.py home_xg / away_xg), less
                      own goals, shared across the squad by attacking evidence per 90 (goals and
                      shots on target) x expected minutes; never by overall player rank
    assists           the same with assists and key passes, team total = goals x assists per goal
    clean sheet       P(60+) x e^(-lambda against), the match model's own Poisson zero
    goals conceded    GK/DEF: -P(60+) x E[floor(G / 2)], G ~ Poisson(lambda against)
    saves             GK: expected minutes / 90 x E[floor(S / 3)], S ~ Poisson(a + b x lambda against)

v1.2 adds, when its parameters are given (experiments/fantasy_v1_2/DESIGN.md):
    goalkeeper minutes  keepers' own start / sub logistics
    saves               the Poisson mean times the team's shrunk actual / expected saves
    penalty saves       GK: expected minutes / 90 x league penalty saves per team-match x 5
    cards               expected minutes / 90 x his shrunk yellow and red rates per 90
    bonus               max(0, x . beta[position]) on the components above and his base BPS
                        per 90 (bps(): an approximation of FPL's BPS from API-Football stats)
v1.3 adds defensive contributions (experiments/fantasy_dc/DESIGN.md): FPL's count in a match
~ NegBin(minutes / 90 x (c + k x his tackles + blocks + interceptions per 90), r), with c, k, r
fitted on FPL's own results; 2 points x P(count >= threshold), as a starter or a sub.

Not modelled: own goals, penalty misses, defensive contributions (and bonus, cards and penalty
saves in v1.1). Positions are API-Football's G/D/M/F. Pure functions: experiments/fantasy_v1 fits the parameters
and validates them against reconstructed points (fpl.py has no captured FPL data to use yet).
"""
from collections import Counter
from datetime import timedelta
import hashlib
import json
import math

GOAL_POINTS = {'G': 6, 'D': 6, 'M': 5, 'F': 4}
CLEAN_SHEET_POINTS = {'G': 4, 'D': 4, 'M': 1, 'F': 0}
ASSIST_POINTS = 3
SAVES_PER_POINT = 3
CONCEDED_PER_POINT = 2
PENALTY_SAVE_POINTS, YELLOW_POINTS, RED_POINTS = 5, -1, -3
HISTORY_MATCHES = 10        # team matches in the start / sub rates
WINDOW = timedelta(days=365)  # team matches, attacking evidence and roles
RECENT_MINUTES = 20         # his last starts / sub appearances for minutes as a starter / sub
PRIOR_N = 5                 # pseudo-appearances pulling those toward the position's
MISSING, DOUBTFUL = 'Missing Fixture', 'Questionable'   # API-Football injury list types
COMPONENT_POINTS = ('appearance_points', 'goal_points', 'assist_points', 'clean_sheet_points',
                    'goals_conceded_points', 'save_points')
EXTRA_POINTS = ('penalty_save_points', 'card_points', 'bonus_points', 'dc_points')      # v1.2, v1.3
# FPL's published BPS values for the actions API-Football records (no clearances, recoveries,
# big chances, crosses, errors, offsides, own goals, penalty misses or winning goals)
BPS_GOAL = {'G': 12, 'D': 12, 'M': 18, 'F': 24}
BPS_ASSIST, BPS_CLEAN_SHEET, BPS_SAVE, BPS_PENALTY_SAVE = 9, 12, 2, 15
BPS_YELLOW, BPS_RED, BPS_PENALTY_CONCEDED = -3, -9, -3
BONUS = (3, 2, 1)
BPS_PASS_MIN = 30
# Role group of a starting role (positions.py); substitutes-only players fall back on position
ROLE_GROUPS = {'GK': 'GK', 'CB': 'CB', 'LB': 'FB', 'RB': 'FB', 'LWB': 'FB', 'RWB': 'FB', 'DM': 'DM',
               'CM': 'CM', 'AM': 'AM', 'LM': 'W', 'RM': 'W', 'LW': 'W', 'RW': 'W', 'ST': 'ST'}
POSITION_GROUPS = {'G': 'GK', 'D': 'CB', 'M': 'CM', 'F': 'ST'}


# ---- Scoring (the target) ----

def actual_points(position, minutes, goals=0, assists=0, team_conceded=0, saves=0,
                  penalties_saved=0, yellow=0, red=0):
    """Reconstructed FPL points by part from one stat line. Clean sheets and goals conceded use
    the whole match (FPL counts only time on the pitch). 'v1' is what fantasy v1 models;
    'total' adds penalty saves and cards. Bonus, own goals and penalty misses are unknown."""
    played, full = minutes > 0, minutes >= 60
    parts = {'appearance_points': played + full,
             'goal_points': GOAL_POINTS[position] * (goals or 0),
             'assist_points': ASSIST_POINTS * (assists or 0),
             'clean_sheet_points': CLEAN_SHEET_POINTS[position] if full and team_conceded == 0 else 0,
             'goals_conceded_points': -(team_conceded // CONCEDED_PER_POINT)
             if full and position in 'GD' else 0,
             'save_points': (saves or 0) // SAVES_PER_POINT if position == 'G' else 0}
    parts['v1'] = sum(parts.values())
    parts['total'] = parts['v1'] + (PENALTY_SAVE_POINTS * (penalties_saved or 0)
                                    + YELLOW_POINTS * (yellow or 0) + RED_POINTS * (red or 0))
    return parts


def bps(position, minutes, goals=0, assists=0, team_conceded=0, saves=0, penalties_saved=0, yellow=0, red=0,
        key_passes=0, tackles=0, blocks=0, interceptions=0, dribbles_won=0, passes=0, passes_accurate=0,
        shots=0, shots_on=0, fouls=0, penalties_committed=0):
    """Approximate FPL BPS: {'bps': total, 'base': the part from general play (not minutes, goals,
    assists, clean sheets, saves or cards), which v1.2 uses as the player's bonus tendency}."""
    if minutes <= 0:
        return {'bps': 0, 'base': 0}
    passes, accurate = passes or 0, passes_accurate or 0
    share = accurate / passes if passes >= BPS_PASS_MIN else 0
    base = ((key_passes or 0) + 2 * (tackles or 0) + ((blocks or 0) + (interceptions or 0)) // 2
            + (dribbles_won or 0) + (6 if share >= .9 else 4 if share >= .8 else 2 if share >= .7 else 0)
            - max((shots or 0) - (shots_on or 0), 0) - (fouls or 0) + BPS_PENALTY_CONCEDED * (penalties_committed or 0))
    events = ((6 if minutes >= 60 else 3) + BPS_GOAL[position] * (goals or 0) + BPS_ASSIST * (assists or 0)
              + (BPS_CLEAN_SHEET if position in 'GD' and minutes >= 60 and team_conceded == 0 else 0)
              + (BPS_SAVE * (saves or 0) if position == 'G' else 0) + BPS_PENALTY_SAVE * (penalties_saved or 0)
              + BPS_YELLOW * (yellow or 0) + BPS_RED * (red or 0))
    return {'bps': events + base, 'base': base}


def match_bonus(scores):
    """{player: bps} for everyone who played in a match -> {player: bonus} under FPL's tie rule:
    competition ranking, so two tied first get 3 each and the next player 1."""
    values = sorted(scores.values(), reverse=True)
    out = {}
    for pid, v in scores.items():
        rank = sum(x > v for x in values)
        out[pid] = BONUS[rank] if rank < len(BONUS) else 0
    return out


# ---- Probability helpers ----

def logistic(x):
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def floor_div_mean(lam, k, tol=1e-12):
    """E[floor(X / k)] for X ~ Poisson(lam)."""
    lam = max(lam, 0.0)
    p = math.exp(-lam)
    total = mean = 0.0
    x = 0
    while total < 1 - tol and x < 200:
        total += p
        mean += (x // k) * p
        x += 1
        p *= lam / x
    return mean


def shrunk(total, n, prior, k):
    """Mean of n values summing to total, pulled toward prior by k pseudo-values."""
    return (total + prior * k) / (n + k)


# ---- Expected minutes ----

def minutes_features(history, gap, decay):
    """(start features, sub features) for the logistics. history: [(started, sub_appearance)]
    over the team's last league matches, most recent first (at most HISTORY_MATCHES);
    gap: team matches since his last appearance (0 = played the last one)."""
    history = history[:HISTORY_MATCHES]
    w = [decay ** j for j in range(len(history))]
    norm = sum(w) or 1.0
    start_rate = sum(wj * s for wj, (s, _) in zip(w, history)) / norm
    sub_rate = sum(wj * b for wj, (_, b) in zip(w, history)) / norm
    last = history[0] if history else (0, 0)
    before = history[1] if len(history) > 1 else (0, 0)
    g = math.log1p(gap)
    return [1.0, start_rate, float(last[0]), float(before[0]), g], [1.0, sub_rate, start_rate, float(last[1]), g]


def minutes_expectation(p_start, p_sub, start_minutes, start_p60, sub_minutes, sub_p60):
    """P(start), P(play), P(60+) and expected minutes. p_sub is P(sub appearance | not started)."""
    p_bench_on = (1 - p_start) * p_sub
    return {'p_start': p_start, 'p_play': p_start + p_bench_on,
            'p60': p_start * start_p60 + p_bench_on * sub_p60,
            'exp_minutes': p_start * start_minutes + p_bench_on * sub_minutes}


def start_probability(features, coefficients):
    return logistic(sum(f * c for f, c in zip(features, coefficients)))


# ---- Attacking shares ----

def attacking_rate(player_evidence, exposure, prior_rate, pseudo_exposure):
    """Player's share of his team's attacking evidence per 90 on the pitch, shrunk to his role
    group's. exposure: sum over his appearances of team evidence in that match x minutes / 90."""
    return (player_evidence + prior_rate * pseudo_exposure) / (exposure + pseudo_exposure)


def allocate(team_total, weights):
    """Split a team expectation in proportion to weights (rate x expected minutes)."""
    total = sum(weights)
    return [team_total * w / total if total > 0 else 0.0 for w in weights]


# ---- Expected points ----

def expected_points(position, minutes, exp_goals, exp_assists, lam_against, save_mean=None, extras=None):
    """Every v1 component for one player-fixture. minutes: minutes_expectation(); save_mean:
    the team's expected saves, or None when saves are not modelled; extras: v1.2's
    player_extras(), or None for v1 / v1.1."""
    p60 = minutes['p60']
    team_cs = math.exp(-lam_against)
    defends = position in 'GD'
    comps = dict(minutes, exp_goals=exp_goals, exp_assists=exp_assists, lambda_against=lam_against,
                 team_p_clean_sheet=team_cs, p_clean_sheet=p60 * team_cs,
                 appearance_points=minutes['p_play'] + p60,
                 goal_points=GOAL_POINTS[position] * exp_goals,
                 assist_points=ASSIST_POINTS * exp_assists,
                 clean_sheet_points=CLEAN_SHEET_POINTS[position] * p60 * team_cs,
                 goals_conceded_points=-p60 * floor_div_mean(lam_against, CONCEDED_PER_POINT) if defends else 0.0,
                 save_points=(minutes['exp_minutes'] / 90 * floor_div_mean(save_mean, SAVES_PER_POINT)
                              if position == 'G' and save_mean is not None else 0.0))
    comps['expected_points'] = sum(comps[k] for k in COMPONENT_POINTS)
    if extras is not None:
        per90 = minutes['exp_minutes'] / 90
        comps.update(save_mean=save_mean, yellow90=extras['yellow90'], red90=extras['red90'],
                     base_bps90=extras['base_bps90'],
                     penalty_save_points=PENALTY_SAVE_POINTS * per90 * extras['penalty_saves'] if position == 'G' else 0.0,
                     card_points=per90 * (YELLOW_POINTS * extras['yellow90'] + RED_POINTS * extras['red90']))
        x = bonus_features(position, comps)
        comps['bonus_points'] = max(0.0, sum(f * b for f, b in zip(x, extras['bonus_beta'][position])))
        comps.update(start_minutes=extras['start_minutes'], sub_minutes=extras['sub_minutes'], dc_points=0.0)
        if 'dc' in extras:
            comps['cbit90'] = extras['cbit90']
            dc = extras['dc']
            comps['dc_points'] = dc['points'] * dc_probability(position, comps, dc) if position in dc['thresholds'] else 0.0
        comps['expected_points'] += sum(comps[k] for k in EXTRA_POINTS)
    return comps


def nb_tail(threshold, mean, r):
    """P(X >= threshold) for X ~ NegBin with the given mean and dispersion r."""
    if mean <= 0:
        return 0.0
    q = r / (r + mean)
    log_p = r * math.log(q)                  # P(X = 0)
    below = 0.0
    for x in range(threshold):
        below += math.exp(log_p)
        log_p += math.log((x + r) / (x + 1) * (1 - q))
    return max(0.0, 1 - below)


def dc_probability(position, comps, dc):
    """P(he reaches FPL's defensive-contribution threshold): as a starter over his minutes as a
    starter, or as a sub over his minutes as a sub. comps: expected_points() output with v1.3's
    start_minutes, sub_minutes and cbit90."""
    q, t = dc[position], dc['thresholds'][position]
    per90 = q['c'] + q['k'] * comps['cbit90']
    return (comps['p_start'] * nb_tail(t, comps['start_minutes'] / 90 * per90, q['r'])
            + (comps['p_play'] - comps['p_start']) * nb_tail(t, comps['sub_minutes'] / 90 * per90, q['r']))


def bonus_features(position, comps):
    """v1.2's bonus regressors for one player-fixture, from his other components."""
    return [comps['p_play'], comps['p60'], comps['exp_goals'], comps['exp_assists'],
            comps['p_clean_sheet'] if position in 'GD' else 0.0,
            comps['save_points'] if position == 'G' else 0.0,
            comps['base_bps90'] * comps['exp_minutes'] / 90]


def player_extras(params, r=None, stored=None):
    """expected_points' extras for v1.2 params (None for v1 / v1.1): from player_features() r,
    or from a stored prediction's own rates (to rescore it with another position)."""
    if 'bonus_beta' not in params:
        return None
    dc = params.get('dc')
    if stored is not None:
        rates = {k: stored[k] for k in ('yellow90', 'red90', 'base_bps90', 'start_minutes', 'sub_minutes')}
        if dc:
            rates['cbit90'] = stored['cbit90']
    else:
        pseudo, prior = params['rate_pseudo_minutes'] / 90, params['rate_priors'][r['position']]
        n90 = r['att_min'] / 90
        rates = {k: (r[src] + prior[k] * pseudo) / (n90 + pseudo)
                 for k, src in (('yellow90', 'yellow'), ('red90', 'red'), ('base_bps90', 'bps_base'))}
        if dc:        # goalkeepers borrow the defenders' prior; they can't score DC anyway
            p = dc['cbit_priors'].get(r['position'], dc['cbit_priors']['D'])
            rates['cbit90'] = (r['cbit'] + p * pseudo) / (n90 + pseudo)
    return dict(rates, penalty_saves=params['penalty_saves_per_team_match'], bonus_beta=params['bonus_beta'],
                **({'dc': dc} if dc else {}))


def save_multiplier(team_saves, a, b, pseudo):
    """Team's actual / expected saves over its recent matches, shrunk toward 1 by pseudo
    matches. team_saves: [(saves, lambda against)] (lambda None where unknown: skipped)."""
    known = [(s, max(a + b * lam, 0.1)) for s, lam in team_saves if lam is not None]
    if not known:
        return 1.0
    expected = sum(e for _, e in known)
    typical = expected / len(known)
    return (sum(s for s, _ in known) + pseudo * typical) / (expected + pseudo * typical)


# ---- Inputs as known before kickoff (shared by the backtest and the live capture) ----

def universe(team, team_recent, latest_club):
    """Candidates for a team-fixture: players with minutes for the team in team_recent (its league
    matches within WINDOW before kickoff) whose latest appearance anywhere was for this team.
    team_recent: [{player: (started, minutes)}]; latest_club: player -> club of his last appearance."""
    seen = {p for match in team_recent for p, (_, minutes) in match.items() if minutes > 0}
    return sorted(p for p in seen if latest_club.get(p) == team)


def player_features(player, kickoff, team_recent, appearances):
    """Everything v1 needs about one player before kickoff.

    team_recent: his team's league matches within WINDOW, oldest first, as {player: (started,
    minutes)}. appearances: his earlier league appearances with minutes, any club, oldest first:
    (kickoff, started, minutes, role, goals, shots_on, assists, key_passes, and his team's goals,
    shots_on, assists, key_passes in that match), optionally followed by v1.2's (base BPS,
    yellow cards, red cards) and v1.3's tackles + blocks + interceptions."""
    history, gap = [], None
    for j, match in enumerate(reversed(team_recent)):
        line = match.get(player)
        on = line is not None and line[1] > 0
        if gap is None and on:
            gap = j
        if j < HISTORY_MATCHES:
            history.append((int(bool(on and line[0])), int(bool(on and not line[0]))))
    starts = [a[2] for a in appearances if a[1]][-RECENT_MINUTES:]
    subs = [a[2] for a in appearances if not a[1]][-RECENT_MINUTES:]
    recent = [a for a in appearances if a[0] >= kickoff - WINDOW]
    roles = Counter(ROLE_GROUPS[a[3]] for a in recent if a[1] and a[3] in ROLE_GROUPS)
    per90 = lambda i: sum(a[i] * a[2] / 90 for a in recent)
    return dict(history=history, gap=gap if gap is not None else len(team_recent),
                start_n=len(starts), start_min=sum(starts), start_60=sum(m >= 60 for m in starts),
                sub_n=len(subs), sub_min=sum(subs), sub_60=sum(m >= 60 for m in subs),
                att_min=sum(a[2] for a in recent), g=sum(a[4] for a in recent), sot=sum(a[5] for a in recent),
                a=sum(a[6] for a in recent), kp=sum(a[7] for a in recent),
                tg=per90(8), tsot=per90(9), ta=per90(10), tkp=per90(11),
                bps_base=sum(a[12] for a in recent if len(a) > 12), yellow=sum(a[13] for a in recent if len(a) > 12),
                red=sum(a[14] for a in recent if len(a) > 12), cbit=sum(a[15] for a in recent if len(a) > 15),
                group=roles.most_common(1)[0][0] if roles else None)


def injury_type(evidence):
    """MISSING, DOUBTFUL or None from availability.merge evidence (API lists and manual absences;
    a manual absence counts as missing)."""
    types = {str(e.get('type') or '') for e in evidence or []}
    return MISSING if MISSING in types else DOUBTFUL if DOUBTFUL in types else None


def predict_team(players, lam_for, lam_against, params, saves=True, save_factor=1.0):
    """Components for one team-fixture. players: player_features() dicts with 'position' (G/D/M/F)
    and 'injury' (injury_type); params: a fitted parameter set (thecornerfc/fantasy_params.json,
    or fantasy_params_v1_2.json); save_factor: v1.2's save_multiplier() for the team."""
    pr, c_g, c_a = params['position_priors'], params['goals_per_shot_on'], params['assists_per_key_pass']
    pseudo = params['K'] / 90
    minutes, weights = [], []
    for r in players:
        s, b = minutes_features(r['history'], r['gap'], params['decay'])
        if params['availability']:
            extra = [float(r['injury'] == MISSING), float(r['injury'] == DOUBTFUL)]
            s, b = s + extra, b + extra
        p = pr[r['position']]
        gk = r['position'] == 'G' and 'gk_start_beta' in params
        mins_start = shrunk(r['start_min'], r['start_n'], p['start_min'], PRIOR_N)
        mins_sub = shrunk(r['sub_min'], r['sub_n'], p['sub_min'], PRIOR_N)
        mins = minutes_expectation(
            start_probability(s, params['gk_start_beta' if gk else 'start_beta']),
            start_probability(b, params['gk_sub_beta' if gk else 'sub_beta']),
            mins_start, shrunk(r['start_60'], r['start_n'], p['start_p60'], PRIOR_N), mins_sub, params['sub_p60'])
        g0, a0 = params['role_priors'][r['group'] or POSITION_GROUPS[r['position']]]
        rate_g = attacking_rate(.5 * r['g'] + .5 * c_g * r['sot'], .5 * r['tg'] + .5 * c_g * r['tsot'],
                                g0, pseudo * params['team_goal_evidence'])
        rate_a = attacking_rate(.5 * r['a'] + .5 * c_a * r['kp'], .5 * r['ta'] + .5 * c_a * r['tkp'],
                                a0, pseudo * params['team_assist_evidence'])
        minutes.append(dict(mins, start_minutes=mins_start, sub_minutes=mins_sub))
        weights.append((rate_g * mins['exp_minutes'], rate_a * mins['exp_minutes']))
    eg = allocate(lam_for * (1 - params['own_goal_share']), [w[0] for w in weights])
    ea = allocate(lam_for * params['assists_per_goal'], [w[1] for w in weights])
    save_mean = max(params['save_intercept'] + params['save_slope'] * lam_against, 0.1) * save_factor if saves else None
    out = []
    for r, m, g, a in zip(players, minutes, eg, ea):
        extras = player_extras(params, r)
        if extras is not None:
            extras.update(start_minutes=m['start_minutes'], sub_minutes=m['sub_minutes'])
        m = {k: m[k] for k in ('p_start', 'p_play', 'p60', 'exp_minutes')}
        out.append(expected_points(r['position'], m, g, a, lam_against, save_mean, extras))
    return out


# ---- Snapshots ----

def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def snapshot_record(*, season, round_name, version_id, source, captured_at, rows, inputs):
    """One immutable, content-hashed record of every component for a round, keyed by
    API-Football ids (the backtest archive, which has no FPL ids). rows: [{'player_id',
    'fixture_id', 'team_id', 'position', components...}]."""
    rows = sorted(rows, key=lambda r: (r['fixture_id'], r['player_id']))
    identity = {'season': season, 'round': round_name, 'model_version_id': version_id,
                'source': source, 'rows': rows, 'inputs': inputs}
    return dict(identity, captured_at=captured_at, content_hash=_digest(identity))


def fpl_predictions(rows, api_to_fpl):
    """Rows as fpl.make_prediction_snapshot predictions (fantasy_prediction_snapshots), for
    players with an FPL id. Needs FPL capture for the id mapping, so nothing calls it yet.
    A double gameweek's fixtures are summed per player."""
    out = {}
    for r in rows:
        fpl_id = api_to_fpl.get(r['player_id'])
        if fpl_id is None:
            continue
        p = out.setdefault(fpl_id, {'fpl_player_id': fpl_id, 'api_player_id': r['player_id'], 'fixtures': 0})
        p['fixtures'] += 1
        for key, value in r.items():
            if key in ('exp_minutes', 'exp_goals', 'exp_assists', 'expected_points', *COMPONENT_POINTS, *EXTRA_POINTS):
                p[key] = p.get(key, 0.0) + value
            elif key in ('p_start', 'p_play', 'p60', 'p_clean_sheet') and p['fixtures'] == 1:
                p[key] = value      # a probability is kept for the first fixture only
    return sorted(out.values(), key=lambda p: p['fpl_player_id'])
