"""The owner's own FPL team (entry FPL_TEAM_ENTRY) for the My FPL team page: squad, selling
prices, bank, free transfers and chips left, written to docs/data/fpl_team.json. The page plans
transfers and chips from it and fpl_predictions.json in the browser (assets/fpl-planner.js).

Owner approved reading the manager endpoints for this entry and showing the result publicly on
2026-09-30 (README: My FPL team). Parsing is separate from IO, as in fpl.py.
"""
from datetime import datetime, timezone
import logging
from pathlib import Path

from . import fpl
from .export import OUT_DIR, _write_json_file

log = logging.getLogger(__name__)

FILENAME = 'fpl_team.json'
POSITIONS = {1: 'G', 2: 'D', 3: 'M', 4: 'F'}
MAX_FREE_TRANSFERS = 5
# Chips that keep banked free transfers (FPL rules since 2024/25): the week counts as no transfers
# made and no new free transfer
TRANSFER_CHIPS = {'wildcard', 'freehit'}


def selling_price(now, bought):
    """FPL keeps half of any rise (rounded down to £0.1m) and passes on every fall."""
    return now if now <= bought else bought + (now - bought) // 2


def free_transfers(history, started_event):
    """Free transfers for the week after the last one in history: 1 from the week after the
    first, +1 a week to MAX_FREE_TRANSFERS, less those used (hits don't go below zero)."""
    chips = {c['event']: c['name'] for c in history.get('chips') or []}
    ft = None
    for week in sorted(history.get('current') or [], key=lambda w: w['event']):
        if week['event'] <= started_event:
            ft = 1
            continue
        if ft is None:
            ft = 1
        if chips.get(week['event']) in TRANSFER_CHIPS:
            continue
        ft = min(MAX_FREE_TRANSFERS, max(ft - week.get('event_transfers', 0), 0) + 1)
    return ft or 1


def chip_windows(bootstrap, history):
    """Each chip FPL offers this season with its window and the week it was played (None = still
    available if its window hasn't closed)."""
    used = [(c['name'], c['event']) for c in history.get('chips') or []]
    rows = []
    for chip in sorted(bootstrap.get('chips') or [], key=lambda c: (c['start_event'], c['id'])):
        played = next((e for n, e in used if n == chip['name'] and chip['start_event'] <= e <= chip['stop_event']), None)
        rows.append({'name': chip['name'], 'start': chip['start_event'], 'stop': chip['stop_event'], 'played': played})
    return rows


def team_payload(bootstrap, entry, history, transfers, picks, api_players, api_teams, now=None):
    """fpl_team.json from FPL's responses. picks: the latest gameweek's picks (the one before a
    Free Hit, whose squad reverts); transfers already made for the next deadline are applied, as
    FPL has. api_players / api_teams: {fpl id: API-Football id} from fpl_id_map_current."""
    now = now or datetime.now(timezone.utc)
    weeks = fpl.gameweeks(bootstrap)
    nxt = fpl.target_gameweek(weeks, now)
    elements = {e['id']: e for e in bootstrap.get('elements') or []}
    current = entry.get('current_event')
    squad = [p['element'] for p in sorted(picks['picks'], key=lambda p: p['position'])]
    bank = picks['entry_history']['bank']
    made = [t for t in transfers if nxt and t['event'] == nxt['event_id']]
    bought = {}
    for t in sorted(transfers, key=lambda t: t['time']):
        bought[t['element_in']] = t['element_in_cost']
    for t in sorted(made, key=lambda t: t['time']):
        if t['element_out'] in squad:
            squad[squad.index(t['element_out'])] = t['element_in']
            bank += t['element_out_cost'] - t['element_in_cost']

    def player(fid):
        e = elements[fid]
        price = e['now_cost']
        paid = bought.get(fid, price - (e.get('cost_change_start') or 0))
        return {'fpl': fid, 'api': api_players.get(fid), 'name': e.get('web_name'),
                'pos': POSITIONS.get(e.get('element_type')), 'fpl_team': e.get('team'), 'team': api_teams.get(e.get('team')),
                'price': price, 'bought': paid, 'sell': selling_price(price, paid),
                'status': e.get('status'), 'chance': e.get('chance_of_playing_next_round')}

    ft = free_transfers(history, entry.get('started_event') or 1)
    return {
        'generated_at': now.isoformat(), 'entry': entry['id'], 'name': entry.get('name'),
        'season': fpl.season_of(weeks), 'current_event': current,
        'next_event': nxt['event_id'] if nxt else None, 'next_deadline': nxt['deadline'].isoformat() if nxt else None,
        'bank': bank, 'free_transfers': ft,
        'made': [{'out': t['element_out'], 'in': t['element_in'], 'out_cost': t['element_out_cost'],
                  'in_cost': t['element_in_cost'], 'out_name': elements.get(t['element_out'], {}).get('web_name'),
                  'in_name': elements.get(t['element_in'], {}).get('web_name')} for t in made],
        'squad': [player(fid) for fid in squad],
        'chips': chip_windows(bootstrap, history),
        'overall_points': entry.get('summary_overall_points'), 'overall_rank': entry.get('summary_overall_rank'),
        'history': [{'event': w['event'], 'points': w['points'], 'rank': w.get('overall_rank'),
                     'transfers': w.get('event_transfers', 0), 'hits': w.get('event_transfers_cost', 0),
                     'bench': w.get('points_on_bench')} for w in history.get('current') or []],
    }


def _mapping(conn, season, kind):
    return dict(conn.execute('''select fpl_id, api_id from fpl_id_map_current
                                where kind = %s and season = %s and api_id is not null''', [kind, season]).fetchall())


def export_team(client, conn, entry_id, out_dir=OUT_DIR):
    """Read the entry from FPL and write fpl_team.json. Reads the database only (the ID map)."""
    bootstrap = client.get('bootstrap-static/')
    entry = client.get(f'entry/{entry_id}/')
    current = entry.get('current_event')
    if not current:
        log.info('FPL team %d: no gameweek played yet; nothing written', entry_id)
        return None
    history = client.get(f'entry/{entry_id}/history/')
    transfers = client.get(f'entry/{entry_id}/transfers/')
    picks = client.get(f'entry/{entry_id}/event/{current}/picks/')
    if picks.get('active_chip') == 'freehit' and current > 1:     # squad and bank go back to the week before
        picks = client.get(f'entry/{entry_id}/event/{current - 1}/picks/')
    season = fpl.season_of(fpl.gameweeks(bootstrap))
    payload = team_payload(bootstrap, entry, history, transfers, picks,
                           _mapping(conn, season, 'player'), _mapping(conn, season, 'team'))
    _write_json_file(Path(out_dir) / FILENAME, payload, ensure_ascii=False)
    unmapped = [p['name'] for p in payload['squad'] if p['api'] is None]
    log.info('FPL team %d: GW%s, %d free transfers, bank £%.1fm%s', entry_id, payload['next_event'],
             payload['free_transfers'], payload['bank'] / 10,
             f'; not matched to our players: {", ".join(unmapped)}' if unmapped else '')
    return payload
