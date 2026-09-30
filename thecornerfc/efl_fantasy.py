"""EFL fantasy v1: expected Fantasy EFL points per player per fixture, and per club pick, for the
Championship, League One and League Two. Nothing is read from the Fantasy EFL site.

The football is fantasy.py's (v1.6 parameters, fitted on the Premier League), run on these leagues'
own history by fantasy_snapshots.build without FPL's inputs: expected minutes, goals (with
penalties and misses), assists, clean sheets, goals conceded, saves, penalty saves and cards.
Fantasy EFL's extra actions come from each player's own rates per 90 in these leagues over the
last year, shrunk toward his role group's, as a Poisson count over his minutes as a starter or sub:

    defenders    +1 per 2 tackles, per 2 blocks and per 4 clearances (API-Football has no
                 clearances: a fixed rate per role group, CLEARANCES_PER_90)
    midfielders  +2 per interception
    mid / fwd    +1 per 2 key passes, +1 per shot on target
    everyone     +5 for a hat-trick (Poisson on his goals when he plays)

Clubs: +5 win, +3 draw, +2 more for an away win, +2 clean sheet, +2 for 2+ goals and +2 more for
4+, from the match model's win / draw chances and Poisson goals.

Not modelled: own goals (-3). Positions are API-Football's G/D/M/F from match data, corrected by
efl_positions.json ({"player id": "D"}), since Fantasy EFL's own listing isn't read.
Gameweeks run Thursday to Wednesday (UK time), numbered from the week of the season's first match.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import logging
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from . import fantasy as fm, fantasy_snapshots as fs

log = logging.getLogger(__name__)

EFL = (40, 41, 42)                  # Championship, League One, League Two
LEAGUE_NAMES = {40: 'Championship', 41: 'League One', 42: 'League Two'}
GAMEWEEKS = 6                       # gameweeks ahead on the page
UK = ZoneInfo('Europe/London')
THURSDAY = 3
POSITIONS_PATH = Path(__file__).with_name('efl_positions.json')

# ---- Fantasy EFL scoring (2025/26 and 2026/27) ----
GOAL_POINTS = {'G': 10, 'D': 7, 'M': 6, 'F': 5}
CLEAN_SHEET_POINTS = {'G': 5, 'D': 5, 'M': 0, 'F': 0}
ASSIST_POINTS, HAT_TRICK_POINTS, PENALTY_MISS_POINTS = 3, 5, -3
YELLOW_POINTS, RED_POINTS, PENALTY_SAVE_POINTS = -1, -3, 5
SAVES_PER, SAVE_POINTS = 3, 2              # +2 per 3 saves
CONCEDED_PER = 2                           # GK / DEF: -1 per 2 conceded
TACKLES_PER, BLOCKS_PER, CLEARANCES_PER = 2, 2, 4     # DEF: +1 each
INTERCEPTION_POINTS = 2                    # MID: each
KEY_PASSES_PER = 2                         # MID / FWD: +1
SHOT_ON_TARGET_POINTS = 1                  # MID / FWD: each
CLUB_WIN, CLUB_DRAW, CLUB_AWAY_WIN, CLUB_CLEAN_SHEET, CLUB_2_GOALS, CLUB_4_GOALS = 5, 3, 2, 2, 2, 2

PARTS = ('appearance', 'goal', 'hat_trick', 'assist', 'penalty_miss', 'clean_sheet', 'goals_conceded',
         'save', 'penalty_save', 'card', 'tackle', 'block', 'clearance', 'interception', 'key_pass', 'shot_on_target')
CLUB_PARTS = ('win', 'draw', 'away_win', 'clean_sheet', 'goals_2', 'goals_4')
ACTIONS = ('tackles', 'blocks', 'interceptions', 'key_passes', 'shots_on')
PSEUDO_MINUTES = 450                       # his rates are pulled toward his role group's by five 90s
# Clearances per 90 by role group: not in API-Football, so a typical EFL rate (an assumption)
CLEARANCES_PER_90 = {'CB': 5.0, 'FB': 2.2, 'DM': 1.5, 'CM': 1.0, 'AM': 0.5, 'W': 0.5, 'ST': 0.7, 'GK': 0.0}


# ---- Probability helpers ----

def poisson_tail(lam, k):
    """P(X >= k), X ~ Poisson(lam)."""
    lam = max(lam, 0.0)
    return max(0.0, 1 - sum(math.exp(-lam) * lam ** x / math.factorial(x) for x in range(k)))


def per_count(comps, rate90, k):
    """E[floor(X / k)] where X ~ Poisson(rate90 x his minutes / 90), as a starter or as a sub."""
    sub = comps['p_play'] - comps['p_start']
    return (comps['p_start'] * fm.floor_div_mean(rate90 * comps['start_minutes'] / 90, k)
            + sub * fm.floor_div_mean(rate90 * comps['sub_minutes'] / 90, k))


# ---- Points ----

def player_points(position, comps, rates):
    """{part: expected points} for one player-fixture. comps: a fantasy_snapshots.build prediction
    (fantasy.expected_points with v1.2+ extras); rates: his action rates per 90 (action_rates)."""
    per90 = comps['exp_minutes'] / 90
    p60, p_play = comps['p60'], comps['p_play']
    goals = comps['exp_goals']
    per_match = goals / p_play if p_play > 0 else 0.0
    lam = comps['lambda_against']
    defends, attacks = position in 'GD', position in 'MF'
    return {
        'appearance': p_play + p60,
        'goal': GOAL_POINTS[position] * goals,
        'hat_trick': HAT_TRICK_POINTS * p_play * poisson_tail(per_match, 3),
        'assist': ASSIST_POINTS * comps['exp_assists'],
        'penalty_miss': PENALTY_MISS_POINTS * comps.get('exp_pen_misses', 0.0),
        'clean_sheet': CLEAN_SHEET_POINTS[position] * p60 * math.exp(-lam),
        'goals_conceded': -p60 * fm.floor_div_mean(lam, CONCEDED_PER) if defends else 0.0,
        'save': SAVE_POINTS * per90 * fm.floor_div_mean(comps['save_mean'], SAVES_PER) if position == 'G' else 0.0,
        'penalty_save': comps['penalty_save_points'] / fm.PENALTY_SAVE_POINTS * PENALTY_SAVE_POINTS if position == 'G' else 0.0,
        'card': per90 * (YELLOW_POINTS * comps['yellow90'] + RED_POINTS * comps['red90']),
        'tackle': per_count(comps, rates['tackles'], TACKLES_PER) if position == 'D' else 0.0,
        'block': per_count(comps, rates['blocks'], BLOCKS_PER) if position == 'D' else 0.0,
        'clearance': per_count(comps, rates['clearances'], CLEARANCES_PER) if position == 'D' else 0.0,
        'interception': INTERCEPTION_POINTS * per90 * rates['interceptions'] if position == 'M' else 0.0,
        'key_pass': per_count(comps, rates['key_passes'], KEY_PASSES_PER) if attacks else 0.0,
        'shot_on_target': SHOT_ON_TARGET_POINTS * per90 * rates['shots_on'] if attacks else 0.0,
    }


def club_points(lam_for, lam_against, p_win, p_draw, is_home):
    """{part: expected points} for a club pick in one fixture."""
    return {'win': CLUB_WIN * p_win, 'draw': CLUB_DRAW * p_draw,
            'away_win': 0.0 if is_home else CLUB_AWAY_WIN * p_win,
            'clean_sheet': CLUB_CLEAN_SHEET * math.exp(-lam_against),
            'goals_2': CLUB_2_GOALS * poisson_tail(lam_for, 2), 'goals_4': CLUB_4_GOALS * poisson_tail(lam_for, 4)}


# ---- Inputs ----

def action_rates(lines, now):
    """{player: {action: per 90}} over his league lines in the year before now, each shrunk toward
    his role group's (the group he started most in; else his position's), with the group's
    clearance rate. lines: fantasy_snapshots.league_lines rows."""
    since = now - fm.WINDOW
    totals = defaultdict(lambda: defaultdict(float))
    starts, labels = defaultdict(Counter), defaultdict(Counter)
    for row in lines:
        (_, kickoff, _, _, _, _, _, pid, minutes, started, position, role, _, _, shots_on, key_passes,
         *_rest) = row
        if kickoff < since or not minutes:
            continue
        tackles, blocks, interceptions = row[20:23]
        t = totals[pid]
        t['minutes'] += minutes
        for k, v in zip(ACTIONS, (tackles, blocks, interceptions, key_passes, shots_on)):
            t[k] += v or 0
        if started and role in fm.ROLE_GROUPS:
            starts[pid][fm.ROLE_GROUPS[role]] += minutes
        if position in fm.POSITION_GROUPS:
            labels[pid][position] += 1
    group = {pid: starts[pid].most_common(1)[0][0] if starts[pid]
             else fm.POSITION_GROUPS[labels[pid].most_common(1)[0][0]] if labels[pid] else 'CM' for pid in totals}
    prior_sum = defaultdict(lambda: defaultdict(float))
    for pid, t in totals.items():
        g = group.get(pid, 'CM')
        for k in ('minutes', *ACTIONS):
            prior_sum[g][k] += t[k]
    priors = {g: {k: 90 * s[k] / s['minutes'] if s['minutes'] else 0.0 for k in ACTIONS} for g, s in prior_sum.items()}
    out = {}
    for pid, t in totals.items():
        g = group.get(pid, 'CM')
        p = priors.get(g, {k: 0.0 for k in ACTIONS})
        out[pid] = {k: (t[k] + p[k] * PSEUDO_MINUTES / 90) / ((t['minutes'] + PSEUDO_MINUTES) / 90) for k in ACTIONS}
        out[pid].update(clearances=CLEARANCES_PER_90.get(g, 1.0), group=g)
    return out, priors


def position_overrides(path=POSITIONS_PATH):
    """{player id: 'G' / 'D' / 'M' / 'F'} from efl_positions.json (keys starting with '_' are notes)."""
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    return {int(k): v.upper() for k, v in doc.items()
            if not k.startswith('_') and isinstance(v, str) and v.upper() in fm.GOAL_POINTS}


def gameweek_start(kickoff):
    """The Thursday (UK date) that starts kickoff's Fantasy EFL gameweek."""
    d = kickoff.astimezone(UK).date()
    return d - timedelta(days=(d.weekday() - THURSDAY) % 7)


# ---- Export ----

def _r(x, n=2):
    x = round(x, n)
    return x if x else 0


def payload(conn, now=None, doc=None, gameweeks=GAMEWEEKS):
    """efl_predictions.json: expected points for every player and club in the next gameweeks, or
    None when no fixtures are coming up. SELECT only."""
    from .predictions import UPCOMING_STATUSES
    now = now or datetime.now(timezone.utc)
    upcoming = conn.execute(
        """select f.fixture_id, f.league_id, f.season, f.home_team_id, f.away_team_id, f.kickoff,
                  p.home_xg::float8, p.away_xg::float8, p.p_home::float8, p.p_draw::float8, p.p_away::float8
           from fixtures f join fixture_predictions p using (fixture_id)
           where f.league_id = any(%s) and f.status_short = any(%s) and f.kickoff > %s
             and p.home_xg is not null and p.away_xg is not null order by f.kickoff""",
        [list(EFL), list(UPCOMING_STATUSES), now]).fetchall()
    if not upcoming:
        return None
    season = upcoming[0][2]
    first = conn.execute("""select min(kickoff) from fixtures where league_id = any(%s) and season = %s""",
                         [list(EFL), season]).fetchone()[0]
    week0 = gameweek_start(first)
    gw_of = {f[0]: (gameweek_start(f[5]) - week0).days // 7 + 1 for f in upcoming}
    keep = sorted(set(gw_of.values()))[:gameweeks]
    upcoming = [f for f in upcoming if gw_of[f[0]] in keep]
    fixtures = {f[0]: f for f in upcoming}
    horizon = max(f[5] for f in upcoming) - now + timedelta(days=1)

    lines = fs.league_lines(conn, 'efl_fantasy_lines', '= any(%s)', list(EFL), season - 2)
    doc = doc or fs.load_params(Path(__file__).with_name('fantasy_params_v1_6.json'))
    doc, teams_out = fs.build(conn, list(fixtures), now=now, doc=doc, horizon=horizon,
                              history=fs.History(lines), leagues=EFL, fpl=False)
    rates, priors = action_rates(lines, now)
    fallback = {**priors.get('CM', {k: 0.0 for k in ACTIONS}), 'clearances': 1.0, 'group': 'CM'}
    overrides = position_overrides()

    players, cells = {}, defaultdict(list)
    for fid, team, _, preds, inputs in teams_out:
        _, league, _, home, away, *_ = fixtures[fid]
        for p in preds:
            pid = p['player_id']
            position = overrides.get(pid, p['position'])
            parts = player_points(position, p, rates.get(pid, fallback))
            if pid not in players:
                players[pid] = [pid, None, team, position, int(pid in overrides), inputs['availability'].get(str(pid))]
            cells[pid].append([gw_of[fid], away if team == home else home, team == home, _r(sum(parts.values())),
                               round(p['exp_minutes']), _r(p['p_start']), _r(p['exp_goals']), _r(p['exp_assists']),
                               _r(p['p_clean_sheet']), [_r(parts[k]) for k in PARTS]])
    # players with no real chance of playing in any gameweek shown are left out
    players = {pid: v for pid, v in players.items() if max(c[4] for c in cells[pid]) >= 5}
    names = dict(conn.execute("select player_id, name from players where player_id = any(%s)", [list(players)]).fetchall())
    for pid, v in players.items():
        v[1] = names.get(pid, str(pid))
    order = sorted(players, key=lambda pid: -sum(c[3] for c in cells[pid]))

    clubs = defaultdict(list)
    for fid, league, _, home, away, _, hx, ax, ph, pd, pa in upcoming:
        for team, is_home in ((home, True), (away, False)):
            lam_for, lam_against = (hx, ax) if is_home else (ax, hx)
            parts = club_points(lam_for, lam_against, ph if is_home else pa, pd, is_home)
            clubs[team].append([gw_of[fid], away if is_home else home, is_home, _r(sum(parts.values())),
                                _r(ph if is_home else pa), _r(math.exp(-lam_against)), [_r(parts[k]) for k in CLUB_PARTS]])
    team_league = {}
    for _, league, _, home, away, *_ in upcoming:
        team_league[home] = team_league[away] = league
    team_info = {t: [n, c, team_league[t]] for t, n, c in conn.execute(
        "select team_id, name, code from teams where team_id = any(%s)", [list(team_league)])}
    first_kick = {g: min(f[5] for f in upcoming if gw_of[f[0]] == g) for g in keep}
    return {'generated_at': now.isoformat(), 'model': 'EFL fantasy v1',
            'gameweeks': [{'id': g, 'start': (week0 + timedelta(weeks=g - 1)).isoformat(),
                           'end': (week0 + timedelta(weeks=g - 1, days=6)).isoformat(),
                           'first_kickoff': first_kick[g].isoformat()} for g in keep],
            'leagues': {str(k): v for k, v in LEAGUE_NAMES.items()},
            'teams': {str(t): v for t, v in team_info.items()},
            'fields': ['player', 'name', 'team', 'position', 'corrected', 'availability'],
            'cell_fields': ['gw', 'opponent', 'home', 'xp', 'minutes', 'p_start', 'goals', 'assists', 'p_clean_sheet', 'parts'],
            'part_fields': list(PARTS),
            'players': [players[pid] for pid in order], 'cells': [sorted(cells[pid]) for pid in order],
            'club_fields': ['gw', 'opponent', 'home', 'xp', 'p_win', 'p_clean_sheet', 'parts'],
            'club_part_fields': list(CLUB_PARTS),
            'clubs': {str(t): sorted(v) for t, v in clubs.items()}}
