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


def rows(fid, base=(0.5, 0.3, 0.2), a18=(0.6, 0.25, 0.15)):
    return [[fid, 'base', *base, BEFORE, BEFORE], [fid, 'a18', *a18, BEFORE, BEFORE]]


class PairsTest(unittest.TestCase):
    def test_both_models_rows_make_a_pair_whichever_was_live(self):
        doc = {'fixtures': [[1, KICK, 2, 1], [2, '2026-11-08T15:00:00+00:00', 1, 1], [3, KICK, 0, 0]],
               'challenger': rows(1) + rows(2) + rows(3)[:1], 'switches': [['2026-11-05T10:00:00+00:00', 'a18']]}
        got, excluded = p18.pairs(doc)
        self.assertEqual([(y, live) for _, y, _, live in got], [(0, 'base'), (1, 'a18')])
        self.assertEqual(got[0][2], {'base': (0.5, 0.3, 0.2), 'a18': (0.6, 0.25, 0.15)})
        self.assertEqual(excluded, {'missing_a_model_before_kickoff': 1})

    def test_the_difference_is_a18_minus_base(self):
        out = p18.record({'fixtures': [[1, KICK, 2, 1]], 'challenger': rows(1), 'switches': []})
        track = out['changes']['MC-0029']
        self.assertEqual(track['n'], 1)
        self.assertAlmostEqual(-track['gain'], -math.log(0.6) + math.log(0.5))
        self.assertEqual(out['live_counts'], {'base': 1, 'a18': 0})

    def test_it_counts_from_the_day_after_the_release(self):
        self.assertEqual(p18.START, '2026-10-15')


class RunnerTest(unittest.TestCase):
    def test_one_document_holds_the_three_protocols(self):
        p16, p17 = runner.p16, runner.p17
        release = p16.record(None, {}, {}, environment='production', generated_at='t')
        out = runner.together(p17.combined(release, p17.record(None, {})), p18.record({'fixtures': [], 'challenger': [], 'switches': []}))
        self.assertEqual(out['protocol'], 'P16, P17 and P18')
        self.assertIn('MC-0029', out['changes'])
        self.assertNotIn('MC-0029', out['not_run'])
        self.assertEqual(out['comparisons'], {'P16': 1, 'P17': 13, 'P18': 1})
        ids = sorted(c['id'] for c in model_changes.load())
        self.assertEqual(sorted(set(out['changes']) | set(out['not_run'])), ids)
        json.dumps(out, allow_nan=False)

    def test_the_scores_give_log_loss_and_right_results_beside_the_other_model(self):
        mine = [(0.6, 0.2, 0.2), (0.2, 0.5, 0.3)]
        theirs = [(0.3, 0.3, 0.4), (0.5, 0.25, 0.25)]
        out = runner.scores({'MC-0018': (mine, theirs, [0, 1]), 'MC-0003': ([], [], [])})
        self.assertEqual(set(out), {'MC-0018'})          # nothing to score, nothing written
        s = out['MC-0018']
        self.assertEqual(s['n'], 2)
        self.assertAlmostEqual(s['log_loss'], -(math.log(0.6) + math.log(0.5)) / 2)
        self.assertAlmostEqual(s['against_log_loss'], -(math.log(0.3) + math.log(0.25)) / 2)
        self.assertEqual((s['right'], s['against_right']), (1.0, 0.0))
        json.dumps(out, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
