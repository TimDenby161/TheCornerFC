"""Read-only frozen inputs for the fantasy v1 backtest. No writes, no API calls."""
import gzip, hashlib, json, sys
from pathlib import Path
from dotenv import dotenv_values
import psycopg

OUT = Path('.cache/fantasy_v1_inputs.json.gz')
PL = 39


def main():
    # The local read-only role sees no rows (RLS), so this uses the main credential inside a
    # read-only session and a read-only repeatable-read transaction, as the other experiments do.
    with psycopg.connect(dotenv_values('.env')['DATABASE_URL'].strip(), connect_timeout=15,
                         options='-c default_transaction_read_only=on') as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        c.execute("SET LOCAL statement_timeout='300s'")
        q = lambda sql, *a: c.execute(sql, *a).fetchall()
        d = {'extracted_at': str(q('select now()')[0][0])}
        d['audit'] = {t: q(f'select count(*) from {t}')[0][0] for t in (
            'fpl_captures', 'fpl_player_states', 'fpl_player_results', 'fpl_id_map', 'fantasy_prediction_snapshots')}
        d['fixtures'] = q('''select fixture_id, season, round, kickoff, status_short, home_team_id, away_team_id,
                                    home_goals, away_goals from fixtures
                             where league_id=%s and season>=2020 order by kickoff, fixture_id''', [PL])
        d['players'] = q('''select fp.fixture_id, fp.team_id, fp.player_id, fp.minutes, fp.started, fp.position, fp.role,
                                   fp.goals, fp.assists, fp.shots, fp.shots_on, fp.key_passes, fp.saves,
                                   fp.goals_conceded, fp.penalties_saved, fp.yellow_cards, fp.red_cards
                            from fixture_players fp join fixtures f using (fixture_id)
                            where f.league_id=%s and f.season>=2020''', [PL])
        # Appearances elsewhere, so a player who has moved clubs leaves his old club's universe
        d['elsewhere'] = q('''select fp.player_id, fp.team_id, f.kickoff from fixture_players fp join fixtures f using (fixture_id)
                              where f.league_id<>%s and f.kickoff >= '2020-07-01' and fp.minutes > 0
                                and fp.player_id in (select distinct fp2.player_id from fixture_players fp2
                                                     join fixtures f2 using (fixture_id) where f2.league_id=%s)''', [PL, PL])
        d['predictions'] = q('''select p.fixture_id, p.home_xg::float8, p.away_xg::float8, p.source
                                from fixture_predictions p join fixtures f using (fixture_id) where f.league_id=%s''', [PL])
        d['prospective'] = q('''select s.fixture_id, s.captured_at, s.created_at, s.effective_at, s.home_xg::float8,
                                       s.away_xg::float8, s.model_version_id
                                from match_prediction_snapshots s join fixtures f using (fixture_id)
                                where f.league_id=%s and s.source='prospective' ''', [PL])
        d['team_saves'] = q('''select s.fixture_id, s.team_id, s.goalkeeper_saves from fixture_team_stats s
                               join fixtures f using (fixture_id) where f.league_id=%s''', [PL])
        d['injuries'] = q('''select i.fixture_id, i.team_id, i.player_id, i.type from injuries i
                             join fixtures f using (fixture_id) where f.league_id=%s''', [PL])
        d['ranks'] = q('''select r.fixture_id, r.player_id, r.player_rank::float8 from fixture_player_ranks r
                          join fixtures f using (fixture_id) where f.league_id=%s''', [PL])
        d['lineup_snapshots'] = q('''select s.fixture_id, s.team_id, s.captured_at, s.effective_at, s.players
                                     from lineup_prediction_snapshots s join fixtures f using (fixture_id)
                                     where f.league_id=%s and s.source='prospective' ''', [PL])
    raw = json.dumps(d, default=str, separators=(',', ':')).encode()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(gzip.compress(raw))
    print(json.dumps({'audit': d['audit'], **{k: len(v) for k, v in d.items() if isinstance(v, list)},
                      'sha256': hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    try:
        main()
    except psycopg.Error as e:
        print(type(e).__name__, e.sqlstate)
        sys.exit(1)
