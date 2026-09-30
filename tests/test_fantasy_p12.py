"""P12's evaluator (experiments/prospective/fantasy_p12.py) on synthetic snapshots: no database."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('fantasy_p12', ROOT / 'experiments/prospective/fantasy_p12.py')
p12 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p12)

KICKOFF = datetime(2026, 10, 10, 14, tzinfo=timezone.utc)


def pred(pid, p_play, p_start=None, minutes=60.0):
    return {'player_id': pid, 'p_play': p_play, 'p_start': p_start if p_start is not None else p_play * .9,
            'exp_minutes': minutes}


def snap(version, preds, inputs, fid=1, round_name='Regular Season - 7', captured=KICKOFF - timedelta(hours=3)):
    return (fid, 10, captured, captured, KICKOFF, preds, inputs, version, 2026, round_name)


class P12Tests(unittest.TestCase):
    def data(self):
        fpl = {'7': {'status': 'i', 'chance': 0, 'news': 'Knee injury - Unknown return date', 'available': 0.0},
               '8': {'status': 'd', 'chance': 75, 'news': 'Knock - 75% chance of playing', 'available': 0.75}}
        snaps = [snap(p12.OLD, [pred(7, .8), pred(8, .9), pred(9, .9)], {'availability': {'9': 'Missing Fixture'}}),
                 snap(p12.NEW, [pred(7, 0.0), pred(8, .675), pred(9, .0)], {'fpl_availability': fpl, 'availability': {}})]
        lines = [(1, 10, 8, 90, True)]           # 7 and 9 didn't play; 8 started
        return snaps, lines, [(2026, 'Regular Season - 7', KICKOFF)]

    def test_rows_pair_versions_and_bucket_by_source(self):
        rows = {r['bucket']: r for r in p12.build(*self.data())}
        self.assertEqual(set(rows), {'no_date', 'doubtful_75', 'api_missing'})
        self.assertFalse(rows['no_date']['played'])
        self.assertTrue(rows['doubtful_75']['played'] and rows['doubtful_75']['started'])
        self.assertTrue(rows['no_date']['flagged'] and not rows['api_missing']['flagged'])

    def test_buckets_and_dates(self):
        k = KICKOFF
        self.assertEqual(p12.bucket({'status': 'i', 'chance': 0, 'news': 'Expected back 17 Oct', 'available': 0.0}, None, k),
                         'dated_before')
        self.assertEqual(p12.bucket({'status': 's', 'chance': 0, 'news': 'Suspended until 03 Oct', 'available': 1.0}, None, k),
                         'dated_after')
        self.assertEqual(p12.bucket({'status': 'd', 'chance': 75, 'news': '', 'available': 1.0}, None, k), 'doubtful_later')
        self.assertEqual(p12.bucket({'status': 'd', 'chance': 25, 'news': '', 'available': .25}, 'Questionable', k), 'both')
        self.assertIsNone(p12.bucket(None, None, k))

    def test_analysis_and_refit_small_buckets_keep_v1_6(self):
        res = p12.analyse(p12.build(*self.data()))
        self.assertLess(res['play_flagged']['diff'], 0)             # 0 for the injured non-player beats 0.8
        self.assertEqual(res['buckets']['no_date']['fitted_factor'], 0.0)   # under MIN_BUCKET: v1.6's value
        self.assertEqual((p12.TARGET_ROUNDS, p12.TARGET_FLAGGED, p12.MIN_BUCKET), (6, 300, 30))


if __name__ == '__main__':
    unittest.main()
