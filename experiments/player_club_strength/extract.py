"""Freeze player experiment inputs using SELECTs in an enforced read-only transaction."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import dotenv_values
import psycopg
from thecornerfc import config, player_ratings as pr


def main():
    env = dotenv_values('.env')
    # Restricted role has RLS-hidden rows; enforce READ ONLY on the main connection.
    with psycopg.connect(env['DATABASE_URL'].strip(), connect_timeout=15,
                          options='-c default_transaction_read_only=on') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        conn.execute("SET LOCAL statement_timeout='180s'")
        data = {'extracted_at': str(conn.execute('select now()').fetchone()[0]),
                'leagues': config.MATCH_PLAYER_LEAGUES}
        data['captures'] = [list(r) for r in conn.execute(
            'select captured_at,population,model_version_id from player_rating_captures order by captured_at')]
        data['fixtures'] = conn.execute('''select f.fixture_id,f.kickoff,f.league_id,f.season,
            f.home_team_id,f.away_team_id,f.home_goals,f.away_goals,
            h.rank_before,h.lt_before,a.rank_before,a.lt_before,
            ox.expected_goals::float8,hx.expected_goals::float8
            from fixtures f
            join team_rank_history h on h.fixture_id=f.fixture_id and h.team_id=f.home_team_id
            join team_rank_history a on a.fixture_id=f.fixture_id and a.team_id=f.away_team_id
            left join fixture_team_stats ox on ox.fixture_id=f.fixture_id and ox.team_id=f.away_team_id
            left join fixture_team_stats hx on hx.fixture_id=f.fixture_id and hx.team_id=f.home_team_id
            where f.league_id=any(%s) and f.status_short='FT'
            and f.kickoff>='2020-01-01' and f.kickoff<now()
            order by f.kickoff,f.fixture_id''', [config.MATCH_PLAYER_LEAGUES], binary=True).fetchall()
        ids = [r[0] for r in data['fixtures']]
        cols = ','.join('fp.' + k for k in pr.STATS[3:])
        data['apps'] = conn.execute(f'''select fp.fixture_id,fp.team_id,fp.player_id,
            fp.minutes,fp.started,fp.position,fp.role,fp.rating::float8,{cols}
            from fixture_players fp where fp.fixture_id=any(%s) and fp.minutes>0
            order by fp.fixture_id,fp.team_id,fp.player_id''', [ids], binary=True).fetchall()
        data['players'] = conn.execute('select player_id,name,birth_date,current_rank,rank_position,rank_minutes from players').fetchall()
        data['teams'] = conn.execute('select team_id,name from teams').fetchall()
    encoded = json.dumps(data, default=str, separators=(',', ':')).encode()
    path = Path('.cache/player_club_strength_inputs.json.gz')
    path.write_bytes(gzip.compress(encoded))
    print(json.dumps({'fixtures':len(data['fixtures']),'appearances':len(data['apps']),
                      'captures':data['captures'],'sha256':hashlib.sha256(encoded).hexdigest()}, default=str))

if __name__ == '__main__':
    try:
        main()
    except psycopg.Error as exc:
        print(json.dumps({'error_type':type(exc).__name__,'sqlstate':exc.sqlstate}))
        sys.exit(1)
