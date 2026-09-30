"""Fantasy Premier League evidence: pre-deadline source state, ID mapping, actual points and
fantasy prediction snapshots. Evidence only: no fantasy model exists yet and nothing here
changes another model.

FPL's JSON endpoints are undocumented browser endpoints with no published licence; access is
off unless FPL_CAPTURE_ENABLED (config.require_fpl_access). Only the fields a fantasy model or
its validation needs are stored, not whole responses. Parsing is separate from IO so a licensed
feed can replace FplClient without changing the evidence tables.
"""
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import time
import unicodedata

import requests

from . import config
from .model_versions import snapshot_times

log = logging.getLogger(__name__)

BASE_URL = 'https://fantasy.premierleague.com/api'
PL_LEAGUE = 39
OVERRIDES_PATH = Path(__file__).with_name('fpl_overrides.json')
# FPL short club names that differ from API-Football's after normalising
TEAM_ALIASES = {'man city': 'manchester city', 'man utd': 'manchester united', 'spurs': 'tottenham',
                'nottm forest': 'nottingham forest'}


class FplClient:
    """Polite, retrying reader of FPL's public JSON. Not an API-Football client: no quota ledger."""

    def __init__(self, min_interval=1.0):
        config.require_fpl_access('FPL request')
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'TheCornerFC evidence capture (+https://thecornerfc.com)'
        self.min_interval = min_interval
        self.calls_made = 0
        self._last_call = 0.0

    def get(self, path, retries=4):
        for attempt in range(1, retries + 1):
            config.require_fpl_access('FPL request')
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            self.calls_made += 1
            try:
                resp = self.session.get(f'{BASE_URL}/{path.lstrip("/")}', timeout=30)
            except requests.RequestException as exc:
                log.warning('FPL request error on %s (attempt %d): %s', path, attempt, type(exc).__name__)
                time.sleep(2 ** attempt)
                continue
            # 503 while FPL updates a gameweek: back off rather than store a partial state
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning('FPL HTTP %s on %s, backing off', resp.status_code, path)
                time.sleep(max(2 ** attempt, 10))
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f'Giving up on FPL {path} after {retries} attempts')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def parse_time(raw):
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace('Z', '+00:00')).astimezone(timezone.utc)


def _iso(raw):
    value = parse_time(raw)
    return value.isoformat() if value else None


# ---- Parsing (no IO) ----

def gameweeks(bootstrap):
    """[{event_id, name, deadline, finished, data_checked}] sorted by gameweek."""
    return sorted(({'event_id': e['id'], 'name': e.get('name'), 'deadline': parse_time(e['deadline_time']),
                    'finished': bool(e.get('finished')), 'data_checked': bool(e.get('data_checked'))}
                   for e in bootstrap.get('events') or [] if e.get('id') and e.get('deadline_time')),
                  key=lambda w: w['event_id'])


def season_of(weeks):
    """Season start year (2026 = 2026/27), from the first deadline."""
    if not weeks:
        raise ValueError('No FPL gameweeks with deadlines')
    first = min(w['deadline'] for w in weeks)
    return first.year if first.month >= 6 else first.year - 1


def target_gameweek(weeks, now):
    """The gameweek the current state is an input to: the earliest deadline still ahead."""
    ahead = [w for w in weeks if w['deadline'] > now]
    return min(ahead, key=lambda w: w['deadline']) if ahead else None


def player_states(bootstrap):
    """Price, position, team, availability and penalty order of every FPL player, sorted by FPL id."""
    positions = {t['id']: t.get('singular_name_short') for t in bootstrap.get('element_types') or []}
    rows = [{'fpl_player_id': e['id'], 'fpl_code': e.get('code'), 'web_name': e.get('web_name'),
             'fpl_team_id': e.get('team'), 'element_type': e.get('element_type'),
             'position': positions.get(e.get('element_type')), 'price_tenths': e.get('now_cost'),
             'status': e.get('status'), 'chance_this_round': e.get('chance_of_playing_this_round'),
             'chance_next_round': e.get('chance_of_playing_next_round'),
             'news': e.get('news') or None, 'news_added': _iso(e.get('news_added')),
             'penalties_order': e.get('penalties_order')}
            for e in bootstrap.get('elements') or [] if e.get('id')]
    return sorted(rows, key=lambda r: r['fpl_player_id'])


def known_fixtures(fixtures):
    """Schedule only (no scores), so a finished match does not look like a changed input.
    event_id None is a fixture FPL has not placed in a gameweek (postponed/unscheduled)."""
    rows = [{'fpl_fixture_id': f['id'], 'event_id': f.get('event'), 'kickoff': _iso(f.get('kickoff_time')),
             'fpl_team_h': f.get('team_h'), 'fpl_team_a': f.get('team_a'),
             'difficulty_h': f.get('team_h_difficulty'), 'difficulty_a': f.get('team_a_difficulty')}
            for f in fixtures or [] if f.get('id')]
    return sorted(rows, key=lambda r: r['fpl_fixture_id'])


def result_rows(live):
    """/event/{id}/live -> per-player actual points, sorted by FPL id."""
    rows = []
    for e in (live or {}).get('elements') or []:
        stats = e.get('stats') or {}
        if not e.get('id') or stats.get('total_points') is None:
            continue
        rows.append({'fpl_player_id': e['id'], 'total_points': stats['total_points'],
                     'minutes': stats.get('minutes'), 'stats': stats, 'explain': e.get('explain') or []})
    return sorted(rows, key=lambda r: r['fpl_player_id'])


# ---- ID mapping ----

_FOLD = str.maketrans({'ø': 'o', 'ł': 'l', 'đ': 'd', 'ß': 'ss', 'æ': 'ae', 'ı': 'i', 'œ': 'oe', 'þ': 'th'})


def normalise(name):
    text = unicodedata.normalize('NFKD', (name or '').lower().translate(_FOLD))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.sub(r"[^a-z ]+", ' ', text.replace("'", '')).split())


def load_overrides(path=OVERRIDES_PATH):
    """Manual mappings keyed by FPL code (stable across seasons): {'teams': {}, 'players': {}}."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        data = {}
    return {kind: {int(k): int(v) for k, v in (data.get(kind) or {}).items()} for kind in ('teams', 'players')}


def _unique(matches, method):
    ids = sorted(set(matches))
    if len(ids) == 1:
        return ids[0], method, {}
    if ids:
        return None, 'ambiguous', {'candidates': ids, 'at': method}
    return None


def match_team(team, candidates, overrides):
    """candidates: [(api_team_id, name, code)] from this season's Premier League clubs."""
    if team.get('code') in overrides:
        return overrides[team['code']], 'manual', {}
    name = normalise(team.get('name'))
    name = TEAM_ALIASES.get(name, name)
    return (_unique([c[0] for c in candidates if normalise(c[1]) == name], 'name')
            or _unique([c[0] for c in candidates if c[2] and c[2] == team.get('short_name')], 'short_code')
            or (None, 'unmatched', {}))


def match_player(element, candidates, overrides):
    """candidates: [(api_player_id, name, firstname, lastname)] at the mapped club. Stops at the
    first rule that finds anyone; more than one hit is 'ambiguous', never a guess."""
    if element.get('code') in overrides:
        return overrides[element['code']], 'manual', {}
    first, second = normalise(element.get('first_name')), normalise(element.get('second_name'))
    full, web = f'{first} {second}'.strip(), normalise(element.get('web_name'))
    tokens = set(full.split()) | set(web.split())
    rules = [
        ('full_name', lambda c: normalise(f'{c[2] or ""} {c[3] or ""}') == full),
        ('initial_surname', lambda c: bool(first) and normalise(c[1]) == f'{first[0]} {second}'),
        ('web_name', lambda c: web and web in (normalise(c[1]), normalise(c[3]))),
        # "Gabriel Magalhães" against FPL "Gabriel dos Santos Magalhães": every multi-letter
        # word of the provider name appears in the FPL names, and any initial starts one of them or
        # FPL's first name is one of the provider's ("J. Murphy" is not FPL's Alex Murphy; "E. Kroupi",
        # first names Eli Junior, is FPL's Junior Kroupi)
        ('name_tokens', lambda c: (words := [w for w in normalise(c[1]).split() if len(w) > 1])
                                  and set(words) <= tokens
                                  and (all(any(t.startswith(w) for t in tokens)
                                           for w in normalise(c[1]).split() if len(w) == 1)
                                       or (bool(first) and first in normalise(c[2]).split()))),
    ]
    for method, rule in rules:
        found = _unique([c[0] for c in candidates if rule(c)], method)
        if found:
            return found
    return None, 'unmatched', {}


def mapping_rows(kind, season, items, captured):
    rows = []
    for fpl_id, code, api_id, method, detail in items:
        row = {'kind': kind, 'season': season, 'fpl_id': fpl_id, 'fpl_code': code, 'api_id': api_id,
               'method': method, 'detail': detail}
        rows.append(dict(row, content_hash=_digest(row), captured_at=captured))
    return rows


def _store_mappings(conn, rows):
    """Append a mapping only when it differs from the latest stored one for that FPL id."""
    if not rows:
        return 0
    latest = dict(((k, s, f), h) for k, s, f, h in conn.execute(
        '''SELECT DISTINCT ON (kind,season,fpl_id) kind,season,fpl_id,content_hash FROM fpl_id_map
           WHERE kind=%s AND season=%s ORDER BY kind,season,fpl_id,captured_at DESC,map_id DESC''',
        [rows[0]['kind'], rows[0]['season']]).fetchall())
    new = [dict(r, detail=json.dumps(r['detail'])) for r in rows
           if latest.get((r['kind'], r['season'], r['fpl_id'])) != r['content_hash']]
    with conn.cursor() as cur:
        cur.executemany('''INSERT INTO fpl_id_map (kind,season,fpl_id,fpl_code,api_id,method,detail,captured_at,content_hash)
            VALUES (%(kind)s,%(season)s,%(fpl_id)s,%(fpl_code)s,%(api_id)s,%(method)s,%(detail)s::jsonb,
                    %(captured_at)s,%(content_hash)s)''', new)
    return len(new)


def map_ids(conn, season, bootstrap, captured, overrides=None):
    """Map FPL clubs and players to API-Football ids; returns {fpl_team_id: api_team_id}."""
    overrides = load_overrides() if overrides is None else overrides
    clubs = conn.execute('''SELECT t.team_id,t.name,t.code FROM team_seasons ts JOIN teams t USING (team_id)
                            WHERE ts.league_id=%s AND ts.season=%s''', [PL_LEAGUE, season]).fetchall()
    team_items = []
    for t in bootstrap.get('teams') or []:
        api_id, method, detail = match_team(t, clubs, overrides['teams'])
        team_items.append((t['id'], t.get('code'), api_id, method, dict(detail, name=t.get('name'))))
    teams = {fpl: api for fpl, _, api, _, _ in team_items if api}
    # candidates: the squad, this season's players, and anyone on a team sheet for the club this
    # season or last (the fantasy predictions' pool: players injured all season or not yet in a squad)
    squads = {}
    for team, pid, name, first, last in conn.execute(
            '''SELECT DISTINCT s.team_id,p.player_id,p.name,p.firstname,p.lastname FROM (
                   SELECT team_id,player_id FROM team_squads WHERE team_id=ANY(%s)
                   UNION SELECT team_id,player_id FROM player_seasons
                   WHERE league_id=%s AND season=%s AND team_id=ANY(%s)
                   UNION SELECT fp.team_id,fp.player_id FROM fixture_players fp JOIN fixtures f USING (fixture_id)
                   WHERE f.league_id=%s AND f.season>=%s AND fp.team_id=ANY(%s)) s JOIN players p USING (player_id)''',
            [list(teams.values()), PL_LEAGUE, season, list(teams.values()), PL_LEAGUE, season - 1, list(teams.values())]):
        squads.setdefault(team, []).append((pid, name, first, last))
    player_items = []
    for e in bootstrap.get('elements') or []:
        api_team = teams.get(e.get('team'))
        api_id, method, detail = (match_player(e, squads.get(api_team, []), overrides['players'])
                                  if api_team or e.get('code') in overrides['players'] else (None, 'unmatched', {}))
        detail = dict(detail, first_name=e.get('first_name'), second_name=e.get('second_name'),
                      web_name=e.get('web_name'), fpl_team_id=e.get('team'), api_team_id=api_team)
        player_items.append((e['id'], e.get('code'), api_id, method, detail))
    stored = (_store_mappings(conn, mapping_rows('team', season, team_items, captured))
              + _store_mappings(conn, mapping_rows('player', season, player_items, captured)))
    unmatched = sum(1 for item in player_items if item[2] is None)
    log.info('FPL mapping: %d/%d clubs, %d/%d players mapped; %d mapping changes stored',
             len(teams), len(team_items), len(player_items) - unmatched, len(player_items), stored)
    return teams


# ---- Capture (IO) ----

def _record_gameweeks(conn, season, weeks, captured):
    with conn.cursor() as cur:
        cur.executemany('''INSERT INTO fpl_gameweeks (season,event_id,name,deadline,first_captured_at)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (season,event_id,deadline) DO NOTHING''',
                        [(season, w['event_id'], w['name'], w['deadline'], captured) for w in weeks])


def make_capture(season, week, fixtures, players, captured):
    if captured.tzinfo is None:
        raise ValueError('Capture time must be timezone-aware')
    times = snapshot_times(captured_at=captured, effective_at=week['deadline'])
    content = {'season': season, 'event_id': week['event_id'], 'effective_at': times['effective_at'],
               'fixtures': fixtures, 'players': players}
    return dict(season=season, event_id=week['event_id'], **times,
                source='prospective' if captured < week['deadline'] else 'late_observation',
                seconds_to_deadline=(week['deadline'] - captured).total_seconds(),
                fixtures=fixtures, players=players, content_hash=_digest(content))


def store_capture(conn, capture):
    """Append a pre-deadline state when it differs from the latest for that gameweek.
    Returns the capture id, or None if unchanged."""
    config.require_db_write('capture FPL state')
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('fpl_captures'))")
    latest = conn.execute('''SELECT content_hash FROM fpl_captures WHERE season=%s AND event_id=%s
        ORDER BY captured_at DESC, capture_id DESC LIMIT 1''', [capture['season'], capture['event_id']]).fetchone()
    if latest and latest[0] == capture['content_hash']:
        return None
    capture_id = conn.execute('''INSERT INTO fpl_captures (season,event_id,source,captured_at,effective_at,
            seconds_to_deadline,fixtures,player_count,content_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) RETURNING capture_id''',
        [capture['season'], capture['event_id'], capture['source'], capture['captured_at'], capture['effective_at'],
         capture['seconds_to_deadline'], json.dumps(capture['fixtures']), len(capture['players']),
         capture['content_hash']]).fetchone()[0]
    cols = ('fpl_player_id', 'fpl_code', 'web_name', 'fpl_team_id', 'element_type', 'position', 'price_tenths',
            'status', 'chance_this_round', 'chance_next_round', 'news', 'news_added', 'penalties_order')
    with conn.cursor() as cur:
        cur.executemany(f'''INSERT INTO fpl_player_states (capture_id,{','.join(cols)})
            VALUES (%s,{','.join(['%s'] * len(cols))})''',
                        [(capture_id, *(p[c] for c in cols)) for p in capture['players']])
    return capture_id


def capture(client, conn, now=None):
    """Store the next gameweek's source state, gameweek deadlines and ID mapping; commits."""
    config.require_db_write('capture FPL state')
    bootstrap = client.get('bootstrap-static/')
    fixtures = client.get('fixtures/')
    # Observation time is taken at the source boundary, before any mapping work
    captured = now or datetime.now(timezone.utc)
    weeks = gameweeks(bootstrap)
    season = season_of(weeks)
    _record_gameweeks(conn, season, weeks, captured)
    map_ids(conn, season, bootstrap, captured)
    week = target_gameweek(weeks, captured)
    if week is None:
        conn.commit()
        log.info('FPL %d: no deadline ahead; gameweeks and mapping recorded only', season)
        return None
    capture_id = store_capture(conn, make_capture(season, week, known_fixtures(fixtures),
                                                  player_states(bootstrap), captured))
    conn.commit()
    log.info('FPL %d GW%d (deadline %s): %s', season, week['event_id'], week['deadline'].isoformat(),
             f'capture {capture_id} stored' if capture_id else 'unchanged since last capture')
    return capture_id


def make_result_capture(season, week, rows, captured):
    content = {'season': season, 'event_id': week['event_id'], 'finished': week['finished'],
               'data_checked': week['data_checked'], 'rows': rows}
    return dict(season=season, event_id=week['event_id'], finished=week['finished'],
                data_checked=week['data_checked'], captured_at=captured, rows=rows, content_hash=_digest(content))


def store_result_capture(conn, result):
    config.require_db_write('capture FPL results')
    if not result['rows']:
        return None          # no answer is not a gameweek where everyone scored nothing
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('fpl_result_captures'))")
    latest = conn.execute('''SELECT content_hash FROM fpl_result_captures WHERE season=%s AND event_id=%s
        ORDER BY captured_at DESC, result_capture_id DESC LIMIT 1''', [result['season'], result['event_id']]).fetchone()
    if latest and latest[0] == result['content_hash']:
        return None
    result_id = conn.execute('''INSERT INTO fpl_result_captures (season,event_id,finished,data_checked,captured_at,
            player_count,content_hash) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING result_capture_id''',
        [result['season'], result['event_id'], result['finished'], result['data_checked'], result['captured_at'],
         len(result['rows']), result['content_hash']]).fetchone()[0]
    with conn.cursor() as cur:
        cur.executemany('''INSERT INTO fpl_player_results (result_capture_id,fpl_player_id,total_points,minutes,stats,explain)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb)''',
                        [(result_id, r['fpl_player_id'], r['total_points'], r['minutes'], json.dumps(r['stats']),
                          json.dumps(r['explain'])) for r in result['rows']])
    return result_id


def results_due(conn, season, weeks, events=None):
    """Finished gameweeks without a stored result that FPL had marked final (data_checked)."""
    if events:
        return [w for w in weeks if w['event_id'] in set(events)]
    checked = {e for (e,) in conn.execute('''SELECT DISTINCT event_id FROM fpl_result_captures
                                             WHERE season=%s AND data_checked''', [season])}
    return [w for w in weeks if w['finished'] and w['event_id'] not in checked]


def capture_results(client, conn, events=None):
    """Actual points for finished gameweeks; re-fetched until FPL marks them final. Commits."""
    config.require_db_write('capture FPL results')
    weeks = gameweeks(client.get('bootstrap-static/'))
    season = season_of(weeks)
    stored = 0
    for week in results_due(conn, season, weeks, events):
        rows = result_rows(client.get(f'event/{week["event_id"]}/live/'))
        stored += store_result_capture(conn, make_result_capture(season, week, rows, datetime.now(timezone.utc))) is not None
        conn.commit()
    log.info('FPL %d results: %d new gameweek result states', season, stored)
    return stored


# ---- Reading inputs as known at a time (for a future model, without look-ahead) ----

def state_as_of(conn, season, event_id, as_of):
    """Latest capture for a gameweek observed and inserted by as_of, with its player rows."""
    header = conn.execute('''SELECT capture_id,captured_at,effective_at,source,fixtures FROM fpl_captures
        WHERE season=%s AND event_id=%s AND captured_at<=%s AND created_at<=%s
        ORDER BY captured_at DESC, capture_id DESC LIMIT 1''', [season, event_id, as_of, as_of]).fetchone()
    if header is None:
        return None
    cur = conn.execute('SELECT * FROM fpl_player_states WHERE capture_id=%s ORDER BY fpl_player_id', [header[0]])
    names = [c.name for c in cur.description]
    return {'capture_id': header[0], 'captured_at': header[1], 'deadline': header[2], 'source': header[3],
            'fixtures': header[4], 'players': [dict(zip(names, row)) for row in cur.fetchall()]}


# ---- Fantasy prediction snapshots ----

def make_prediction_snapshot(*, season, event_id, deadline, predictions, inputs, version_id,
                             captured_at, source, input_capture_id=None):
    """predictions: [{'fpl_player_id': int, 'expected_points': float, ...}] where any extra field
    is a number or None. Register the version with ModelType.FANTASY first."""
    if source not in ('prospective', 'reconstruction', 'late_observation'):
        raise ValueError('Unknown snapshot source')
    if source == 'prospective' and input_capture_id is None:
        raise ValueError('A prospective fantasy prediction must name the FPL capture it used')
    if not isinstance(inputs, dict):
        raise ValueError('inputs must be a JSON object')
    seen, clean = set(), []
    for p in predictions:
        pid = p.get('fpl_player_id')
        if not isinstance(pid, int) or isinstance(pid, bool) or pid in seen:
            raise ValueError('Each prediction needs a unique integer fpl_player_id')
        for key, value in p.items():
            if key != 'fpl_player_id' and value is not None and (
                    isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError(f'{key} must be a finite number or None')
        if p.get('expected_points') is None:
            raise ValueError('expected_points is required')
        seen.add(pid)
        clean.append(dict(p))
    if not clean:
        raise ValueError('No predictions')
    clean.sort(key=lambda p: p['fpl_player_id'])
    times = snapshot_times(captured_at=captured_at, effective_at=deadline)
    if source == 'prospective' and captured_at >= deadline:
        source = 'late_observation'
    values = dict(season=season, event_id=event_id, model_version_id=version_id, input_capture_id=input_capture_id,
                  source=source, **times, seconds_to_deadline=(deadline - captured_at).total_seconds(),
                  predictions=clean, inputs=inputs)
    identity = {k: v for k, v in values.items() if k not in ('captured_at', 'seconds_to_deadline')}
    values['content_hash'] = _digest(identity)
    values['predictions'] = json.dumps(clean, allow_nan=False)
    values['inputs'] = json.dumps(inputs, allow_nan=False)
    return values


def append_prediction_snapshots(conn, rows):
    """Caller owns the transaction. Identical retries keep the first row."""
    if not rows:
        return
    config.require_db_write('append fantasy prediction snapshots')
    columns = tuple(rows[0])
    placeholders = ','.join(f'%({k})s' + ('::jsonb' if k in ('predictions', 'inputs') else '') for k in columns)
    with conn.cursor() as cur:
        cur.executemany(f'''INSERT INTO fantasy_prediction_snapshots ({','.join(columns)}) VALUES ({placeholders})
            ON CONFLICT (season,event_id,model_version_id,source,content_hash) DO NOTHING''', rows)
