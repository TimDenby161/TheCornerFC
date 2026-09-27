"""Sample-size planning for the prospective protocols. Uses only frozen historical rows; no outcomes
from the prospective period. Writes experiments/prospective/power.json."""
from collections import defaultdict
from pathlib import Path
import gzip,json,math,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
ROOT=Path(__file__).parent
Z_ALPHA,Z_POWER=1.959964,0.841621   # two-sided 5%, 80% power


def loss(p,y):return -math.log(max(p[y],1e-15))


def required(diffs,weeks,delta):
    """Fixtures needed to detect a mean paired difference of delta, inflated by the observed
    week-cluster design effect (variance of weekly sums relative to independent fixtures)."""
    n=len(diffs);mean=sum(diffs)/n;var=sum((d-mean)**2 for d in diffs)/(n-1)
    blocks=defaultdict(list)
    for d,w in zip(diffs,weeks):blocks[w].append(d-mean)
    clustered=sum(sum(b)**2 for b in blocks.values())/n
    deff=max(1.,clustered/var)
    return {'n_sample':n,'sd':math.sqrt(var),'design_effect':deff,'delta':delta,
            'fixtures_required':math.ceil(((Z_ALPHA+Z_POWER)*math.sqrt(var*deff)/delta)**2)}


def main():
    rows=json.loads(gzip.decompress(Path('.cache/lineup_value_rows.json.gz').read_bytes()))['historical']
    test=[r for r in rows if r['date']>='2024-07-01'];weeks=[r['week'] for r in test]
    def diff(a,b):return [loss(r['scores'][a][0],r['y'])-loss(r['scores'][b][0],r['y']) for r in test]
    out={'method':'normal approximation, two-sided alpha 0.05, power 0.8, week-cluster design effect from 2024-07 onward historical lineup rows',
         # Actual-vs-predicted XI is the closest historical analogue of P3's official-XI re-score.
         'P3_official_vs_predicted_XI':required(diff('actual','predicted'),weeks,.002),
         # Predicted-vs-none is the closest analogue of a small single-component ablation (P4, P7).
         'P4_P7_small_component_ablation':required(diff('predicted','none'),weeks,.002),
         'P6_market':'No historical timestamped odds. Target fixed at 2,000 fixtures, re-estimated once from blinded variance at 500 fixtures (see PROTOCOLS.md).'}
    (ROOT/'power.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
