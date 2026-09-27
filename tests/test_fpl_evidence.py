from argparse import Namespace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, patch
import uuid

from thecornerfc import config, evaluation, fpl
from thecornerfc.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'db/migrations/20260927_fpl_evidence.sql'
NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
BOOTSTRAP = {
    'events': [
        {'id': 5, 'name': 'Gameweek 5', 'deadline_time': '2026-09-19T10:00:00Z', 'finished': True, 'data_checked': True},
        {'id': 6, 'name': 'Gameweek 6', 'deadline_time': '2026-09-26T10:00:00Z', 'finished': False, 'data_checked': False},
        {'id': 1, 'name': 'Gameweek 1', 'deadline_time': '2026-08-21T17:30:00Z', 'finished': True, 'data_checked': True}],
    'element_types': [{'id': 1, 'singular_name_short': 'GKP'}, {'id': 3, 'singular_name_short': 'MID'}],
    'teams': [{'id': 1, 'code': 3, 'name': 'Arsenal', 'short_name': 'ARS'},
              {'id': 13, 'code': 43, 'name': 'Man City', 'short_name': 'MCI'}],
    'elements': [
        {'id': 20, 'code': 223340, 'first_name': 'Bukayo', 'second_name': 'Saka', 'web_name': 'Saka', 'team': 1,
         'element_type': 3, 'now_cost': 101, 'status': 'd', 'chance_of_playing_this_round': 75,
         'chance_of_playing_next_round': 75, 'news': 'Knock - 75% chance of playing',
         'news_added': '2026-09-24T09:15:00.123456Z', 'selected_by_percent': '40.1'},
        {'id': 1, 'code': 9, 'first_name': 'David', 'second_name': 'Raya Martín', 'web_name': 'Raya', 'team': 1,
         'element_type': 1, 'now_cost': 55, 'status': 'a', 'chance_of_playing_this_round': None,
         'chance_of_playing_next_round': None, 'news': '', 'news_added': None}]}
FIXTURES = [{'id': 51, 'event': 6, 'kickoff_time': '2026-09-26T11:30:00Z', 'team_h': 1, 'team_a': 13,
             'team_h_difficulty': 4, 'team_a_difficulty': 4, 'team_h_score': None, 'finished': False},
            {'id': 99, 'event': None, 'kickoff_time': None, 'team_h': 13, 'team_a': 1}]


class ParsingTests(unittest.TestCase):
    def test_gameweeks_season_and_target_deadline(self):
        weeks = fpl.gameweeks(BOOTSTRAP)
        self.assertEqual([w['event_id'] for w in weeks], [1, 5, 6])
        self.assertEqual(fpl.season_of(weeks), 2026)
        self.assertEqual(fpl.target_gameweek(weeks, NOW)['event_id'], 6)
        self.assertIsNone(fpl.target_gameweek(weeks, weeks[-1]['deadline']))  # a deadline at "now" has passed
        self.assertEqual(fpl.season_of([{'deadline': datetime(2027, 1, 1, tzinfo=timezone.utc)}]), 2026)

    def test_player_states_preserve_price_position_team_and_availability_only(self):
        saka, raya = fpl.player_states(BOOTSTRAP)[::-1]
        self.assertEqual(raya['fpl_player_id'], 1)
        self.assertEqual((saka['price_tenths'], saka['position'], saka['fpl_team_id'], saka['status'],
                          saka['chance_next_round'], saka['news']), (101, 'MID', 1, 'd', 75, 'Knock - 75% chance of playing'))
        self.assertEqual(saka['news_added'], '2026-09-24T09:15:00.123456+00:00')
        self.assertIsNone(raya['news'])            # empty news is no news
        self.assertNotIn('selected_by_percent', saka)

    def test_known_fixtures_keep_schedule_not_scores(self):
        rows = fpl.known_fixtures(FIXTURES)
        self.assertEqual(rows[0], {'fpl_fixture_id': 51, 'event_id': 6, 'kickoff': '2026-09-26T11:30:00+00:00',
                                   'fpl_team_h': 1, 'fpl_team_a': 13, 'difficulty_h': 4, 'difficulty_a': 4})
        self.assertIsNone(rows[1]['event_id'])     # unscheduled fixture is kept, not dropped
        finished = [dict(FIXTURES[0], team_h_score=2, finished=True), FIXTURES[1]]
        self.assertEqual(fpl.known_fixtures(finished), rows)

    def test_result_rows_keep_points_minutes_and_per_fixture_explain(self):
        live = {'elements': [{'id': 20, 'stats': {'minutes': 90, 'total_points': 12, 'bonus': 3},
                              'explain': [{'fixture': 51, 'stats': [{'identifier': 'bonus', 'points': 3, 'value': 3}]}]},
                             {'id': 7, 'stats': {'minutes': 0, 'total_points': 0}},
                             {'id': 8, 'stats': {}}]}
        rows = fpl.result_rows(live)
        self.assertEqual([(r['fpl_player_id'], r['total_points'], r['minutes']) for r in rows], [(7, 0, 0), (20, 12, 90)])
        self.assertEqual(rows[1]['explain'][0]['fixture'], 51)


class CaptureTests(unittest.TestCase):
    def capture(self, captured=NOW, players=None):
        week = fpl.target_gameweek(fpl.gameweeks(BOOTSTRAP), NOW)
        return fpl.make_capture(2026, week, fpl.known_fixtures(FIXTURES),
                                players or fpl.player_states(BOOTSTRAP), captured)

    def test_capture_timing_and_content_identity(self):
        first = self.capture()
        self.assertEqual((first['source'], first['event_id'], first['seconds_to_deadline']), ('prospective', 6, 22 * 3600))
        self.assertEqual(first['effective_at'], '2026-09-26T10:00:00+00:00')
        self.assertEqual(first['content_hash'], self.capture(NOW + timedelta(hours=1))['content_hash'])
        cheaper = [dict(p, price_tenths=p['price_tenths'] - 1) for p in fpl.player_states(BOOTSTRAP)]
        self.assertNotEqual(first['content_hash'], self.capture(players=cheaper)['content_hash'])
        self.assertEqual(self.capture(NOW + timedelta(days=2))['source'], 'late_observation')
        with self.assertRaises(ValueError):
            self.capture(datetime(2026, 9, 25))

    def test_store_capture_skips_unchanged_state_and_writes_player_rows(self):
        capture = self.capture()
        conn = MagicMock()
        with patch.object(config, 'require_db_write'):
            conn.execute.return_value.fetchone.return_value = (capture['content_hash'],)
            self.assertIsNone(fpl.store_capture(conn, capture))
            conn.execute.return_value.fetchone.side_effect = [None, (41,)]
            self.assertEqual(fpl.store_capture(conn, capture), 41)
        rows = conn.cursor.return_value.__enter__.return_value.executemany.call_args[0][1]
        self.assertEqual([r[:2] for r in rows], [(41, 1), (41, 20)])
        self.assertEqual(rows[1][-5:], ('d', 75, 75, 'Knock - 75% chance of playing', '2026-09-24T09:15:00.123456+00:00'))

    def test_results_due_until_final_and_empty_answer_not_stored(self):
        conn = MagicMock()
        conn.execute.return_value.__iter__.return_value = iter([(1,)])
        due = fpl.results_due(conn, 2026, fpl.gameweeks(BOOTSTRAP))
        self.assertEqual([w['event_id'] for w in due], [5])
        self.assertEqual([w['event_id'] for w in fpl.results_due(conn, 2026, fpl.gameweeks(BOOTSTRAP), [1])], [1])
        with patch.object(config, 'require_db_write'):
            self.assertIsNone(fpl.store_result_capture(Mock(), fpl.make_result_capture(2026, due[0], [], NOW)))

    def test_access_is_off_by_default_and_cli_refuses(self):
        with patch.object(config, 'FPL_CAPTURE_ENABLED', False):
            with self.assertRaisesRegex(config.SafetyError, 'no published licence'):
                config.require_fpl_access('test')
            with self.assertRaises(config.SafetyError), patch.object(config, 'READ_ONLY', False), \
                    patch.object(config, 'GITHUB_ACTIONS', True):
                main(['fpl', 'capture'])
        with patch.object(config, 'FPL_CAPTURE_ENABLED', True), patch.object(config, 'NO_API', True):
            with self.assertRaises(config.SafetyError):
                fpl.FplClient()


class MappingTests(unittest.TestCase):
    CLUBS = [(42, 'Arsenal', 'ARS'), (50, 'Manchester City', 'MAC'), (47, 'Tottenham', 'TOT')]

    def test_normalise_folds_accents_and_punctuation(self):
        self.assertEqual(fpl.normalise("Martin Ødegaard"), 'martin odegaard')
        self.assertEqual(fpl.normalise("Nott'm Forest"), 'nottm forest')
        self.assertEqual(fpl.normalise('B. Saka'), 'b saka')

    def test_team_alias_short_code_and_override(self):
        none = {}
        self.assertEqual(fpl.match_team({'name': 'Man City', 'short_name': 'MCI'}, self.CLUBS, none)[:2], (50, 'name'))
        self.assertEqual(fpl.match_team({'name': 'Spurs', 'short_name': 'XXX'}, self.CLUBS, none)[:2], (47, 'name'))
        self.assertEqual(fpl.match_team({'name': 'Gunners', 'short_name': 'ARS'}, self.CLUBS, none)[:2], (42, 'short_code'))
        self.assertEqual(fpl.match_team({'name': 'Coventry', 'short_name': 'COV'}, self.CLUBS, none)[:2], (None, 'unmatched'))
        self.assertEqual(fpl.match_team({'code': 94, 'name': 'Coventry'}, self.CLUBS, {94: 1346})[:2], (1346, 'manual'))

    def test_player_rules_in_order_and_never_guess_between_two(self):
        squad = [(1, 'B. Saka', 'Bukayo Ayoyinka', 'T. M. Saka'), (2, 'Gabriel Magalhães', 'Gabriel', 'dos Santos Magalhães'),
                 (3, 'D. Raya', 'David', 'Raya Martín'), (4, 'Gabriel Jesus', 'Gabriel Fernando', 'de Jesus'),
                 (5, 'Martin Ødegaard', 'Martin', 'Ødegaard')]
        match = lambda first, second, web, code=0: fpl.match_player(
            {'code': code, 'first_name': first, 'second_name': second, 'web_name': web}, squad, {})
        self.assertEqual(match('David', 'Raya Martín', 'Raya')[:2], (3, 'full_name'))
        self.assertEqual(match('Bukayo', 'Saka', 'Saka')[:2], (1, 'initial_surname'))
        self.assertEqual(match('Martin', 'Ødegaard', 'Ødegaard')[:2], (5, 'full_name'))
        self.assertEqual(match('Gabriel', 'dos Santos Magalhães', 'Gabriel')[:2], (2, 'full_name'))
        self.assertEqual(match('Gabriel', 'Jesus', 'G.Jesus')[:2], (4, 'name_tokens'))
        found = fpl.match_player({'first_name': 'X', 'second_name': 'Y', 'web_name': 'Gabriel'},
                                 squad + [(6, 'Gabriel', 'Gabriel', 'Martinelli'), (7, 'Gabriel', 'Gabriel', 'Silva')], {})
        self.assertEqual(found[:2], (None, 'ambiguous'))
        self.assertEqual(found[2], {'candidates': [6, 7], 'at': 'web_name'})
        self.assertEqual(match('Nobody', 'Here', 'Here')[:2], (None, 'unmatched'))
        self.assertEqual(match('Nobody', 'Here', 'Here', code=77)[:2], (None, 'unmatched'))
        self.assertEqual(fpl.match_player({'code': 77}, [], {77: 12})[:2], (12, 'manual'))

    def test_mapping_appends_only_changes(self):
        rows = fpl.mapping_rows('player', 2026, [(20, 223340, 1, 'initial_surname', {}), (1, 9, None, 'unmatched', {})], NOW)
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [('player', 2026, 20, rows[0]['content_hash'])]
        self.assertEqual(fpl._store_mappings(conn, rows), 1)
        stored = conn.cursor.return_value.__enter__.return_value.executemany.call_args[0][1]
        self.assertEqual([r['fpl_id'] for r in stored], [1])

    def test_overrides_file_is_valid(self):
        self.assertEqual(fpl.load_overrides(), {'teams': {}, 'players': {}})


class PredictionSnapshotTests(unittest.TestCase):
    DEADLINE = datetime(2026, 9, 26, 10, tzinfo=timezone.utc)

    def make(self, **kwargs):
        args = dict(season=2026, event_id=6, deadline=self.DEADLINE, version_id='mv_x', captured_at=NOW,
                    source='prospective', input_capture_id=41, inputs={'capture_id': 41},
                    predictions=[{'fpl_player_id': 20, 'expected_points': 6.1}, {'fpl_player_id': 1, 'expected_points': 3.0,
                                                                                'start_probability': .95}])
        return fpl.make_prediction_snapshot(**{**args, **kwargs})

    def test_valid_snapshot_is_sorted_and_retry_stable(self):
        row = self.make()
        self.assertEqual([p['fpl_player_id'] for p in json.loads(row['predictions'])], [1, 20])
        self.assertEqual(row['content_hash'], self.make(captured_at=NOW + timedelta(minutes=5))['content_hash'])
        self.assertNotEqual(row['content_hash'], self.make(input_capture_id=42)['content_hash'])
        self.assertEqual(self.make(captured_at=self.DEADLINE)['source'], 'late_observation')
        self.assertEqual(self.make(source='reconstruction', input_capture_id=None)['source'], 'reconstruction')

    def test_rejects_invalid_predictions(self):
        for kwargs in ({'source': 'live'}, {'input_capture_id': None}, {'predictions': []},
                       {'predictions': [{'fpl_player_id': 1}]},
                       {'predictions': [{'fpl_player_id': 1, 'expected_points': float('nan')}]},
                       {'predictions': [{'fpl_player_id': 1, 'expected_points': True}]},
                       {'predictions': [{'fpl_player_id': '1', 'expected_points': 2}]},
                       {'predictions': [{'fpl_player_id': 1, 'expected_points': 2}, {'fpl_player_id': 1, 'expected_points': 3}]},
                       {'captured_at': datetime(2026, 9, 25)}, {'inputs': []}):
            with self.assertRaises(ValueError, msg=kwargs):
                self.make(**kwargs)


class FantasyEvaluationTests(unittest.TestCase):
    def test_metrics(self):
        rows = [{'snapshot_id': 1, 'expected_points': 6., 'actual_points': 2},
                {'snapshot_id': 1, 'expected_points': 2., 'actual_points': 2}]
        m = evaluation.fantasy_metrics(rows)
        self.assertEqual((m['n'], m['snapshots'], m['mae'], m['bias'], m['mean_actual']), (2, 1, 2., 2., 2.))
        self.assertAlmostEqual(m['rmse'], 8 ** .5)
        self.assertIsNone(evaluation.fantasy_metrics([])['rmse'])

    def test_load_counts_unlabelled_snapshots_and_missing_players(self):
        base = dict(season=2026, event_id=6, model_version_id='mv_x', input_capture_id=41, captured_at=NOW,
                    effective_at=NOW + timedelta(hours=3), seconds_to_deadline=3 * 3600., result_captured_at=NOW)
        snaps = [dict(base, snapshot_id=1, result_capture_id=9,
                      predictions=[{'fpl_player_id': 20, 'expected_points': 6.1}, {'fpl_player_id': 21, 'expected_points': 1}]),
                 dict(base, snapshot_id=2, event_id=7, result_capture_id=None, predictions=[])]
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [(9, 20, 12)]
        args = Namespace(as_of=NOW, start=NOW, end=NOW, hours_before=0)
        with patch.object(evaluation, 'query', return_value=snaps):
            rows, coverage = evaluation.load_fantasy(conn, args)
        self.assertEqual([(r['fpl_player_id'], r['expected_points'], r['actual_points']) for r in rows], [(20, 6.1, 12)])
        self.assertEqual(coverage, {'selected_snapshots': 2, 'snapshots_without_final_points': 1,
                                    'predictions_without_player_result': 1})


class SchemaTests(unittest.TestCase):
    def test_schema_contains_migration(self):
        self.assertIn(MIGRATION.read_text(), (ROOT / 'db/schema.sql').read_text())


@unittest.skipUnless(os.getenv('MODEL_VERSION_TEST_DSN'), 'Requires an explicitly supplied disposable PostgreSQL test database')
class FplPostgresTests(unittest.TestCase):
    def test_migration_guards_and_writers(self):
        import psycopg
        from thecornerfc.model_versions import register_model_version
        with psycopg.connect(os.environ['MODEL_VERSION_TEST_DSN']) as conn:
            try:
                schema = 'fpl_test_' + uuid.uuid4().hex
                conn.execute(f'CREATE SCHEMA {schema}')
                conn.execute(f'SET LOCAL search_path TO {schema}')
                conn.execute((MIGRATION.parent / '20260926_model_versions.sql').read_text())
                conn.execute(MIGRATION.read_text())
                conn.execute(MIGRATION.read_text())
                now = datetime.now(timezone.utc)
                week = {'event_id': 6, 'deadline': now + timedelta(days=1)}
                with patch.object(config, 'READ_ONLY', False), patch.object(config, 'GITHUB_ACTIONS', True):
                    fpl._record_gameweeks(conn, 2026, [dict(week, name='GW6')] * 2, now)
                    capture = fpl.make_capture(2026, week, fpl.known_fixtures(FIXTURES), fpl.player_states(BOOTSTRAP), now)
                    capture_id = fpl.store_capture(conn, capture)
                    self.assertIsNone(fpl.store_capture(conn, capture))
                    past = fpl.make_capture(2026, {'event_id': 5, 'deadline': now - timedelta(hours=1)}, [], [], now)
                    past['source'] = 'prospective'           # a writer bug; the trigger still downgrades it
                    past_id = fpl.store_capture(conn, past)
                    fpl._store_mappings(conn, fpl.mapping_rows('team', 2026, [(1, 3, 42, 'name', {})], now))
                    week5 = {'event_id': 5, 'finished': True, 'data_checked': True}
                    result_id = fpl.store_result_capture(conn, fpl.make_result_capture(
                        2026, week5, fpl.result_rows({'elements': [{'id': 20, 'stats': {'total_points': 12, 'minutes': 90}}]}), now))
                    fantasy = register_model_version(conn, 'fantasy', 'baseline')
                    match = register_model_version(conn, 'match', 'baseline')
                    snap = lambda **kw: fpl.make_prediction_snapshot(**{**dict(
                        season=2026, event_id=6, deadline=week['deadline'], version_id=fantasy, captured_at=now,
                        source='prospective', input_capture_id=capture_id, inputs={},
                        predictions=[{'fpl_player_id': 20, 'expected_points': 5.5}]), **kw})
                    fpl.append_prediction_snapshots(conn, [snap(), snap()])
                self.assertEqual(conn.execute('SELECT count(*) FROM fpl_gameweeks').fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT count(*) FROM fpl_player_states WHERE capture_id=%s', [capture_id]).fetchone()[0], 2)
                self.assertEqual(conn.execute('SELECT source FROM fpl_captures WHERE capture_id=%s', [past_id]).fetchone()[0], 'late_observation')
                self.assertEqual(conn.execute('SELECT deadline FROM fpl_gameweek_deadlines').fetchone()[0], week['deadline'])
                self.assertEqual(conn.execute('SELECT api_id FROM fpl_id_map_current').fetchone()[0], 42)
                self.assertEqual(conn.execute('SELECT total_points FROM fpl_player_results WHERE result_capture_id=%s',
                                              [result_id]).fetchone()[0], 12)
                self.assertEqual(conn.execute('SELECT count(*), min(source) FROM fantasy_prediction_snapshots').fetchone(), (1, 'prospective'))
                failures = [
                    ('UPDATE fpl_player_states SET price_tenths=1', 'append only'),
                    ('DELETE FROM fpl_captures', 'append only'),
                    ('TRUNCATE fpl_player_results CASCADE', 'append only'),
                    ('UPDATE fantasy_prediction_snapshots SET source=%s', 'append only', ['reconstruction'])]
                for sql, message, *params in failures:
                    with self.assertRaisesRegex(psycopg.Error, message), conn.transaction():
                        conn.execute(sql, *params)
                with patch.object(config, 'READ_ONLY', False), patch.object(config, 'GITHUB_ACTIONS', True):
                    for kwargs, message in (({'version_id': match}, 'fantasy model version'),
                                            ({'captured_at': now - timedelta(minutes=5)}, 'observed after'),
                                            ({'input_capture_id': past_id}, 'different gameweek')):
                        with self.assertRaisesRegex(psycopg.Error, message), conn.transaction():
                            fpl.append_prediction_snapshots(conn, [snap(**kwargs, predictions=[{'fpl_player_id': 1, 'expected_points': 1}])])
            finally:
                conn.rollback()


if __name__ == '__main__':
    unittest.main()
