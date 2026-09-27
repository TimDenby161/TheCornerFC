import importlib.util
import unittest
from datetime import datetime,timezone
from thecornerfc import predictions as p

AVAILABLE=all(importlib.util.find_spec(m) for m in ('numpy','scipy'))
if AVAILABLE:
    import numpy as np
    from experiments.lineup_value.run import scores,shift,select_snapshots
    from experiments.lineup_value.weight_sensitivity import probs

@unittest.skipUnless(AVAILABLE,'Install offline experiment requirements')
class LineupExperimentTests(unittest.TestCase):
    def test_removal_and_readdition_reproduces_probabilities(self):
        lines=[[70,65,72,80],[68,63,70,73]]
        margin=.3+shift(lines)
        hx,ax=p.project(1.4,1.1,margin)
        actual,restored=scores([margin-shift(lines),hx,ax],lines)
        np.testing.assert_allclose(actual,p.outcome_probabilities(hx,ax)[:3],atol=1e-13)
        self.assertAlmostEqual(restored,margin)

    def test_small_goal_rate_product_is_not_clamped_twice(self):
        hx,ax=.02,2.
        got,margin=scores([hx-ax,hx,ax],None)
        np.testing.assert_allclose(got,p.outcome_probabilities(hx,ax)[:3],atol=1e-13)
        self.assertAlmostEqual(margin,hx-ax)

    def test_gk_ablation_only_changes_keeper_margin(self):
        lines=[[80,60,65,70],[60,60,65,70]]
        self.assertEqual(shift(lines),0)
        self.assertAlmostEqual(shift(lines,.005),.1)
        self.assertEqual(shift([[80,None,65,70],[60,60,65,70]],.005),0)

    def test_cutoff_uses_database_creation_and_one_capture_per_fixture(self):
        def row(cap,created,source='prospective'):
            return [1,'2026-09-26T12:00:00+00:00',39,1,0,source,cap,created]
        early=row('2026-09-26T09:00:00+00:00','2026-09-26T09:01:00+00:00')
        late_insert=row('2026-09-26T10:00:00+00:00','2026-09-26T11:01:00+00:00')
        late=row('2026-09-26T11:30:00+00:00','2026-09-26T11:31:00+00:00')
        self.assertEqual(select_snapshots([early,late_insert,late],1),[early])
        self.assertEqual(select_snapshots([early,late_insert,late],0),[late])
        self.assertEqual(select_snapshots([early],24),[])

    def test_unit_multiplier_matches_production_line_weights(self):
        base=[.2,1.5,1.2];lines=[['80','70','66','71'],['60','65','69','64']]
        np.testing.assert_allclose(probs(base,lines,1.),scores(base,lines)[0],atol=1e-13)
        np.testing.assert_allclose(probs(base,lines,0.),scores(base,None)[0],atol=1e-13)

if __name__=='__main__':unittest.main()
