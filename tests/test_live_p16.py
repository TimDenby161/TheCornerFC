"""P16's release tracker (experiments/prospective/live_p16.py): the parts that need no database."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('live_p16', ROOT / 'experiments/prospective/live_p16.py')
p16 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p16)


class LiveP16Test(unittest.TestCase):
    def test_pins_and_settings_hold(self):
        p16.check_pins()

    def test_only_a_version_that_changed_ranking_alone_is_the_release(self):
        before = dict(p16.BEFORE)
        changed = {**before, 'ranking.py': 'a' * 64}
        also = {**changed, 'predictions.py': 'b' * 64}
        versions = [['mv_old', before], ['mv_new', changed], ['mv_later', also], ['mv_empty', None]]
        self.assertEqual(p16.released(versions), {'mv_new'})

    def test_before_is_the_fingerprint_table_at_registration(self):
        # the release changes ranking.py, and a later player-rank change may change player_ratings.py
        # (amendment 16), so only the others must still match the table
        from tests.test_model_fingerprints import FINGERPRINTS
        for name, want in p16.BEFORE.items():
            if name != 'ranking.py' and name not in p16.MAY_ALSO_DIFFER:
                self.assertEqual(FINGERPRINTS[name][1], want, name)

    def test_a_version_that_also_changes_the_player_ranks_is_still_the_release(self):
        before = dict(p16.BEFORE)
        released = {**before, 'ranking.py': 'a' * 64}
        players = {**released, 'player_ratings.py': 'c' * 64}
        without_the_rank = {**before, 'player_ratings.py': 'c' * 64}
        versions = [['mv_rel', released], ['mv_players', players], ['mv_old_rank', without_the_rank]]
        self.assertEqual(p16.released(versions), {'mv_rel', 'mv_players'})

    def test_record_before_any_match_has_the_tracker_shape(self):
        out = p16.record(None, {'latest_snapshot_from_the_old_version': 3}, {}, environment='production', generated_at='t')
        self.assertEqual(out['protocol'], 'P16')
        self.assertEqual(list(out['changes']), ['MC-0028'])
        self.assertEqual(out['changes']['MC-0028']['n'], 0)
        self.assertIsNone(out['changes']['MC-0028']['verdict'])
        self.assertNotIn('MC-0028', out['not_run'])
        self.assertIn('MC-0016', out['not_run'])
        json.dumps(out, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
