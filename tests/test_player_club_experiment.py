"""Chronology and cohort regression tests for the offline experiment."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('player_club_experiment',Path(__file__).resolve().parents[1]/'experiments/player_club_strength/run.py')
e=importlib.util.module_from_spec(spec)
HAS_EXPERIMENT_DEPS=all(importlib.util.find_spec(name) for name in ('numpy','scipy'))
if HAS_EXPERIMENT_DEPS:
    spec.loader.exec_module(e)


@unittest.skipUnless(HAS_EXPERIMENT_DEPS, 'Install offline experiment requirements to run these tests')
class PlayerClubExperimentTests(unittest.TestCase):
    def data(self):
        data={'fixtures':[], 'apps':[], 'players':[]}
        for team in (1,2):
            for n in range(11):
                p=team*100+n
                data['players'].append([p,str(p),'1995-01-01',75,'GK' if n==0 else 'ST',1000])
        for fid in range(1,15):
            date=f'2021-01-{fid:02d}' if fid<=12 else '2022-01-02'
            # Last two fixtures deliberately share kickoff.
            data['fixtures'].append([fid,date+' 12:00:00+00:00',39,2021,1,2,1,0,1000,990,950,940,1.,1.])
            for team in (1,2):
                for n in range(11):
                    data['apps'].append([fid,team,team*100+n,90,True,'G' if n==0 else 'F',
                                         'GK' if n==0 else 'ST',7.]+[0]*len(e.pr.STATS[3:]))
        return data

    def replay(self,data):
        norms={p:{k:(0.,1.) for k in weights} for p,weights in e.pr.WEIGHTS.items()}
        with patch.object(e,'temporal_norms',return_value=norms):
            return e.replay(data)

    def test_same_kickoff_outcomes_do_not_change_inputs(self):
        data=self.data();changed=copy.deepcopy(data)
        for row in changed['apps']:
            if row[0]==13:
                row[7]=10.;row[8]=5
        first=self.replay(data);second=self.replay(changed)
        self.assertTrue(first[0]);self.assertEqual(len(first[1]),2)
        self.assertEqual([r['values'] for r in first[0]],[r['values'] for r in second[0]])
        self.assertEqual([r['home'] for r in first[1]],[r['home'] for r in second[1]])
        self.assertNotEqual([r['performance'] for r in first[0]],[r['performance'] for r in second[0]])

    def test_absence_kept_as_zero_minutes(self):
        data=self.data()
        for a in data['apps']:
            if a[0]==13 and a[2]==110:a[2]=999
        rows,_,_,_=self.replay(data)
        absent=[r for r in rows if r['player']==110 and r['minutes']==0]
        self.assertEqual(len(absent),1)
        self.assertIsNone(absent[0]['performance'])

    def test_partial_lineup_does_not_create_false_absences(self):
        data=self.data()
        data['apps']=[a for a in data['apps'] if not(a[0]>=13 and a[2]==110)]
        rows,matches,_,_=self.replay(data)
        self.assertEqual(rows,[])
        self.assertEqual(matches,[])

    def test_residual_fit_does_not_use_test_ratings(self):
        rows=[{'position':p,'date':'2022-06-01','club':club,'values':[club/12,50,75]}
              for p in e.POSITIONS for club in (800,900,1000,1100)]
        other=copy.deepcopy(rows)
        for rr,rating in ((rows,50),(other,100)):
            rr.extend({'position':p,'date':'2025-06-01','club':1000,'values':[rating,50,75]}
                      for p in e.POSITIONS)
        self.assertEqual(e.add_residual(rows,[],[]),e.add_residual(other,[],[]))

if __name__=='__main__':unittest.main()
