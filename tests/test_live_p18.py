"""P18, the stored challenger against the live model (experiments/prospective/live_p18.py), and the
runner that stores P16, P17 and P18 together (live_tracking.py): the parts that need no database."""
import importlib.util
import json
import math
import unittest
from pathlib import Path

from thecornerfc.evidence import model_changes

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'experiments/prospective/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p18, runner = load('live_p18'), load('live_tracking')
KICK = '2026-11-01T15:00:00+00:00'
BEFORE = '2026-11-01T09:00:00+00:00'


def snapshot(fid, model, probs=(0.5, 0.3, 0.2), created=BEFORE):
    return {'fixture_id': fid, 'captured_at': created, 'created_at': created, 'p_home': probs[0], 'p_draw': probs[1],
            'p_away': probs[2], 'match_model': model}


class PairsTest(unittest.TestCase):
    def test_the_live_snapshot_and_the_other_model_s_row_make_a_pair(self):
        doc = {'fixtures': [[1, KICK, 2, 1], [2, KICK, 1, 1], [3, KICK, 0, 0], [4, KICK, 0, 1]],
               'snapshots': [snapshot(1, 'base'), snapshot(2, 'a18'), snapshot(3, None)],
               'challenger': [[1, 'a18', 0.6, 0.25, 0.15, BEFORE, BEFORE], [2, 'base', 0.4, 0.35, 0.25, BEFORE, BEFORE]]}
        rows, excluded = p18.pairs(doc)
        self.assertEqual([(y, live) for _, y, _, live in rows], [(0, 'base'), (1, 'a18')])
        self.assertEqual(rows[0][2], {'base': (0.5, 0.3, 0.2), 'a18': (0.6, 0.25, 0.15)})
        self.assertEqual(excluded, {'no_snapshot_before_kickoff': 1, 'snapshot_from_before_the_two_models': 1,
                                    'no_challenger_row_before_kickoff': 0})

    def test_a_missing_challenger_row_is_left_out_and_counted(self):
        doc = {'fixtures': [[1, KICK, 2, 1]], 'snapshots': [snapshot(1, 'base')], 'challenger': []}
        rows, excluded = p18.pairs(doc)
        self.assertEqual(rows, [])
        self.assertEqual(excluded['no_challenger_row_before_kickoff'], 1)

    def test_the_difference_is_a18_minus_base(self):
        doc = {'fixtures': [[1, KICK, 2, 1]], 'snapshots': [snapshot(1, 'base')],
               'challenger': [[1, 'a18', 0.6, 0.25, 0.15, BEFORE, BEFORE]]}
        out = p18.record(doc)
        track = out['changes']['MC-0029']
        self.assertEqual(track['n'], 1)
        self.assertAlmostEqual(-track['gain'], -math.log(0.6) + math.log(0.5))
        self.assertEqual(out['live_counts'], {'base': 1, 'a18': 0})

    def test_nothing_is_read_before_the_release_sets_its_start(self):
        self.assertIsNone(p18.START)
        self.assertEqual(p18.extract(None), {'fixtures': [], 'snapshots': [], 'challenger': []})


class RunnerTest(unittest.TestCase):
    def test_one_document_holds_the_three_protocols(self):
        p16, p17 = runner.p16, runner.p17
        release = p16.record(None, {}, {}, environment='production', generated_at='t')
        out = runner.together(p17.combined(release, p17.record(None, {})), p18.record({'fixtures': [], 'snapshots': [], 'challenger': []}))
        self.assertEqual(out['protocol'], 'P16, P17 and P18')
        self.assertIn('MC-0029', out['changes'])
        self.assertNotIn('MC-0029', out['not_run'])
        self.assertEqual(out['comparisons'], {'P16': 1, 'P17': 13, 'P18': 1})
        ids = sorted(c['id'] for c in model_changes.load())
        self.assertEqual(sorted(set(out['changes']) | set(out['not_run'])), ids)
        json.dumps(out, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
