"""Controlled, offline club-performance forecasts. Never mutates production data/models."""
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import json
import math
import pickle
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
from experiments.player_club_strength.run import interval, corr
from experiments.strength_weight.run import TIERS

ROOT=Path(__file__).parent
CODE_SHA=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
VAL='2023-07-01'; TEST='2024-07-01'
BASELINES=('baseline','current','blend','both')
MODELS=('club_only','raw_squad','residual_squad','history_only','history_raw','history_neutral')
TARGETS=('goal_difference','points','adjusted_goal_difference')
HORIZONS=(5,10,20)
SEED=20260927


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def turnover(recent,previous):
    a=Counter();b=Counter()
    for match in recent:a.update(match)
    for match in previous:b.update(match)
    sa,sb=sum(a.values()),sum(b.values())
    if not sa or not sb:return None
    return .5*sum(abs(a[p]/sa-b[p]/sb) for p in a.keys()|b.keys())


def split_for(anchor,end):
    if anchor<'2022-01-01':return None
    if anchor<VAL:return 'train' if end<VAL else None
    if anchor<TEST:return 'validation' if end<TEST else None
    return 'test'


def club_basis(row,name):
    c=(row['current']-1000)/100;l=(row['baseline']-1000)/100
    if name=='both':return [c,l,c*c,l*l,c*l]
    v=l if name=='baseline' else c if name=='current' else .6*c+.4*l
    return [v,v*v]


def build_rows():
    raw=gzip.decompress(Path('.cache/player_club_strength_inputs.json.gz').read_bytes())
    data=json.loads(raw);prior=json.loads(Path('experiments/player_club_strength/results.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=prior['input_sha256']:
        raise RuntimeError('Player replay source fingerprint mismatch')
    if sha('experiments/player_club_strength/run.py')!=prior['code_sha256']:
        raise RuntimeError('Player replay code fingerprint mismatch')
    with gzip.open('.cache/player_club_strength_replay.pkl.gz','rb') as handle:
        candidates,_,_,_,_=pickle.load(handle)  # Locally generated experiment cache only.
    grouped=defaultdict(list)
    for r in candidates:grouped[(r['team'],r['date'])].append(r)
    snapshots={};ambiguous=0
    for key,rr in grouped.items():
        if len({r['player'] for r in rr})!=len(rr):
            ambiguous+=1;continue
        if len(rr)<11 or not any(r['position']=='GK' for r in rr):continue
        w=np.array([r['controls'][7] for r in rr]);w/=w.sum()
        snapshots[key]={'raw':float(w@np.array([r['values'][0] for r in rr])),
                        'neutral':float(w@np.array([r['values'][2] for r in rr])),
                        'embedded':float(w@np.array([r['club']/1000 for r in rr])),
                        'embedded_squared':float(w@np.array([(r['club']/1000)**2 for r in rr])),
                        'eligible_players':len(rr)}
    del candidates,grouped
    membership_data=json.loads(gzip.decompress(Path('.cache/strength_weight_inputs.json.gz').read_bytes()))
    membership={(t,y):set(leagues) for t,y,leagues in membership_data['membership']}
    del membership_data
    fixtures=data['fixtures'];series=defaultdict(list);latest=defaultdict(list);minutes=defaultdict(dict)
    homegaps=defaultdict(list)
    for a in data['apps']:minutes[(a[0],a[1])][a[2]]=a[3]
    for f in fixtures:
        if f[1][:10]<'2022-01-01':homegaps[f[2]].append(f[6]-f[7])
        for team,opp,cur,lt,oc,ol,gd,venue in ((f[4],f[5],f[8],f[9],f[10],f[11],f[6]-f[7],1),
                                            (f[5],f[4],f[10],f[11],f[8],f[9],f[7]-f[6],-1)):
            record={'fixture':f[0],'kickoff':f[1],'date':f[1][:10],'league':f[2],'season':f[3],
                    'team':team,'opponent':opp,'current':cur,'baseline':lt,'gd':gd,'venue':venue}
            series[team].append(record)
            if cur is not None and lt is not None:latest[team].append((f[1],.6*cur+.4*lt))
    for v in latest.values():v.sort()
    dates={team:[t for t,_ in v] for team,v in latest.items()}
    homeedge={lg:float(np.mean(vals)) for lg,vals in homegaps.items()}
    fallback=float(np.mean([x for vals in homegaps.values() for x in vals]))
    rows={h:[] for h in HORIZONS};diagnostics=Counter()
    for team,ss in series.items():
        ss.sort(key=lambda r:(r['kickoff'],r['fixture']))
        seasons=Counter()
        for i,r in enumerate(ss):
            early=seasons[(r['league'],r['season'])]<5
            seasons[(r['league'],r['season'])]+=1
            if r['date']<'2022-01-01' or i<10 or i%5:continue
            diagnostics['candidate_anchors']+=1
            snap=snapshots.get((team,r['date']))
            if not snap or r['current'] is None or r['baseline'] is None:
                diagnostics['no_eligible_squad_or_club_ranks']+=1;continue
            change=turnover([minutes[(f['fixture'],team)] for f in ss[i-5:i]],
                            [minutes[(f['fixture'],team)] for f in ss[i-10:i-5]])
            tier=TIERS.get(r['league']);prev=membership.get((team,r['season']-1),set())
            groups=['all']
            if tier:
                prior_tiers=[TIERS[lg][1] for lg in prev if lg in TIERS and TIERS[lg][0]==tier[0]]
                if any(t>tier[1] for t in prior_tiers):groups.append('promoted')
                if any(t<tier[1] for t in prior_tiers):groups.append('relegated')
                if int(r['date'][5:7]) in (1,7,8):groups.append('transfer_window_proxy')
            if early:groups.append('early_season')
            if change is not None and change>=.35:groups.append('large_squad_change')
            dt=datetime.fromisoformat(r['kickoff']);week=dt.strftime('%G-%V')
            for h in HORIZONS:
                future=ss[i:i+h]
                if len(future)<h:
                    diagnostics[f'h{h}_incomplete']+=1;continue
                if (datetime.fromisoformat(future[-1]['kickoff'])-dt).days>365:
                    diagnostics[f'h{h}_over_365_days']+=1;continue
                split=split_for(r['date'],future[-1]['date'])
                if split is None:
                    diagnostics[f'h{h}_purged_boundary']+=1;continue
                adjusted=[]
                for f in future:
                    j=bisect_right(dates.get(f['opponent'],[]),r['kickoff'])-1
                    if j<0:break
                    strength=latest[f['opponent']][j][1]
                    adjusted.append(f['gd']+(strength-1000)/100-f['venue']*homeedge.get(f['league'],fallback))
                rows[h].append({**r,**snap,'index':i,'horizon':h,'end':future[-1]['date'],'split':split,
                    'week':week,'groups':groups,'turnover':change,'early':int(early),
                    'goal_difference':float(np.mean([f['gd'] for f in future])),
                    'points':float(np.mean([3 if f['gd']>0 else 1 if f['gd']==0 else 0 for f in future])),
                    'adjusted_goal_difference':float(np.mean(adjusted)) if len(adjusted)==h else None})
    provenance={'player_input_sha256':prior['input_sha256'],
                'player_replay_sha256':sha('.cache/player_club_strength_replay.pkl.gz'),
                'player_replay_source_sha256':prior['code_sha256'],
                'membership_input_sha256':sha('.cache/strength_weight_inputs.json.gz'),
                'last_fixture':fixtures[-1][1],'fixtures':len(fixtures),'clubs':len(series),
                'eligible_squad_snapshots':len(snapshots),'ambiguous_team_dates':ambiguous,
                'home_advantage_pre2022':homeedge,'diagnostics':dict(diagnostics)}
    encoded=json.dumps({'provenance':provenance,'rows':rows},separators=(',',':')).encode()
    Path('.cache/squad_forward_rows.json.gz').write_bytes(gzip.compress(encoded))
    return rows,provenance


def moving_week_interval(delta,weeks,repeats=1000,length=26):
    totals=defaultdict(lambda:[0.,0.])
    for d,w in zip(delta,weeks):totals[w][0]+=float(d);totals[w][1]+=1
    # Include calendar weeks without observations.
    from datetime import timedelta
    start=datetime.strptime(min(totals)+'-1','%G-%V-%u')
    end=datetime.strptime(max(totals)+'-1','%G-%V-%u')
    keys=[(start+timedelta(weeks=i)).strftime('%G-%V') for i in range((end-start).days//7+1)]
    a=np.array([totals[w] for w in keys]);n=len(a);rng=np.random.default_rng(SEED)
    if n<length:return {'weeks':n,'ci95':None}
    estimates=[]
    for _ in range(repeats):
        starts=rng.integers(0,n,math.ceil(n/length))
        ids=((starts[:,None]+np.arange(length))%n).ravel()[:n]
        sums=a[ids].sum(axis=0)
        if sums[1]:estimates.append(sums[0]/sums[1])
    return {'weeks':n,'block_weeks':length,'effective_blocks_approx':n/length,
            'ci95':np.quantile(estimates,[.025,.975]).tolist()}


def normalize(x,train):
    mean=x[train].mean(axis=0);sd=x[train].std(axis=0);sd[sd<1e-8]=1
    return np.column_stack((np.ones(len(x)),(x-mean)/sd))


def ols(x,y,mask):return np.linalg.lstsq(x[mask],y[mask],rcond=1e-10)[0]


def augmentation(x,z,y,train,val,dev,test):
    baseline=x@ols(x,y,train)
    augmented=np.column_stack((x,z))
    extra=augmented@ols(augmented,y,train)
    choices=[(float(np.mean((baseline[val]+g*(extra[val]-baseline[val])-y[val])**2)),g)
             for g in (0.,.25,.5,.75,1.)]
    # Round near-ties to avoid different choices from floating-point reparameterization.
    score,gamma=min(choices,key=lambda t:(round(t[0],12),t[1]))
    b=x[test]@ols(x,y,dev);a=augmented[test]@ols(augmented,y,dev)
    return b+gamma*(a-b),gamma,score


def assess(rows,target,baseline):
    rr=[r for r in rows if r[target] is not None]
    train=np.array([r['split']=='train' for r in rr]);val=np.array([r['split']=='validation' for r in rr]);test=np.array([r['split']=='test' for r in rr]);dev=train|val
    if min(train.sum(),val.sum(),test.sum())<100:raise RuntimeError('Insufficient chronological cohorts')
    y=np.array([r[target] for r in rr]);leagues=sorted({r['league'] for r,b in zip(rr,train) if b})
    controls=np.array([club_basis(r,baseline)+[int(r['league']==lg) for lg in leagues[1:]]+
                       [math.sin(2*math.pi*int(r['date'][5:7])/12),math.cos(2*math.pi*int(r['date'][5:7])/12),r['early']] for r in rr])
    x=normalize(controls,train)
    raw=np.array([r['raw'] for r in rr]);neutral=np.array([r['neutral'] for r in rr])
    residual=raw-x@ols(x,raw,train)
    z=normalize(np.array([[r['embedded'],r['embedded_squared']] for r in rr]),train)[:,1:]
    history=np.column_stack((x,z))
    preds={'club_only':x[test]@ols(x,y,dev),'history_only':history[test]@ols(history,y,dev)}
    selections={}
    for name,base,extra in [('raw_squad',x,raw),('residual_squad',x,residual),
                             ('history_raw',history,raw),('history_neutral',history,neutral)]:
        preds[name],g,score=augmentation(base,extra,y,train,val,dev,test)
        selections[name]={'augmentation_shrinkage':g,'validation_mse':score}
    equality=float(np.max(np.abs(preds['raw_squad']-preds['residual_squad'])))
    if equality>1e-6:raise AssertionError('Raw/residual equivalence failed')
    tr=[r for r,b in zip(rr,test) if b];clubs=[r['team'] for r in tr];weeks=[r['week'] for r in tr]
    losses={name:(p-y[test])**2 for name,p in preds.items()}
    results={}
    for name in MODELS:
        delta=losses[name]-losses['club_only'];dh=losses[name]-losses['history_only']
        results[name]={'mse':float(losses[name].mean()),'mae':float(np.abs(preds[name]-y[test]).mean()),
            'delta_vs_club':{'mean':float(delta.mean()),**interval(delta,clubs)},
            'delta_vs_history':{'mean':float(dh.mean()),**interval(dh,clubs)},
            'calendar_block_delta_vs_club':moving_week_interval(delta,weeks),
            'calendar_block_delta_vs_history':moving_week_interval(dh,weeks),**selections.get(name,{})}
    groups={g:np.array([g in r['groups'] for r in tr]) for g in ('all','promoted','relegated','early_season','transfer_window_proxy','large_squad_change')}
    groups['nonoverlapping']=np.array([r['index']%r['horizon']==0 for r in tr])
    groups['2024-25']=np.array([r['date']<'2025-07-01' for r in tr])
    groups['2025-onward']=~groups['2024-25']
    cohorts={}
    for label,mask in groups.items():
        if not mask.any():continue
        cc=[c for c,b in zip(clubs,mask) if b]
        cohorts[label]={'n':int(mask.sum()),'clubs':len(set(cc)),'models':{}}
        for name in MODELS:
            d=losses[name][mask]-losses['club_only'][mask];dh=losses[name][mask]-losses['history_only'][mask]
            cohorts[label]['models'][name]={'mse':float(losses[name][mask].mean()),
                'delta_vs_club':{'mean':float(d.mean()),**interval(d,cc)},
                'delta_vs_history':{'mean':float(dh.mean()),**interval(dh,cc)}}
    return {'train_n':int(train.sum()),'validation_n':int(val.sum()),'test_n':int(test.sum()),
            'test_clubs':len(set(clubs)),'models':results,'cohorts':cohorts,
            'raw_residual_prediction_max_abs_difference':equality,
            'residual_vs_rating_test_correlation':corr(residual[test],np.array([sum(club_basis(r,baseline)[:1]) for r in tr])),
            'raw_squad_vs_blend_test_correlation':corr(raw[test],[.6*r['current']+.4*r['baseline'] for r in tr])}


def main():
    if '--cached-rows' in sys.argv:
        cached=json.loads(gzip.decompress(Path('.cache/squad_forward_rows.json.gz').read_bytes()))
        rows={int(h):v for h,v in cached['rows'].items()};provenance=cached['provenance']
    else:
        print('Building frozen squad anchors and purged forward targets',flush=True)
        rows,provenance=build_rows()
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'code_sha256':CODE_SHA,
            'provenance':provenance,'rows_sha256':sha('.cache/squad_forward_rows.json.gz'),
            'horizons':{},'protocol_sha256':sha(ROOT/'DESIGN.md')}
    for h in HORIZONS:
        result['horizons'][str(h)]={}
        for target in TARGETS:
            result['horizons'][str(h)][target]={}
            for baseline in BASELINES:
                print('Evaluating',h,target,baseline,flush=True)
                result['horizons'][str(h)][target][baseline]=assess(rows[h],target,baseline)
    (ROOT/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('Results written',flush=True)

if __name__=='__main__':main()
