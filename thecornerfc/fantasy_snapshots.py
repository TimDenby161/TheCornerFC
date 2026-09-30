"""Prospective fantasy snapshots: every component of every Premier League player's expected
points for upcoming fixtures, stored in fantasy_fixture_snapshots before kickoff, together with
the availability and benchmark values known then, so each model can be judged later on gameweeks
it had not seen (experiments/prospective/PROTOCOLS.md: P8 for v1.1, P9 for v1.3, P10 for v1.4).

Calculations are fantasy.py's (the backtests run the same functions); the parameters are frozen
in fantasy_params.json (v1.1, experiments/fantasy_v1/run.py), fantasy_params_v1_3.json (v1.3,
experiments/fantasy_dc/run.py) and fantasy_params_v1_4.json (v1.4, experiments/fantasy_v1_4/run.py).
Each version's rows carry its model_version_id. Evidence only: nothing reads it, and
a failure here never fails the nightly or match-day run (capture_safely).
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path

from . import availability, config, fantasy as fm
from .cache import WEEK, cached_rows
from .model_versions import ModelType, current_code_sha, register_model_version, snapshot_times

log = logging.getLogger(__name__)

PL = 39
HORIZON = timedelta(days=8)       # fixtures this far ahead get a snapshot each run
HISTORY_SEASON = 2020             # league history read, as in the backtest
PARAMS_PATH = Path(__file__).with_name('fantasy_params.json')
CAPTURED = (PARAMS_PATH, Path(__file__).with_name('fantasy_params_v1_3.json'),
            Path(__file__).with_name('fantasy_params_v1_4.json'))                    # each run snapshots all three
TABLE = 'fantasy_fixture_snapshots'
BENCHMARK_MATCHES = 5


def load_params(path=PARAMS_PATH):
    return json.loads(path.read_text(encoding='utf-8'))


def register_version(conn, doc):
    root = Path(__file__).parent
    start, end = (datetime.fromisoformat(t) for t in doc['fitted_on'])
    return register_model_version(
        conn, ModelType.FANTASY, doc['version_name'], code_sha=current_code_sha(),
        configuration={'params': doc['params'], 'saves': doc['saves'], 'input_sha256': doc['input_sha256'],
                       'horizon_days': HORIZON.days,
                       'source_digests': {n: hashlib.sha256((root / n).read_bytes()).hexdigest()
                                          for n in ('fantasy.py', 'fantasy_snapshots.py', 'availability.py')}},
        training_window=(start, end), notes=doc['notes'])


def _pl_lines(conn):
    """Every finished Premier League player line since HISTORY_SEASON, oldest first."""
    return cached_rows(conn, 'fantasy_pl_lines', f"""
        select {WEEK.format('f.kickoff')} as part, f.fixture_id, f.kickoff, f.season, fp.team_id,
               f.home_team_id, f.home_goals, f.away_goals, fp.player_id, fp.minutes, fp.started,
               fp.position, fp.role, coalesce(fp.goals, 0) as goals, coalesce(fp.assists, 0) as assists,
               coalesce(fp.shots_on, 0) as shots_on, coalesce(fp.key_passes, 0) as key_passes,
               coalesce(fp.saves, 0) as saves, coalesce(fp.penalties_saved, 0) as penalties_saved,
               coalesce(fp.yellow_cards, 0) as yellow, coalesce(fp.red_cards, 0) as red,
               coalesce(fp.tackles, 0), coalesce(fp.blocks, 0), coalesce(fp.interceptions, 0),
               coalesce(fp.dribbles_won, 0), coalesce(fp.passes, 0), coalesce(fp.passes_accurate, 0),
               coalesce(fp.shots, 0), coalesce(fp.fouls_committed, 0), coalesce(fp.penalties_committed, 0),
               p.home_xg::float8, p.away_xg::float8
        from fixture_players fp join fixtures f using (fixture_id)
        left join fixture_predictions p on p.fixture_id = f.fixture_id
        where f.league_id = %s and f.season >= %s and f.status_short = any(%s) and f.home_goals is not null""",
        [PL, HISTORY_SEASON, list(config.FINISHED_STATUSES)], order_by='kickoff, fixture_id, player_id')


EXTRA_STATS = ('tackles', 'blocks', 'interceptions', 'dribbles_won', 'passes', 'passes_accurate', 'shots',
               'fouls', 'penalties_committed')


class History:
    """League history before now, arranged as fantasy.player_features and the benchmarks need it.
    lines: _pl_lines() rows; the trailing v1.2 columns (EXTRA_STATS, home / away xG) may be absent."""

    def __init__(self, lines):
        matches = defaultdict(lambda: defaultdict(dict))     # team -> fixture -> player -> line
        self.kickoffs, self.season_of, self.lam_against = {}, {}, {}
        counts = defaultdict(Counter)
        for (fid, kickoff, season, team, home, hg, ag, pid, minutes, started, position, role,
             goals, assists, shots_on, key_passes, saves, pens, yellow, red, *extra) in lines:
            stats = dict(zip(EXTRA_STATS, extra))
            matches[team][fid][pid] = dict(minutes=minutes, started=bool(started), role=role, goals=goals,
                                           assists=assists, shots_on=shots_on, key_passes=key_passes,
                                           saves=saves, pens=pens, yellow=yellow, red=red,
                                           conceded=ag if team == home else hg,
                                           base_bps=fm.bps('M', minutes, key_passes=key_passes, shots_on=shots_on,
                                                           **stats)['base'],
                                           cbit=sum(stats.get(k) or 0 for k in ('tackles', 'blocks', 'interceptions')))
            if len(extra) > len(EXTRA_STATS):
                hx, ax = extra[len(EXTRA_STATS):len(EXTRA_STATS) + 2]
                self.lam_against[(fid, team)] = ax if team == home else hx
            self.kickoffs[fid], self.season_of[fid] = kickoff, season
            if minutes > 0 and position in fm.GOAL_POINTS:
                counts[(pid, season)][position] += 1
        self.labels = defaultdict(dict)
        for (pid, season), c in counts.items():
            self.labels[pid][season] = c.most_common(1)[0][0]
        self.team_matches = {t: sorted(ms.items(), key=lambda m: (self.kickoffs[m[0]], m[0]))
                             for t, ms in matches.items()}
        self.appearances, self.points = defaultdict(list), {}
        season_pts = defaultdict(lambda: [0.0, 0])
        for team, ms in self.team_matches.items():
            for fid, players in ms:
                totals = tuple(sum(l[c] for l in players.values()) for c in ('goals', 'shots_on', 'assists', 'key_passes'))
                for pid, l in players.items():
                    if l['minutes'] <= 0:
                        continue
                    self.appearances[pid].append((self.kickoffs[fid], l['started'], l['minutes'], l['role'], l['goals'],
                                                  l['shots_on'], l['assists'], l['key_passes'], *totals,
                                                  l['base_bps'], l['yellow'], l['red'], l['cbit']))
                    pos = self.label(pid, self.season_of[fid])
                    pts = fm.actual_points(pos, l['minutes'], l['goals'], l['assists'], l['conceded'], l['saves'],
                                           l['pens'], l['yellow'], l['red'])['total']
                    self.points[(fid, pid)] = pts
                    sp = season_pts[(pid, self.season_of[fid])]
                    sp[0] += pts
                    sp[1] += 1
        self.season_pts = dict(season_pts)
        for v in self.appearances.values():
            v.sort(key=lambda a: a[0])

    def label(self, pid, season):
        seasons = self.labels.get(pid, {})
        for s in sorted(seasons, reverse=True):
            if s <= season:
                return seasons[s]
        return min(seasons.items())[1] if seasons else None

    def team_recent(self, team, kickoff):
        return [(fid, players) for fid, players in self.team_matches.get(team, [])
                if kickoff - fm.WINDOW <= self.kickoffs[fid] < kickoff]

    def save_history(self, team, kickoff):
        """[(team saves, lambda against)] over its league matches in fm.WINDOW before kickoff."""
        return [(sum(l['saves'] for l in players.values()), self.lam_against.get((fid, team)))
                for fid, players in self.team_recent(team, kickoff)]

    def benchmarks(self, pid, season, team_recent):
        cur, prev = self.season_pts.get((pid, season), (0.0, 0)), self.season_pts.get((pid, season - 1), (0.0, 0))
        last = team_recent[-BENCHMARK_MATCHES:]
        return {'ppg': cur[0] / cur[1] if cur[1] else prev[0] / prev[1] if prev[1] else 0.0,
                'recent5': sum(self.points.get((fid, pid), 0) for fid, _ in last) / len(last) if last else 0.0,
                'recent5_minutes': sum(p[pid]['minutes'] if pid in p else 0 for _, p in last) / len(last) if last else 0.0}


def fpl_dc_record(conn, season, now):
    """v1.4's input: {API player: (FPL minutes, FPL defensive-contribution count)} this season, from
    each gameweek's latest final (data_checked) FPL results captured before now."""
    return {api: (int(m), int(c)) for api, m, c in conn.execute(
        """select m.api_id, sum(r.minutes), sum(coalesce((r.stats->>'defensive_contribution')::int, 0))
           from (select distinct on (event_id) result_capture_id from fpl_result_captures
                 where season = %s and data_checked and captured_at < %s
                 order by event_id, captured_at desc, result_capture_id desc) c
           join fpl_player_results r using (result_capture_id)
           join fpl_id_map_current m on m.kind = 'player' and m.season = %s and m.fpl_id = r.fpl_player_id
           where m.api_id is not null and r.minutes > 0 group by m.api_id""", [season, now, season])}


def team_snapshot(history, fixture, team, is_home, injuries, doc, fpl_dc=None):
    """(predictions, inputs) for one side of an upcoming fixture, from history before kickoff.
    fpl_dc: fpl_dc_record() for v1.4."""
    fid, kickoff, season, home_xg, away_xg, latest_club = fixture
    lam_for, lam_against = (home_xg, away_xg) if is_home else (away_xg, home_xg)
    recent = history.team_recent(team, kickoff)
    team_recent = [{p: (l['started'], l['minutes']) for p, l in players.items()} for _, players in recent]
    players, bench = [], {}
    for pid in fm.universe(team, team_recent, latest_club):
        position = history.label(pid, season)
        if position is None:
            continue
        feats = fm.player_features(pid, kickoff, team_recent, [a for a in history.appearances[pid] if a[0] < kickoff])
        players.append(dict(feats, player_id=pid, position=position, injury=injuries.get(pid),
                            fpl_dc=(fpl_dc or {}).get(pid)))
        bench[str(pid)] = history.benchmarks(pid, season, recent)
    params = doc['params']
    factor = (fm.save_multiplier(history.save_history(team, kickoff), params['save_intercept'], params['save_slope'],
                                 params['save_pseudo_matches']) if 'save_pseudo_matches' in params else 1.0)
    comps = fm.predict_team(players, lam_for, lam_against, params, saves=doc['saves'], save_factor=factor)
    predictions = [dict(player_id=p['player_id'], position=p['position'],
                        **{k: round(v, 6) for k, v in c.items()}) for p, c in zip(players, comps)]
    inputs = {'lambda_for': lam_for, 'lambda_against': lam_against, 'is_home': is_home,
              'team_matches_in_window': len(recent),
              'availability': {str(p['player_id']): p['injury'] for p in players if p['injury']},
              'benchmarks': bench}
    return predictions, inputs


def make_snapshot(*, fixture_id, team_id, kickoff, version_id, captured_at, predictions, inputs):
    if captured_at.tzinfo is None:
        raise ValueError('Capture time must be timezone-aware')
    values = dict(fixture_id=fixture_id, team_id=team_id, model_version_id=version_id,
                  source='prospective' if captured_at < kickoff else 'late_observation',
                  **snapshot_times(captured_at=captured_at, effective_at=kickoff),
                  seconds_to_kickoff=(kickoff - captured_at).total_seconds(),
                  predictions=predictions, inputs=inputs)
    # Observation time alone is not a new state: identical inputs and outputs keep the first row
    identity = {k: v for k, v in values.items() if k not in ('captured_at', 'seconds_to_kickoff')}
    values['content_hash'] = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
                                                       allow_nan=False).encode()).hexdigest()
    values['predictions'] = json.dumps(predictions, allow_nan=False)
    values['inputs'] = json.dumps(inputs, allow_nan=False)
    return values


def append_snapshots(conn, rows):
    if not rows:
        return
    config.require_db_write('append fantasy snapshots')
    columns = tuple(rows[0])
    placeholders = ','.join(f'%({k})s' + ('::jsonb' if k in ('predictions', 'inputs') else '') for k in columns)
    with conn.cursor() as cur:
        cur.executemany(f'''INSERT INTO {TABLE} ({','.join(columns)}) VALUES ({placeholders})
            ON CONFLICT (fixture_id,team_id,model_version_id,source,content_hash) DO NOTHING''', rows)


def build(conn, fixture_ids=None, now=None, doc=None, horizon=HORIZON, history=None):
    """(params doc, [(fixture_id, team_id, kickoff, predictions, inputs)]) for every upcoming Premier
    League fixture within HORIZON (or only fixture_ids). SELECT only. history: a History to reuse
    when building several versions."""
    now = now or datetime.now(timezone.utc)
    doc = doc or load_params()
    upcoming = conn.execute(
        """select f.fixture_id, f.kickoff, f.season, f.home_team_id, f.away_team_id,
                  p.home_xg::float8, p.away_xg::float8
           from fixtures f join fixture_predictions p using (fixture_id)
           where f.league_id = %s and f.status_short in ('NS', 'TBD') and f.kickoff > %s and f.kickoff <= %s
             and p.home_xg is not null and p.away_xg is not null
             and (%s::int[] is null or f.fixture_id = any(%s::int[])) order by f.kickoff""",
        [PL, now, now + horizon, fixture_ids, fixture_ids]).fetchall()
    if not upcoming:
        return doc, []
    history = history or History(_pl_lines(conn))
    candidates = sorted({p for f in upcoming for t in f[3:5] for _, players in history.team_recent(t, f[1])
                         for p in players})
    latest_club = dict(conn.execute(
        """select distinct on (fp.player_id) fp.player_id, fp.team_id
           from fixture_players fp join fixtures f using (fixture_id)
           where fp.player_id = any(%s) and fp.minutes > 0 and f.kickoff < %s
           order by fp.player_id, f.kickoff desc, f.fixture_id desc""", [candidates, now]).fetchall())
    avail = availability.load(conn, [(f[0], f[1], f[3], f[4], True) for f in upcoming], observed_at=now)
    own = 'own_pseudo_90s' in doc['params'].get('dc', {})
    fpl_dc = {season: fpl_dc_record(conn, season, now) for season in {f[2] for f in upcoming}} if own else {}
    out = []
    for fid, kickoff, season, home, away, hx, ax in upcoming:
        for team, is_home in ((home, True), (away, False)):
            injuries = {p: fm.injury_type(v.get('evidence')) for p, v in avail.get((fid, team), {}).items()}
            predictions, inputs = team_snapshot(history, (fid, kickoff, season, hx, ax, latest_club),
                                                team, is_home, injuries, doc, fpl_dc.get(season))
            if predictions:
                out.append((fid, team, kickoff, predictions, inputs))
    return doc, out


def capture(conn, fixture_ids=None):
    """Build and append snapshots; commits. Returns the number of team-fixtures, or None when the
    table has not been created yet."""
    config.require_db_write('capture fantasy snapshots')
    if conn.execute('select to_regclass(%s)', [f'public.{TABLE}']).fetchone()[0] is None:
        log.warning('Fantasy snapshots: %s does not exist yet (apply db/migrations/'
                    '20260927_fantasy_fixture_snapshots.sql); skipped', TABLE)
        return None
    history, total = None, 0
    for path in CAPTURED:
        doc = load_params(path)
        history = history or History(_pl_lines(conn))
        doc, teams = build(conn, fixture_ids, doc=doc, history=history)
        if not teams:
            log.info('Fantasy snapshots: no upcoming Premier League fixtures')
            return 0
        version = register_version(conn, doc)
        captured = datetime.now(timezone.utc)
        append_snapshots(conn, [make_snapshot(fixture_id=fid, team_id=team, kickoff=kickoff, version_id=version,
                                              captured_at=captured, predictions=predictions, inputs=inputs)
                                for fid, team, kickoff, predictions, inputs in teams])
        conn.commit()
        log.info('Fantasy snapshots (%s): %d team-fixtures captured', doc['version_name'], len(teams))
        total += len(teams)
    return total


def capture_safely(conn, fixture_ids=None):
    """capture(), but a failure is logged and rolled back instead of failing the run: the
    snapshots are evaluation evidence, not part of the published pipeline."""
    try:
        return capture(conn, fixture_ids)
    except Exception:
        conn.rollback()
        log.exception('Fantasy snapshots failed (evidence only; the run continues)')
        return None
