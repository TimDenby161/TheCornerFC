"""P19, the ideas of 30 October 2026 on live matches (experiments/prospective/live_p19.py), and its
place in the Live tracking document (live_tracking.py): the parts that need no database."""
import importlib.util
import json
import unittest
from pathlib import Path

from thecornerfc.evidence import model_changes

ROOT = Path(__file__).resolve().parents[1]

try:
    import numpy as np
except ImportError:                       # the jobs' test run has no numpy
    np = None


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'experiments/prospective/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load('live_tracking')
p19 = runner.p19


class RegistrationTest(unittest.TestCase):
    def test_it_counts_from_the_day_after_registration(self):
        self.assertEqual(p19.START, '2026-10-31')

    def test_two_ideas_each_against_what_it_improves_on(self):
        self.assertEqual(p19.AGAINST, {'MC-0040': 'MC-0018', 'MC-0041': 'production'})
        self.assertEqual(set(p19.SETTINGS), set(p19.AGAINST))

    def test_its_files_are_as_registered(self):
        p19.check_pins()

    def test_an_empty_record_has_both_tracks(self):
        out = p19.record(None, {})
        self.assertEqual(out['n'], 0)
        self.assertEqual(set(out['changes']), {'MC-0040', 'MC-0041'})
        json.dumps(out, allow_nan=False)


@unittest.skipIf(np is None, 'needs numpy')
class AfterEuropeTest(unittest.TestCase):
    class Data:
        def __init__(self, rows):
            # (home, away, league, is_league, day number)
            self.n = len(rows)
            self.home = [r[0] for r in rows]
            self.away = [r[1] for r in rows]
            self.league = [r[2] for r in rows]
            self.is_league = [r[3] for r in rows]
            self.ordinal = [r[4] for r in rows]

    def test_only_a_league_match_five_days_or_more_after_europe(self):
        data = self.Data([
            (1, 2, 2, False, 100),        # 1 plays in the Champions League
            (1, 3, 39, True, 105),        # five days later in the league: counts
            (4, 1, 3, False, 110),        # 1 in the Europa League (away)
            (5, 1, 39, True, 113),        # three days later: too soon
            (6, 7, 3, False, 120),        # 6 in Europe
            (6, 8, 45, False, 127),       # then a domestic cup: not a league match
        ])
        flags = p19.after_europe(data, 5, (2, 3, 848))
        self.assertEqual(flags.tolist(), [[False, False], [True, False], [False, False],
                                          [False, False], [False, False], [False, False]])


class RunnerTest(unittest.TestCase):
    def test_one_document_holds_the_four_protocols(self):
        p16, p17, p18 = runner.p16, runner.p17, runner.p18
        release = p16.record(None, {}, {}, environment='production', generated_at='t')
        out = runner.with_p19(
            runner.together(p17.combined(release, p17.record(None, {})),
                            p18.record({'fixtures': [], 'challenger': [], 'switches': []})),
            p19.record(None, {}))
        self.assertEqual(out['protocol'], 'P16, P17, P18 and P19')
        self.assertEqual(out['comparisons'], {'P16': 1, 'P17': 13, 'P18': 1, 'P19': 2})
        for cid in ('MC-0040', 'MC-0041'):
            self.assertIn(cid, out['changes'])
            self.assertNotIn(cid, out['not_run'])
        ids = sorted(c['id'] for c in model_changes.load())
        self.assertEqual(sorted(set(out['changes']) | set(out['not_run'])), ids)
        json.dumps(out, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
