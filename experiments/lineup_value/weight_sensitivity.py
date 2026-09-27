"""Outfield line-weight sensitivity on the frozen lineup rows. Writes experiment artifacts only.

The main ablation keeps production outfield weights (0.005 per rating point). A perfect-XI
gain measured at a fixed, possibly mis-scaled weight is not an information upper bound, so
scale the outfield weights, choose the multiplier on validation log loss, and report test once.
"""
from pathlib import Path
import gzip,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
from thecornerfc import predictions as p
from experiments.player_club_strength.run import interval
ROOT=Path(__file__).parent
MULTIPLIERS=[0.,.5,1.,1.5,2.,3.,4.]

def probs(base,lines,k):
    margin=base[0]+sum(k*.005*(float(h)-float(a)) for h,a in zip(lines[0][1:],lines[1][1:]))
    product=base[1]*base[2];hx=(margin+(margin*margin+4*product)**.5)/2
    return p.outcome_probabilities(hx,product/hx)[:3]

def losses(rows,variant,k):
    return np.array([-np.log(max(probs(r['base'],r[variant],k)[r['y']],1e-15)) for r in rows])

def main():
    rows=json.loads(gzip.decompress(Path('.cache/lineup_value_rows.json.gz').read_bytes()))['historical']
    val=[r for r in rows if r['date']<'2024-07-01'];test=[r for r in rows if r['date']>='2024-07-01']
    weeks=[r['week'] for r in test];none=losses(test,'pred',0.)
    out={'multipliers':MULTIPLIERS,'validation_n':len(val),'test_n':len(test),'variants':{}}
    for variant in ('pred','actual'):
        v={k:float(losses(val,variant,k).mean()) for k in MULTIPLIERS}
        t={k:losses(test,variant,k) for k in MULTIPLIERS}
        chosen=min(MULTIPLIERS,key=v.get)
        out['variants'][variant]={'validation_log_loss':{str(k):x for k,x in v.items()},
            'test_log_loss':{str(k):float(x.mean()) for k,x in t.items()},'validation_selected_multiplier':chosen,
            'selected_test_delta_vs_none':float((t[chosen]-none).mean()),'selected_test_ci':interval(t[chosen]-none,weeks,2000),
            'selected_test_delta_vs_production':float((t[chosen]-t[1.]).mean()),'selected_vs_production_ci':interval(t[chosen]-t[1.],weeks,2000)}
    (ROOT/'weight_sensitivity.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:{x:v[x] for x in ('validation_selected_multiplier','selected_test_delta_vs_none','selected_test_delta_vs_production')} for k,v in out['variants'].items()}))

if __name__=='__main__':main()
