from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from thecornerfc import config, fantasy as fm, fantasy_snapshots as fs

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


class ParamsAndMigrationTests(unittest.TestCase):
    def test_frozen_params_are_v1_1_with_saves_and_availability(self):
        doc = fs.load_params()
        self.assertEqual(doc['version_name'], 'fantasy-v1.1')
        self.assertTrue(doc['saves'] and doc['params']['availability'])
        self.assertEqual(len(doc['params']['start_beta']), 7)

    def test_migration_is_append_only_and_requires_a_fantasy_version(self):
        sql = MIGRATION.read_text()
        self.assertIn("RAISE EXCEPTION 'Fantasy snapshots are append only'", sql)
        self.assertIn("model_type='fantasy'", sql)
        self.assertIn('BEFORE TRUNCATE', sql)
        self.assertIn('UNIQUE(fixture_id,team_id,model_version_id,source,content_hash)', sql)


if __name__ == '__main__':
    unittest.main()
