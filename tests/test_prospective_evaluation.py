"""Prospective shadow evaluator: reproduction, component ablations, timing rules and market consensus."""
import unittest
from datetime import datetime,timedelta,timezone
from experiments.prospective import evaluate as e
from thecornerfc.models import predictions as p

KICKOFF=datetime(2026,10,3,15,tzinfo=timezone.utc)


def snapshot(**over):
    inputs={'home_match_rank':820.,'away_match_rank':790.,'home_current_rank':830.,'away_current_rank':785.,
            'home_lt_algo':805.,'away_lt_algo':797.5,'home_records':[(1.6,1.0),(1.2,1.4)],'away_records':[(1.1,1.3)],
            'league_home_goals':1.45,'league_away_goals':1.15,'home_missing':.12,'away_missing':None,
            'sides':[.1,-.05,.02,.01,1.4,1.1],'predicted_lines':[[70,68,66,72],[65,64,63,61]]}
    inputs.update(over.pop('inputs',{}))
    out=p.predict_match(inputs['home_match_rank'],inputs['away_match_rank'],inputs['home_records'],inputs['away_records'],
                        inputs['league_home_goals'],inputs['league_away_goals'],39,.12,0.,inputs['sides'],inputs['predicted_lines'])
    s={'fixture_id':1,'league_id':39,'source':'prospective','kickoff':KICKOFF,'effective_at':KICKOFF,
       'captured_at':KICKOFF-timedelta(hours=2),'created_at':KICKOFF-timedelta(hours=2),
       'model_reference_at':KICKOFF-timedelta(hours=2),'p_home':out[3],'p_draw':out[4],'p_away':out[5],'inputs':inputs}
    s.update(over);return s


class ProspectiveEvaluationTests(unittest.TestCase):
    def test_snapshot_reproduction_and_availability_ablation(self):
        s=snapshot()
        self.assertTrue(e.reproduces(s))
        self.assertFalse(e.reproduces(dict(s,p_home=s['p_home']+1e-4,p_draw=s['p_draw']-1e-4)))
        on,off=e.rescore(s),e.rescore(s,missing=False)
        self.assertNotEqual(on,off)
        self.assertEqual(off,e.rescore(snapshot(inputs={'home_missing':None}),missing=True))

    def test_production_year_weight_reproduces_match_rank(self):
        for days in (0,10,200,400):
            self.assertAlmostEqual(e.year_rank(830,805,days,p.MATCH_RANK_NOW_YEAR),p.match_rank(830,805,days))
        self.assertAlmostEqual(e.year_rank(830,None,100,.4),830)

    def test_snapshot_selection_respects_kickoff_and_source(self):
        early=snapshot(created_at=KICKOFF-timedelta(days=9),captured_at=KICKOFF-timedelta(days=9),model_reference_at=KICKOFF-timedelta(days=9))
        late=snapshot(created_at=KICKOFF-timedelta(minutes=5))
        after=snapshot(created_at=KICKOFF+timedelta(minutes=1))
        recon=snapshot(source='reconstruction',created_at=KICKOFF-timedelta(minutes=1))
        self.assertIs(e.latest_before_kickoff([early,late,after,recon])[1],late)
        self.assertIs(e.earliest_ahead([early,late],7)[1],early)
        self.assertEqual(e.earliest_ahead([late],7),{})

    def test_market_consensus_ignores_prices_inserted_after_cutoff(self):
        cut=KICKOFF-timedelta(hours=1)
        def o(book,sel,odds,minutes):
            t=cut+timedelta(minutes=minutes);return {'bookmaker_id':book,'selection':sel,'odds':odds,'captured_at':t,'created_at':t}
        odds=[o(1,'Home',2.,-30),o(1,'Draw',3.5,-30),o(1,'Away',4.,-30),o(1,'Home',1.5,10),
              o(2,'Home',2.2,-5),o(2,'Draw',3.4,-5)]       # book 2 incomplete; book 1's later price is after cutoff
        raw=[1/2.,1/3.5,1/4.];total=sum(raw)
        for got,want in zip(e.consensus(odds,cut),[x/total for x in raw]):self.assertAlmostEqual(got,want)
        self.assertIsNone(e.consensus(odds,cut-timedelta(hours=1)))

    def test_every_protocol_has_a_target_and_comparison(self):
        self.assertEqual(set(e.TARGETS),set(e.COMPARISONS))
        self.assertIn(str(p.MATCH_RANK_NOW_YEAR),[str(y) for y in e.P7_GRID])


if __name__=='__main__':unittest.main()
