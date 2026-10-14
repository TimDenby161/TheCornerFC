"""P17's tracker of the ideas on the live model (experiments/prospective/live_p17.py): the parts that
need no database."""
import importlib.util
import json
import unittest
from pathlib import Path

from thecornerfc.evidence import model_changes

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('live_p17', ROOT / 'experiments/prospective/live_p17.py')
p17 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p17)


class LiveP17Test(unittest.TestCase):
    def test_pins_hold(self):
        p17.check_pins()

    def test_every_change_is_tracked_by_p16_or_p17_or_says_why_not(self):
        # the changes recorded after P17 (MC-0029 on) are other protocols' to list
        ids = sorted(c['id'] for c in model_changes.load() if c['id'] <= 'MC-0028')
        tracked = set(p17.CANDIDATES) | {p17.p16.CHANGE}
        self.assertFalse(tracked & set(p17.NOT_RUN))
        self.assertEqual(sorted(tracked | set(p17.NOT_RUN)), ids)
        self.assertEqual(len(p17.CANDIDATES), 13)

    def test_each_candidate_keeps_the_setting_p15_registered(self):
        for cid, entry in p17.CANDIDATES.items():
            self.assertEqual(entry, p17.p15.CANDIDATES[cid])
        for cid in ('MC-0013', 'MC-0014', 'MC-0016', 'MC-0024'):
            self.assertEqual(p17.NOT_RUN[cid], p17.IN_PRODUCTION)

    def test_one_document_holds_the_release_and_the_ideas(self):
        release = p17.p16.record(None, {'latest_snapshot_from_the_old_version': 2}, {}, environment='production', generated_at='t')
        ideas = p17.record(None, {'latest_snapshot_from_the_old_version': 2})
        out = p17.combined(release, ideas)
        self.assertEqual(out['protocol'], 'P16 and P17')
        self.assertEqual(sorted(out['changes']), sorted({*p17.CANDIDATES, 'MC-0028'}))
        self.assertFalse(set(out['changes']) & set(out['not_run']))
        self.assertEqual(out['comparisons'], {'P16': 1, 'P17': 13})
        self.assertEqual(out['minimum'], {'matches': 500, 'weeks': 8})
        json.dumps(out, allow_nan=False)

    def test_its_workflow_runs_it_and_stores_one_document(self):
        text = (ROOT / '.github/workflows/live-tracking.yml').read_text()
        self.assertIn('python experiments/prospective/live_p17.py --store', text)
        self.assertNotIn('live_p16.py --store', text)


if __name__ == '__main__':
    unittest.main()
