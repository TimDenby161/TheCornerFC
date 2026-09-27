"""Additional read-only history and market evidence; no external API calls."""
import gzip,json,sys,hashlib
from pathlib import Path
from dotenv import dotenv_values
import psycopg

def main():
    with psycopg.connect(dotenv_values('.env')['DATABASE_URL'].strip(),connect_timeout=15,options='-c default_transaction_read_only=on') as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        c.execute("SET LOCAL statement_timeout='180s'")
        d={'extracted_at':str(c.execute('select now()').fetchone()[0])}
        d['fixtures']=c.execute('''select f.fixture_id,f.kickoff,f.league_id,f.home_team_id,f.away_team_id,f.home_goals,f.away_goals,hx.expected_goals::float8,ax.expected_goals::float8,
        h.rank_before,h.lt_before,a.rank_before,a.lt_before,h.split_before,a.split_before,h.edge_before,a.edge_before,h.goal_base,a.goal_base
        from fixtures f left join fixture_team_stats hx on hx.fixture_id=f.fixture_id and hx.is_home
        left join fixture_team_stats ax on ax.fixture_id=f.fixture_id and not ax.is_home
        left join team_rank_history h on h.fixture_id=f.fixture_id and h.team_id=f.home_team_id
        left join team_rank_history a on a.fixture_id=f.fixture_id and a.team_id=f.away_team_id
        where f.status_short in ('FT','AET','PEN') and f.home_goals is not null and f.away_goals is not null and f.kickoff<now() order by f.kickoff,f.fixture_id''',binary=True).fetchall()
        d['starters']=c.execute('''select fp.fixture_id,fp.team_id,count(*),count(r.player_rank) from fixture_players fp left join fixture_player_ranks r using(fixture_id,player_id) where fp.started group by fp.fixture_id,fp.team_id''',binary=True).fetchall()
        d['odds']=c.execute('''select o.fixture_id,o.bookmaker_id,o.selection,o.odds::float8,o.captured_at,o.created_at from odds_observations o join fixtures f using(fixture_id) where market_id=1 and f.status_short='FT' and o.captured_at<f.kickoff and o.created_at<f.kickoff''',binary=True).fetchall()
        d['snapshots']=c.execute('''select s.fixture_id,s.effective_at,s.league_id,f.home_goals,f.away_goals,s.source,s.captured_at,s.created_at,s.exp_diff,s.home_xg,s.away_xg,s.p_home,s.p_draw,s.p_away,s.inputs,s.model_version_id from match_prediction_snapshots s join fixtures f using(fixture_id) where f.status_short='FT' order by s.fixture_id,s.captured_at''',binary=True).fetchall()
        d['leagues']=c.execute('select league_id,name from leagues').fetchall()
    b=json.dumps(d,default=str,separators=(',',':')).encode();Path('.cache/lineup_value_history.json.gz').write_bytes(gzip.compress(b))
    print(json.dumps({'fixtures':len(d['fixtures']),'starter_groups':len(d['starters']),'odds':len(d['odds']),'sha256':hashlib.sha256(b).hexdigest()}))
if __name__=='__main__':
    try:main()
    except psycopg.Error as e: print(type(e).__name__,e.sqlstate);sys.exit(1)
