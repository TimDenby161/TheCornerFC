"""Read-only inputs for the defensive-contribution and bonus check: FPL's final GW results
(owner-approved use, 2026-09-29) matched to API-Football stat lines. No writes, no API calls."""
import gzip, hashlib, json, sys
from pathlib import Path
from dotenv import dotenv_values
import psycopg

OUT = Path('.cache/fantasy_dc_inputs.json.gz')


def main():
    with psycopg.connect(dotenv_values('.env')['DATABASE_URL'].strip(), connect_timeout=15,
                         options='-c default_transaction_read_only=on') as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        q = lambda sql, *a: c.execute(sql, *a).fetchall()
        d = {'extracted_at': str(q('select now()')[0][0])}
        # the latest final (data_checked) result capture of each gameweek
        d['results'] = q('''select distinct on (c.event_id, r.fpl_player_id) c.season, c.event_id, r.fpl_player_id,
                                   r.minutes, r.stats, r.explain
                            from fpl_player_results r join fpl_result_captures c using (result_capture_id)
                            where c.data_checked order by c.event_id, r.fpl_player_id, c.captured_at desc''')
        d['map'] = q('''select season, fpl_id, api_id from fpl_id_map_current where kind = 'player' and api_id is not null''')
        d['positions'] = q('''select distinct on (s.fpl_player_id) s.fpl_player_id, s.position from fpl_player_states s
                              join fpl_captures c using (capture_id) order by s.fpl_player_id, c.captured_at desc''')
        d['gameweeks'] = q('select season, event_id, deadline from fpl_gameweeks order by season, event_id, deadline')
    raw = json.dumps(d, default=str, separators=(',', ':')).encode()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(gzip.compress(raw))
    print(json.dumps({k: len(v) for k, v in d.items() if isinstance(v, list)} | {'sha256': hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    try:
        main()
    except psycopg.Error as e:
        print(type(e).__name__, e.sqlstate)
        sys.exit(1)
