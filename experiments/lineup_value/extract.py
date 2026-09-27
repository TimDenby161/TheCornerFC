"""Read-only frozen inputs for a retrospective lineup ablation."""
import gzip,json,sys,hashlib
from pathlib import Path
from dotenv import dotenv_values
import psycopg

def main():
    with psycopg.connect(dotenv_values('.env')['DATABASE_URL'].strip(),connect_timeout=15,options='-c default_transaction_read_only=on') as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        c.execute("SET LOCAL statement_timeout='180s'")
        data={'extracted_at':str(c.execute('select now()').fetchone()[0])}
        data['audit']={}
        for table in ['match_prediction_snapshots','lineup_prediction_snapshots','official_lineup_snapshots']:
            data['audit'][table]=c.execute(f'''select s.source,count(*),count(*) filter(where f.status_short='FT'),count(distinct s.fixture_id) filter(where f.status_short='FT') from {table} s join fixtures f using(fixture_id) group by s.source''').fetchall()
        data['columns']={t:[r[0] for r in c.execute('select column_name from information_schema.columns where table_name=%s order by ordinal_position',[t])] for t in ['fixture_team_ratings','odds_observations','model_versions']}
        data['snapshots']=c.execute('''select distinct on(s.fixture_id) s.fixture_id,s.effective_at,s.league_id,f.home_goals,f.away_goals,s.source,s.captured_at,s.created_at,s.exp_diff,s.home_xg,s.away_xg,s.p_home,s.p_draw,s.p_away,s.inputs,s.model_version_id from match_prediction_snapshots s join fixtures f using(fixture_id) where f.status_short='FT' order by s.fixture_id,(s.source='prospective') desc,s.captured_at desc''',binary=True).fetchall()
        data['lines']=c.execute('select * from fixture_team_ratings',binary=True).fetchall()
        data['versions']=c.execute('select * from model_versions',binary=True).fetchall()
        data['lineups']=c.execute('select fixture_id,team_id,source,captured_at,created_at,effective_at,players,selection_inputs,availability from lineup_prediction_snapshots',binary=True).fetchall()
        data['official']=c.execute('select fixture_id,team_id,captured_at,created_at,effective_at,players from official_lineup_snapshots',binary=True).fetchall()
    b=json.dumps(data,default=str,separators=(',',':')).encode();Path('.cache/lineup_value_inputs.json.gz').write_bytes(gzip.compress(b))
    print(json.dumps({'audit':data['audit'],'columns':data['columns'],'snapshots':len(data['snapshots']),'sha256':hashlib.sha256(b).hexdigest()},default=str))
if __name__=='__main__':
    try:main()
    except psycopg.Error as e:
        print(type(e).__name__,e.sqlstate);sys.exit(1)
