"""Append-only squad and transfer evidence for prospective evaluation (experiments/prospective,
protocols P1/P2). Captured only: no rating or prediction reads these tables."""
from datetime import datetime, timezone
import hashlib
import json
import logging

from . import config

log = logging.getLogger(__name__)

TRANSFER_MAX_CALLS = 300          # /transfers?team= requests per night, clubs with changed squads first
TRANSFER_SINCE = '2025-07-01'     # older transfers are not needed for forward evaluation


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def squad_players(items, mapped):
    """/players/squads items -> sorted [{api_player, player, name, position}]. `player` is the
    match-data id sync_squads mapped it to (None if unknown). Age and shirt number are left out so
    a birthday or a number change is not recorded as a squad change."""
    players = {}
    for item in items:
        for pl in item.get('players') or []:
            if pl.get('id'):
                players[pl['id']] = {'api_player': pl['id'], 'player': mapped.get(pl['id']),
                                     'name': pl.get('name'), 'position': pl.get('position')}
    return [players[k] for k in sorted(players)]


def capture_squad(conn, team, players, captured=None):
    """Store the squad when it differs from the club's latest stored squad. Returns True if stored."""
    if not players:
        return False          # no answer is not an empty squad
    config.require_db_write('capture squad snapshot')
    digest = _digest(players)
    latest = conn.execute('SELECT content_hash FROM squad_snapshots WHERE team_id=%s ORDER BY captured_at DESC, '
                          'snapshot_id DESC LIMIT 1', [team]).fetchone()
    if latest and latest[0] == digest:
        return False
    conn.execute('INSERT INTO squad_snapshots (team_id,source,captured_at,players,content_hash) '
                 'VALUES (%s,%s,%s,%s::jsonb,%s)',
                 [team, 'api_football/players/squads', captured or datetime.now(timezone.utc),
                  json.dumps(players), digest])
    return True


def transfer_rows(items, captured, since=TRANSFER_SINCE):
    rows = {}
    for item in items:
        player = item.get('player') or {}
        for t in item.get('transfers') or []:
            date = t.get('date')
            if not player.get('id') or not date or date < since:
                continue
            teams = t.get('teams') or {}
            row = {'player_id': player['id'], 'player_name': player.get('name'), 'transfer_date': date,
                   'transfer_type': t.get('type'), 'team_in': (teams.get('in') or {}).get('id'),
                   'team_out': (teams.get('out') or {}).get('id')}
            rows[_digest(row)] = row
    return [dict(r, content_hash=h, captured_at=captured, source='api_football/transfers') for h, r in rows.items()]


def teams_due(conn, teams, limit=TRANSFER_MAX_CALLS):
    """Clubs never fetched, then clubs whose stored squad changed since their last transfer fetch."""
    rows = conn.execute('''SELECT t.team, f.last, s.last FROM unnest(%s::int[]) t(team)
        LEFT JOIN LATERAL (SELECT max(fetched_at) last FROM transfer_fetches WHERE team_id=t.team) f ON true
        LEFT JOIN LATERAL (SELECT max(captured_at) last FROM squad_snapshots WHERE team_id=t.team) s ON true''',
                        [list(teams)]).fetchall()
    never = sorted(team for team, fetched, _ in rows if fetched is None)
    changed = sorted((fetched, team) for team, fetched, squad in rows
                     if fetched is not None and squad is not None and squad > fetched)
    return (never + [team for _, team in changed])[:limit]


def sync_transfers(api, conn, teams, limit=TRANSFER_MAX_CALLS):
    due = teams_due(conn, teams, limit)
    log.info('Transfers to fetch: %d clubs (cap %d)', len(due), limit)
    config.require_db_write('capture transfers')
    stored = 0
    for n, team in enumerate(due, 1):
        captured = datetime.now(timezone.utc)
        rows = transfer_rows(api.get('transfers', team=team), captured)
        with conn.cursor() as cur:
            cur.executemany('''INSERT INTO transfer_observations (player_id,player_name,transfer_date,transfer_type,
                team_in,team_out,source,captured_at,content_hash) VALUES (%(player_id)s,%(player_name)s,
                %(transfer_date)s,%(transfer_type)s,%(team_in)s,%(team_out)s,%(source)s,%(captured_at)s,
                %(content_hash)s) ON CONFLICT (content_hash) DO NOTHING''', rows)
        conn.execute('INSERT INTO transfer_fetches (team_id,records) VALUES (%s,%s)', [team, len(rows)])
        stored += len(rows)
        if n % 50 == 0:
            conn.commit()
    conn.commit()
    log.info('Transfers: %d clubs fetched, %d recent transfer reports seen', len(due), stored)
