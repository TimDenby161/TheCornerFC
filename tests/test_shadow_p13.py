"""P13's evaluator (experiments/prospective/shadow_p13.py): the parts that need no database."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('shadow_p13', ROOT / 'experiments/prospective/shadow_p13.py')
p13 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p13)

KICKOFF = '2026-10-17T14:00:00+00:00'


def snap(fixture_id, captured, created=None, **more):
    return {'fixture_id': fixture_id, 'captured_at': captured, 'created_at': created or captured, **more}


class P13Tests(unittest.TestCase):
    def test_the_latest_snapshot_before_kickoff_is_chosen(self):
        chosen = p13.latest_before_kickoff(
            [snap(1, '2026-10-16T22:00:00+00:00', tag='night'), snap(1, '2026-10-17T13:10:00+00:00', tag='late'),
             snap(1, '2026-10-17T14:00:00+00:00', tag='at kickoff'), snap(1, '2026-10-17T15:00:00+00:00', tag='after')],
            {1: KICKOFF})
        self.assertEqual(chosen[1]['tag'], 'late')

    def test_a_snapshot_inserted_after_kickoff_does_not_count(self):
        chosen = p13.latest_before_kickoff(
            [snap(1, '2026-10-17T13:00:00+00:00', created='2026-10-17T14:30:00+00:00')], {1: KICKOFF})
        self.assertEqual(chosen, {})

    def test_a_fixture_outside_the_population_is_ignored(self):
        self.assertEqual(p13.latest_before_kickoff([snap(2, '2026-10-16T22:00:00+00:00')], {1: KICKOFF}), {})

    def test_retraining_dates_are_each_july_and_january(self):
        self.assertEqual(p13.blocks_until('2026-10-20'), ['2026-07-01'])
        self.assertEqual(p13.blocks_until('2027-01-01'), ['2026-07-01', '2027-01-01'])
        self.assertEqual(p13.blocks_until('2027-08-15'), ['2026-07-01', '2027-01-01', '2027-07-01'])

    def test_the_registered_target_follows_from_the_planning_figures(self):
        self.assertAlmostEqual(p13.fixtures_required(0.097), 9400, delta=100)
        self.assertEqual(p13.fixtures_required(0.001), p13.REESTIMATE_AT)

    def test_the_candidate_files_are_as_registered(self):
        p13.check_pins()

    def test_the_accrual_check_reads_no_outcome_and_no_odds(self):
        for sql in (p13.ACCRUAL_SQL, p13.SNAPSHOT_SQL, p13.FETCHED_SQL):
            self.assertNotIn('odds', sql.lower())
        self.assertNotIn('goals', p13.ACCRUAL_SQL.replace('ft_home is not null', '').replace('ft_away is not null', ''))
        self.assertIn('odds', p13.SKIP_QUERIES)

    def test_the_protocol_is_registered(self):
        text = (ROOT / 'experiments/prospective/PROTOCOLS.md').read_text()
        self.assertIn('## P13: Shadow corrections to the match predictions', text)
        self.assertIn(f'{p13.TARGET:,} fixtures', text)
        self.assertIn(p13.START, text)


if __name__ == '__main__':
    unittest.main()
