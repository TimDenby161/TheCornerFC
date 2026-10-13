"""P15's live tracker (experiments/prospective/live_p15.py): the parts that need no database."""
import importlib.util
import math
import random
import unittest
from pathlib import Path

from thecornerfc.evidence import model_changes

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('live_p15', ROOT / 'experiments/prospective/live_p15.py')
p15 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p15)


def season(rng, mean, weeks=40, a_week=150, sd=0.08):
    """Per-match differences and their weeks for a run of weeks."""
    d = [rng.gauss(mean, sd) for _ in range(weeks * a_week)]
    w = [202642 + i // a_week for i in range(weeks * a_week)]
    return d, w


class JudgementTests(unittest.TestCase):
    def test_the_interval_is_wider_than_a_single_look_s_and_narrows_with_matches(self):
        rho = p15.mixture_rho(0.05)
        widths = [p15.half_width(n, 0.08, 0.05, rho) for n in (100, 500, 2000, 6200, 20000)]
        self.assertEqual(widths, sorted(widths, reverse=True))
        for n, w in zip((100, 500, 2000, 6200, 20000), widths):
            self.assertGreater(w, 1.96 * 0.08 / math.sqrt(n))        # the price of looking as often as you like
        self.assertEqual(p15.half_width(1, 0.08, 0.05, rho), math.inf)
        self.assertEqual(p15.half_width(500, 0.0, 0.05, rho), math.inf)
        self.assertGreater(p15.half_width(2000, 0.08, 0.05, rho, design=2.0), p15.half_width(2000, 0.08, 0.05, rho))

    def test_matches_that_come_in_weeks_never_narrow_it(self):
        self.assertEqual(p15.design_effect([1.0, -1.0, 0.5, -0.5], [10, 10, 10, 10], 0.0, 1.0, 40), 1.0)
        self.assertGreater(p15.design_effect([30.0, -30.0, 25.0, -25.0], [100, 100, 100, 100], 0.0, 1.0, 400), 1.0)

    def test_nothing_is_called_before_500_matches_and_8_weeks(self):
        self.assertIsNone(p15.verdict(-0.01, -0.002, 499, 20))
        self.assertIsNone(p15.verdict(-0.01, -0.002, 5000, 7))
        self.assertEqual(p15.verdict(-0.01, -0.002, 500, 8), 'better')
        self.assertEqual(p15.verdict(0.002, 0.01, 500, 8), 'worse')
        self.assertIsNone(p15.verdict(-0.004, 0.001, 5000, 30))

    def test_a_clear_improvement_is_called_and_the_call_stands(self):
        d, w = season(random.Random(1), -0.02, weeks=30)
        got = p15.track(d, w, 0.05 / 17)
        self.assertEqual((got['verdict'], got['ready']), ('better', True))
        self.assertGreaterEqual(got['called']['n'], p15.MINIMUM_MATCHES)
        self.assertEqual((got['n'], got['weeks'], len(got['series'])), (4500, 30, 30))
        self.assertLess(got['low'], got['gain'])
        # a bad later run can't take back a call the method has already allowed
        worse = p15.track(d + [0.5] * 3000, w + [202700] * 3000, 0.05 / 17)
        self.assertEqual((worse['verdict'], worse['called']), ('better', got['called']))
        self.assertFalse(worse['ready'])                # but it is not put forward while its gain is under the bar

    def test_a_proven_gain_under_the_bar_is_not_ready(self):
        d, w = season(random.Random(2), -0.001, weeks=40, a_week=2000, sd=0.02)
        got = p15.track(d, w, 0.05 / 17)
        self.assertEqual((got['verdict'], got['ready']), ('better', False))
        self.assertLess(got['gain'], p15.BAR)

    def test_no_matches_is_an_empty_record(self):
        got = p15.track([], [], 0.05 / 17)
        self.assertEqual((got['n'], got['verdict'], got['ready'], got['series']), (0, None, False, []))

    def test_looking_every_week_does_not_manufacture_improvements(self):
        # 300 candidates that change nothing, each watched for 40 weeks at the plain 5% level:
        # far fewer than 5% may ever be called either way, or the method would not be doing its job
        rng = random.Random(20261014)
        called = sum(p15.track(*season(rng, 0.0), 0.05)['verdict'] is not None for _ in range(300))
        self.assertLessEqual(called, 15)

    def test_a_real_improvement_of_the_planned_size_is_usually_found(self):
        rng = random.Random(20261015)
        found = sum(p15.track(*season(rng, -0.0035, weeks=80), 0.05 / 17)['verdict'] == 'better' for _ in range(40))
        self.assertGreaterEqual(found, 30)


class RegistrationTests(unittest.TestCase):
    def test_every_change_in_the_register_is_either_run_or_says_why_not(self):
        ids = [c['id'] for c in model_changes.load()]
        self.assertFalse(set(p15.CANDIDATES) & set(p15.NOT_RUN))
        self.assertEqual(sorted(set(p15.CANDIDATES) | set(p15.NOT_RUN)), ids)
        self.assertEqual(len(p15.CANDIDATES), 17)

    def test_the_register_says_which_changes_are_in_this_live_test(self):
        marked = {c['id'] for c in model_changes.load()
                  if any(e['type'] == 'live_test' and e['protocol'] == 'P15' for e in c['events'])}
        self.assertEqual(marked, set(p15.CANDIDATES))
        for c in model_changes.load():
            for e in c['events']:
                if e['type'] == 'live_test' and e['protocol'] == 'P15':
                    self.assertEqual((e['start'], e['target'], e['extra_time']), (p15.START, p15.PLANNED, True))

    def test_no_experiment_is_run_live_with_a_setting_it_did_not_fix(self):
        for cid, (_, setting, source) in p15.CANDIDATES.items():
            self.assertTrue((ROOT / source.split(':')[0]).exists(), f'{cid}: {source}')
        self.assertEqual(p15.CANDIDATES['MC-0016'][1], {'pull': 0.5, 'boost': 0.5, 'tau': 40.0})
        self.assertEqual(p15.CANDIDATES['MC-0007'][1], {'power': 1.10})

    def test_the_candidate_files_are_as_registered(self):
        p15.check_pins()

    def test_it_reads_no_odds_and_ties_after_90_minutes_count(self):
        self.assertNotIn('odds', p15.SNAPSHOT_SQL.lower())
        self.assertIn('odds', p15.SKIP_QUERIES)
        self.assertEqual(p15.STATUSES, ('FT', 'AET', 'PEN'))

    def test_the_protocol_is_registered(self):
        text = (ROOT / 'experiments/prospective/PROTOCOLS.md').read_text()
        self.assertIn('## P15: Every runnable change, scored on live matches and watched as it goes', text)
        self.assertIn(p15.START, text)
        self.assertIn('**Amendment 9 (2026-10-13)', text)
        self.assertIn('P13 and P14 are no longer blind', text)

    def test_its_workflow_runs_it_on_production_and_stores_one_document(self):
        text = (ROOT / '.github/workflows/live-tracking.yml').read_text()
        self.assertIn('python experiments/prospective/live_p15.py --store', text)
        self.assertIn('pip install -r experiments/prospective/requirements-live.txt', text)
        self.assertNotIn('-r requirements.txt -r', text)        # pip refuses a hashed file and an unhashed one together
        self.assertIn('group: db-sync', text)
        self.assertIn('THECORNERFC_NO_API: "true"', text)
        self.assertNotIn('API_FOOTBALL_KEY', text)


    def test_what_the_job_installs_is_pinned_by_hash_at_the_registered_versions(self):
        folder = ROOT / 'experiments/prospective'
        registered = dict(line.split('==') for line in (folder / 'requirements-p13.txt').read_text().split())
        lines = [l for l in (folder / 'requirements-live.txt').read_text().splitlines() if l and not l.startswith('#')]
        pins = dict(l.rstrip(' \\').split('==') for l in lines if '==' in l)
        for name, version in registered.items():
            self.assertEqual(pins.get(name), version, name)
        hashes = [l for l in lines if l.strip().startswith('--hash=sha256:')]
        self.assertEqual(len(hashes), len(pins))               # every package, the ones they pull in too
        for l in hashes:
            self.assertRegex(l.strip(), r'^--hash=sha256:[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
