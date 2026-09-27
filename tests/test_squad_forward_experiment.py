"""Forward-label boundaries, roster turnover and residualization checks."""
import importlib.util
from pathlib import Path
import unittest

AVAILABLE=all(importlib.util.find_spec(m) for m in ('numpy','scipy'))
if AVAILABLE:
    spec=importlib.util.spec_from_file_location('squad_forward',Path(__file__).resolve().parents[1]/'experiments/squad_forward/run.py')
    e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)


@unittest.skipUnless(AVAILABLE,'Install offline experiment requirements')
class SquadForwardTests(unittest.TestCase):
    def test_forward_labels_are_purged_at_both_boundaries(self):
        self.assertEqual(e.split_for('2023-05-01','2023-06-30'),'train')
        self.assertIsNone(e.split_for('2023-05-01','2023-07-01'))
        self.assertEqual(e.split_for('2024-05-01','2024-06-30'),'validation')
        self.assertIsNone(e.split_for('2024-05-01','2024-07-01'))
        self.assertEqual(e.split_for('2024-07-01','2025-01-01'),'test')
        self.assertIsNone(e.split_for('2021-12-01','2022-05-01'))

    def test_turnover_measures_changed_minutes_not_match_count(self):
        self.assertAlmostEqual(e.turnover([{1:90,2:90}],[{1:45,2:45}]),0.)
        self.assertAlmostEqual(e.turnover([{3:90,4:90}],[{1:90,2:90}]),1.)
        self.assertAlmostEqual(e.turnover([{1:90,3:90}],[{1:90,2:90}]),.5)
        self.assertIsNone(e.turnover([], [{1:90}]))

    def test_raw_and_residual_augmentations_are_equivalent(self):
        np=e.np;rng=np.random.default_rng(5)
        x=np.column_stack((np.ones(300),rng.normal(size=(300,2))))
        raw=10*x[:,1]+rng.normal(size=300)
        y=3*x[:,1]+2*raw+rng.normal(size=300)
        train=np.arange(300)<150;val=(np.arange(300)>=150)&(np.arange(300)<220);test=np.arange(300)>=220
        residual=raw-x@e.ols(x,raw,train)
        a=e.augmentation(x,raw,y,train,val,train|val,test)
        b=e.augmentation(x,residual,y,train,val,train|val,test)
        np.testing.assert_allclose(a[0],b[0],atol=1e-9)
        self.assertEqual(a[1],b[1])

if __name__=='__main__':unittest.main()
