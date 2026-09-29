from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import tempfile

from thecornerfc import config, export, fantasy as fm, fantasy_snapshots as fs

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'db/migrations/20260927_fantasy_fixture_snapshots.sql'
T0 = datetime(2026, 8, 1, 14, tzinfo=timezone.utc)
KICKOFF = T0 + timedelta(days=21)


def line(fid, week, team, home, pid, minutes, started, position='M', role='CM', goals=0, shots_on=0, hg=1, ag=0):
    # (fixture, kickoff, season, team, home team, home goals, away goals, player, minutes, started,
    #  position, role, goals, assists, shots_on, key_passes, saves, pens saved, yellow, red)
    return (fid, T0 + timedelta(days=7 * week), 2026, team, home, hg, ag, pid, minutes, started, position,
            role if started else None, goals, 0, shots_on, 1, 0, 0, 0, 0)


LINES = [line(1, 0, 10, 10, 7, 90, True, goals=1, shots_on=2), line(1, 0, 10, 10, 8, 20, False, 'F'),
         line(1, 0, 10, 10, 9, 90, True, 'G', 'GK'), line(1, 0, 20, 10, 30, 90, True),
         line(2, 1, 10, 20, 7, 70, True, hg=2, ag=2), line(2, 1, 10, 20, 8, 90, True, 'F', 'ST', 1, 3, hg=2, ag=2),
         line(2, 1, 10, 20, 9, 90, True, 'G', 'GK', hg=2, ag=2)]


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.h = fs.History(LINES)

    def test_live_features_match_the_backtest_function_on_the_same_history(self):
        recent = self.h.team_recent(10, KICKOFF)
        team_recent = [{p: (l['started'], l['minutes']) for p, l in players.items()} for _, players in recent]
        feats = fm.player_features(7, KICKOFF, team_recent, self.h.appearances[7])
        self.assertEqual(feats['history'], [(1, 0), (1, 0)])
        self.assertEqual((feats['start_n'], feats['start_min'], feats['g'], feats['sot']), (2, 160, 1, 2))
        self.assertEqual(feats['group'], 'CM')
        # his team's player-credited goals x his minutes / 90, summed over his appearances
        self.assertAlmostEqual(feats['tg'], 1 * 90 / 90 + 1 * 70 / 90)
        self.assertEqual(fm.player_features(8, KICKOFF, team_recent, self.h.appearances[8])['history'], [(1, 0), (0, 1)])

    def test_benchmarks_and_points_use_the_same_scoring_as_the_target(self):
        self.assertEqual(self.h.points[(1, 7)], fm.actual_points('M', 90, 1, 0, 0)['total'])
        self.assertEqual(self.h.points[(2, 9)], 2 - 1)      # GK conceded 2 away at team 20
        bench = self.h.benchmarks(9, 2026, self.h.team_recent(10, KICKOFF))
        self.assertAlmostEqual(bench['ppg'], (2 + 4 + 1) / 2)
        self.assertEqual(bench['recent5_minutes'], 90)

    def test_team_window_excludes_matches_at_or_after_kickoff(self):
        self.assertEqual([f for f, _ in self.h.team_recent(10, T0 + timedelta(days=7))], [1])

    def test_team_snapshot_allocates_the_match_models_goals_and_records_inputs(self):
        doc = fs.load_params()
        preds, inputs = fs.team_snapshot(self.h, (99, KICKOFF, 2026, 1.8, 0.9, {7: 10, 8: 10, 9: 10, 30: 20}),
                                         10, True, {8: fm.MISSING}, doc)
        self.assertEqual([p['player_id'] for p in preds], [7, 8, 9])
        self.assertAlmostEqual(sum(p['exp_goals'] for p in preds), 1.8 * (1 - doc['params']['own_goal_share']), places=5)
        self.assertEqual(inputs['availability'], {'8': fm.MISSING})
        self.assertEqual(set(inputs['benchmarks']), {'7', '8', '9'})
        self.assertGreater(preds[2]['save_points'], 0)
        flagged = {p['player_id']: p['p_start'] for p in preds}
        fit, _ = fs.team_snapshot(self.h, (99, KICKOFF, 2026, 1.8, 0.9, {7: 10, 8: 10, 9: 10}), 10, True, {}, doc)
        self.assertLess(flagged[8], {p['player_id']: p['p_start'] for p in fit}[8])

    def test_a_player_whose_last_appearance_was_elsewhere_is_left_out(self):
        preds, _ = fs.team_snapshot(self.h, (99, KICKOFF, 2026, 1.2, 1.2, {7: 10, 8: 55, 9: 10}), 10, True, {}, fs.load_params())
        self.assertEqual([p['player_id'] for p in preds], [7, 9])


class SnapshotTests(unittest.TestCase):
    def make(self, captured, preds=None):
        return fs.make_snapshot(fixture_id=1, team_id=2, kickoff=KICKOFF, version_id='mv_x', captured_at=captured,
                                predictions=preds or [{'player_id': 7, 'expected_points': 2.5}], inputs={'lambda_for': 1.2})

    def test_hash_ignores_observation_time_but_not_content(self):
        a, b = self.make(KICKOFF - timedelta(days=2)), self.make(KICKOFF - timedelta(hours=1))
        self.assertEqual(a['content_hash'], b['content_hash'])
        self.assertNotEqual(a['content_hash'], self.make(KICKOFF - timedelta(days=2), [{'player_id': 7, 'expected_points': 2.6}])['content_hash'])
        self.assertEqual(a['source'], 'prospective')
        self.assertEqual(self.make(KICKOFF)['source'], 'late_observation')
        self.assertEqual(json.loads(a['predictions'])[0]['player_id'], 7)
        with self.assertRaises(ValueError):
            self.make(KICKOFF.replace(tzinfo=None) - timedelta(days=1))

    def test_injury_type_reads_merged_evidence(self):
        self.assertEqual(fm.injury_type([{'type': 'Questionable'}, {'type': 'Missing Fixture', 'source': 'manual'}]), fm.MISSING)
        self.assertEqual(fm.injury_type([{'type': 'Questionable'}]), fm.DOUBTFUL)
        self.assertIsNone(fm.injury_type([]))


class CaptureTests(unittest.TestCase):
    def setUp(self):
        for name, val in [('READ_ONLY', False), ('GITHUB_ACTIONS', True)]:
            p = patch.object(config, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_missing_table_is_skipped_without_writing(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (None,)
        self.assertIsNone(fs.capture(conn))
        conn.commit.assert_not_called()

    def test_capture_safely_rolls_back_and_never_raises(self):
        conn = MagicMock()
        with patch.object(fs, 'capture', side_effect=RuntimeError('boom')), self.assertLogs(fs.log, 'ERROR'):
            self.assertIsNone(fs.capture_safely(conn))
        conn.rollback.assert_called_once()

    def test_read_only_mode_refuses(self):
        with patch.object(config, 'READ_ONLY', True), self.assertRaises(config.SafetyError):
            fs.capture(MagicMock())

    def test_each_run_snapshots_v1_1_and_v1_3_under_their_own_versions(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = ('fantasy_fixture_snapshots',)
        team = [(1, 10, KICKOFF, [{'player_id': 7, 'expected_points': 1.0}], {'availability': {}})]
        with patch.object(fs, 'History'), patch.object(fs, '_pl_lines'), \
                patch.object(fs, 'build', side_effect=lambda c, f, doc, history: (doc, team)) as build, \
                patch.object(fs, 'register_version', side_effect=lambda c, doc: 'mv_' + doc['version_name']), \
                patch.object(fs, 'append_snapshots') as append:
            self.assertEqual(fs.capture(conn), 2)
        self.assertEqual([c.kwargs['doc']['version_name'] for c in build.call_args_list], ['fantasy-v1.1', 'fantasy-v1.3'])
        self.assertIs(build.call_args_list[0].kwargs['history'], build.call_args_list[1].kwargs['history'])
        self.assertEqual([c.args[1][0]['model_version_id'] for c in append.call_args_list], ['mv_fantasy-v1.1', 'mv_fantasy-v1.3'])


class ParamsAndMigrationTests(unittest.TestCase):
    def test_frozen_params_are_v1_1_with_saves_and_availability(self):
        doc = fs.load_params()
        self.assertEqual(doc['version_name'], 'fantasy-v1.1')
        self.assertTrue(doc['saves'] and doc['params']['availability'])
        self.assertEqual(len(doc['params']['start_beta']), 7)

    def test_v1_3_is_v1_2_plus_defensive_contributions(self):
        v12 = fs.load_params(ROOT / 'thecornerfc/fantasy_params_v1_2.json')
        v13 = fs.load_params(ROOT / 'thecornerfc/fantasy_params_v1_3.json')
        self.assertEqual(v13['version_name'], 'fantasy-v1.3')
        self.assertEqual({k: v for k, v in v13['params'].items() if k != 'dc'}, v12['params'])
        self.assertEqual(v13['params']['dc']['thresholds'], {'D': 10, 'M': 12, 'F': 12})

    def test_p8_and_its_accrual_read_only_v1_1_rows(self):
        p8 = (ROOT / 'experiments/prospective/fantasy_p8.py').read_text()
        self.assertIn("MODEL = 'fantasy-v1.1'", p8)
        self.assertIn('mv.version_name = %s', p8)
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [('t',), (None, 0, 0, 0), (0,)]
        export._fantasy_progress(conn)
        self.assertTrue(all(c.args[1] == ['fantasy-v1.1'] for c in conn.execute.call_args_list[1:]))

    def test_migration_is_append_only_and_requires_a_fantasy_version(self):
        sql = MIGRATION.read_text()
        self.assertIn("RAISE EXCEPTION 'Fantasy snapshots are append only'", sql)
        self.assertIn("model_type='fantasy'", sql)
        self.assertIn('BEFORE TRUNCATE', sql)
        self.assertIn('UNIQUE(fixture_id,team_id,model_version_id,source,content_hash)', sql)


class FplTabExportTests(unittest.TestCase):
    def test_fpl_json_holds_the_findings_and_waits_for_the_snapshot_table(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (None,)
        with tempfile.TemporaryDirectory() as out:
            export.export_fantasy(conn, out)
            data = json.loads((Path(out) / 'fpl.json').read_text())
        results = json.loads(export.FANTASY_RESULTS.read_text())
        self.assertEqual([c['pass'] for c in data['criteria']],
                         [v for k, v in results['success'].items() if k[0].isdigit() and not k.endswith('detail')])
        self.assertEqual(data['overall']['model']['mae'], results['test']['overall']['model']['mae'])
        self.assertEqual(data['prospective']['state'], 'not_started')
        self.assertEqual(data['fpl_rows_available'], 0)

    def test_a_failure_skips_the_file_without_breaking_the_export(self):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError('db down')
        with tempfile.TemporaryDirectory() as out, self.assertLogs(export.log, 'ERROR'):
            export.export_fantasy(conn, out)
            self.assertFalse((Path(out) / 'fpl.json').exists())
        conn.rollback.assert_called_once()


class PredictionPayloadTests(unittest.TestCase):
    def pred(self, pid, position, **kw):
        mins = fm.minutes_expectation(0.9, 0.5, 85, 0.9, 20, 0.0)
        return dict(player_id=pid, position=position, **fm.expected_points(position, mins, kw.get('g', 0.3), 0.1, 1.2))

    def test_fpl_position_rescoring_doubles_and_order(self):
        k = KICKOFF
        fixtures = {1: (6, 10, 20, k), 2: (7, 30, 10, k + timedelta(days=7)), 3: (7, 10, 40, k + timedelta(days=9))}
        teams_out = [(fid, 10, k, [self.pred(7, 'F'), self.pred(8, 'M', g=0.05), self.pred(9, 'M')],
                      {'availability': {'8': fm.DOUBTFUL}}) for fid in (1, 2, 3)]
        doc = fs.load_params()
        # 9 isn't in FPL at the club (he has left it), so he's dropped
        out = export.fantasy_prediction_payload(fixtures, teams_out, doc, {7: ('M', 85, 'a', None), 8: ('M', 50, 'd', 75)},
                                                {7: 'Striker', 8: 'Mid', 9: 'Gone'}, {10: ['Home FC', 'HOM']}, source='fpl')
        self.assertEqual([g['id'] for g in out['gameweeks']], [6, 7])
        players = [dict(zip(out['fields'], r)) for r in out['players']]
        self.assertEqual([p['player'] for p in players], [7, 8])      # most total points first
        self.assertEqual((players[0]['fpl_position'], players[0]['price']), ('M', 85))
        self.assertEqual(players[1]['availability'], fm.DOUBTFUL)
        cells = [dict(zip(out['cell_fields'], c)) for c in out['cells'][0]]
        self.assertEqual([c['gw'] for c in cells], [0, 1, 1])         # a double gameweek keeps both matches
        self.assertEqual([c['opponent'] for c in cells], [20, 30, 40])
        # scored as FPL's MID: 5 per goal, 1 per clean sheet, not FWD's 4 and 0
        self.assertAlmostEqual(cells[0]['xp'], round(self.pred(7, 'M')['expected_points'], 2), places=2)
        self.assertGreater(cells[0]['xp'], round(self.pred(7, 'F')['expected_points'], 2))

    def test_prediction_export_failure_is_skipped(self):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError('db down')
        with tempfile.TemporaryDirectory() as out, self.assertLogs(export.log, 'ERROR'):
            export.export_fantasy_predictions(conn, out)
            self.assertFalse((Path(out) / 'fpl_predictions.json').exists())


if __name__ == '__main__':
    unittest.main()
