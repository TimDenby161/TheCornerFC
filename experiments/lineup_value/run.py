"""Fixed-formula lineup experiment. Writes experiment artifacts only."""
from collections import defaultdict,deque,Counter
from datetime import datetime,timedelta
from itertools import groupby
from pathlib import Path
import gzip,json,hashlib,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
from thecornerfc.models import predictions as p, player_ratings as pr
from experiments.player_club_strength.run import calibration,interval
ROOT=Path(__file__).parent
GRID=[-.005,0.,.0025,.005,.01,.02]

def read(name):return json.loads(gzip.decompress(Path('.cache/'+name+'.json.gz').read_bytes()))
def dt(s):return datetime.fromisoformat(s)
def complete(lines):return lines is not None and len(lines)==2 and all(len(s)==4 and all(v is not None for v in s) for s in lines)
def shift(lines,gk=0.):return sum(w*(float(h)-float(a)) for w,h,a in zip([gk,.005,.005,.005],*lines)) if complete(lines) else 0.
def scores(base,lines,gk=0.):
    # Use the exact quadratic identity, without reapplying project()'s base clamps.
    margin=base[0]+shift(lines,gk); product=base[1]*base[2]
    hx=(margin+(margin*margin+4*product)**.5)/2; ax=product/hx
    return list(p.outcome_probabilities(hx,ax)[:3]),margin

def pack(fid,kickoff,league,hg,ag,base,pred,actual,**extra):
    r=dict(fixture=fid,date=kickoff[:10],week=dt(kickoff).strftime('%G-%V'),league=league,y=0 if hg>ag else 1 if hg==ag else 2,gd=hg-ag,base=base,pred=pred,actual=actual,**extra)
    r['scores']={'none':scores(base,None),'predicted':scores(base,pred),'actual':scores(base,actual)}
    for name,lines in [('predicted',pred),('actual',actual)]:
        for g in GRID:r['scores'][f'{name}_gk_{g}']=scores(base,lines,g)
    r['line_margin']=shift(pred)
    return r

def summary(rows,keys=('none','predicted','actual'),ref='none'):
    if not rows:return {'n':0}
    y=np.array([r['y'] for r in rows]); target=np.eye(3)[y]; weeks=[r['week'] for r in rows]
    out={'n':len(rows),'weeks':len(set(weeks)),'models':{}}
    def loss(key):
        a=np.array([r['scores'][key][0] for r in rows]);return a,-np.log(np.maximum(a[np.arange(len(y)),y],1e-15)),np.sum((a-target)**2,axis=1)
    _,rl,rb=loss(ref)
    _,pl,pb=loss('predicted')
    for key in keys:
        a,l,b=loss(key);ece,bins=calibration(a,y)
        out['models'][key]={'log_loss':float(l.mean()),'brier':float(b.mean()),'classwise_ece':ece,'calibration':bins,'accuracy':float(np.mean(a.argmax(axis=1)==y)),
          'goal_difference_mae':float(np.mean([abs(r['scores'][key][1]-r['gd']) for r in rows])),
          'delta_log_loss_vs_'+ref:float(np.mean(l-rl)),'delta_brier_vs_'+ref:float(np.mean(b-rb)),
          'log_loss_ci':interval(l-rl,weeks,2000),'brier_ci':interval(b-rb,weeks,2000),
          'delta_log_loss_vs_predicted':float(np.mean(l-pl)),'vs_predicted_ci':interval(l-pl,weeks,2000)}
    return out

def historical(x,h):
    lines={(r[0],r[1]):r for r in x['lines']}; starters={(r[0],r[1]):r[2:] for r in h['starters']}
    # Independently frozen FT set avoids treating extra-time scores as 90-minute outcomes.
    ft={f[0] for f in read('player_club_strength_inputs')['fixtures']}
    home=defaultdict(deque);away=defaultdict(deque);comp=defaultdict(deque);rows=[];excluded=Counter()
    for kickoff,batch in groupby(h['fixtures'],key=lambda f:f[1]):
        batch=list(batch); now=dt(kickoff)
        for f in batch:
            fid,_,lg,ht,at,hg,ag,hx,ax,hcur,hlt,acur,alt,*side=f
            for q in (home[ht],away[at],comp[lg]):
                while q and q[0][0]<now-timedelta(days=365):q.popleft()
            if kickoff[:10]<'2023-07-01' or fid not in ft:continue
            excluded['considered']+=1
            lr=[lines.get((fid,t)) for t in (ht,at)]
            if any(r is None for r in lr):excluded['missing_line_rows']+=1;continue
            pred=[r[10:14] for r in lr];act=[r[6:10] for r in lr]
            if any(r[3]!=11 for r in lr) or any(starters.get((fid,t))!=[11,11] for t in (ht,at)):
                excluded['incomplete_predicted_or_rated_actual_XI']+=1;continue
            if not complete(pred) or not complete(act):excluded['missing_line']+=1;continue
            if any(v is None for v in (hcur,hlt,acur,alt)):excluded['missing_club_rank']+=1;continue
            g=comp[lg]; lh=sum(z[1] for z in g)/len(g) if g else p.DEFAULT_HOME_GOALS;la=sum(z[2] for z in g)/len(g) if g else p.DEFAULT_AWAY_GOALS
            s=side if all(v is not None for v in side) else None
            baseline=p.predict_match(p.match_rank(hcur,hlt),p.match_rank(acur,alt),[r[1:] for r in home[ht]],[r[1:] for r in away[at]],lh,la,lg,sides=s)
            rows.append(pack(fid,kickoff,lg,hg,ag,list(baseline[:3]),pred,act,club_controls=[(hcur-acur)/100,(hlt-alt)/100]))
        for f in batch:
            fid,_,lg,ht,at,hg,ag,hx,ax,*_=f
            hf,af=p._form(hg,ag,hx,ax);home[ht].append((now,hf,af));away[at].append((now,af,hf));comp[lg].append((now,hg,ag))
    return rows,dict(excluded)

def select_snapshots(snapshots,hours=0):
    chosen={}
    for s in snapshots:
        if s[5]!='prospective' or max(dt(s[6]),dt(s[7]))>dt(s[1])-timedelta(hours=hours):continue
        if s[0] not in chosen or max(dt(s[6]),dt(s[7]))>max(dt(chosen[s[0]][6]),dt(chosen[s[0]][7])):chosen[s[0]]=s
    return list(chosen.values())

def prospective(x,h,hours_cutoff=0):
    fixtures={f[0]:f for f in h['fixtures']};versions={r[0]:r[4] for r in x['versions']}
    lineups=defaultdict(list);official=defaultdict(list)
    for r in x['lineups']:lineups[(r[0],r[1])].append(r)
    for r in x['official']:official[(r[0],r[1])].append(r)
    rows=[];allrows=[];excluded=Counter()
    selected_snapshots=select_snapshots(h.get('snapshots',x['snapshots']),hours_cutoff)
    for s in selected_snapshots:
        fid,kick,lg,hg,ag,source,captured,created,margin,hx,ax,ph,pd,pa,inp,ver=s
        if source!='prospective' or max(dt(captured),dt(created))>=dt(kick):continue
        pred=inp.get('predicted_lines')
        if not complete(pred):excluded['no_complete_line_adjustment']+=1;continue
        reproduced=p.predict_match(inp['home_match_rank'],inp['away_match_rank'],inp['home_records'],inp['away_records'],inp['league_home_goals'],inp['league_away_goals'],lg,inp.get('home_missing') or 0.,inp.get('away_missing') or 0.,inp.get('sides'),pred)
        if max(abs(a-b) for a,b in zip(reproduced[:6],[margin,hx,ax,ph,pd,pa]))>1e-8 or versions[ver]['XI_LINE_WEIGHTS']!=list(p.XI_LINE_WEIGHTS):
            excluded['formula_mismatch']+=1;continue
        base=[margin-shift(pred),hx,ax]
        hours=(dt(kick)-max(dt(captured),dt(created))).total_seconds()/3600
        r=pack(fid,kick,lg,hg,ag,base,pred,pred,hours=hours)
        allrows.append(r)
        actual=[];overlap=[];available=[]
        for side,team in enumerate(fixtures[fid][3:5]):
            ls=[l for l in lineups[(fid,team)] if l[2]=='prospective' and max(dt(l[3]),dt(l[4]))<=max(dt(captured),dt(created)) and max(dt(l[3]),dt(l[4]))<dt(kick)]
            os=official[(fid,team)]
            if not ls or not os:break
            l=max(ls,key=lambda a:dt(a[3]));o=min(os,key=lambda a:dt(a[2]))
            players=l[6];starters=[v for v in o[5] if v['starter']]
            if len(players)!=11 or len(starters)!=11:break
            pp=pr._by_line([(v['player_rating'],v['line']) for v in players])
            if any(v is None for v in pp) or max(abs(float(a)-b) for a,b in zip(pred[side],pp))>.011:break
            ratings={v['player']:v['player_rating'] for v in l[7].get('scored_candidates',[]) if v.get('player_rating') is not None}
            if any(v['player'] not in ratings for v in starters):break
            al=pr._by_line([(ratings[v['player']],pr.line_of(v.get('role'),v.get('position'))) for v in starters])
            if any(v is None for v in al):break
            actual.append(al);overlap.append(len({v['player'] for v in players}&{v['player'] for v in starters}));available.append(l[8])
        if len(actual)!=2:excluded['no_aligned_complete_frozen_actual_XI']+=1;continue
        reported=sum(len(v) for v in available)
        rows.append(pack(fid,kick,lg,hg,ag,base,pred,actual,hours=hours,overlap=sum(overlap),availability_records=reported))
    # A single chosen bookmaker per fixture (lowest ID), complete synchronized observation <= cutoff.
    odds=defaultdict(lambda:defaultdict(dict))
    for fid,book,sel,odd,cap,create in h['odds']:
        odds[fid][(book,cap)][sel]=(odd,create)
    matched=[]
    cutoffs={s[0]:max(dt(s[6]),dt(s[7])) for s in selected_snapshots}
    for r in rows:
        eligible=[(book,cap,{k:v[0] for k,v in vals.items()}) for (book,cap),vals in odds[r['fixture']].items() if dt(cap)<=cutoffs[r['fixture']] and all(k in vals and dt(vals[k][1])<=cutoffs[r['fixture']] for k in ['Home','Draw','Away'])]
        if not eligible:continue
        book=min(a[0] for a in eligible);_,_,vals=max((a for a in eligible if a[0]==book),key=lambda a:dt(a[1]))
        probs=np.array([1/vals[k] for k in ['Home','Draw','Away']]);probs/=probs.sum()
        r['scores']['market']=[probs.tolist(),0.];matched.append(r)
    return rows,allrows,matched,dict(excluded)

def breakdown(rows,threshold,pros=False):
    groups=defaultdict(list)
    for r in rows:
        groups['competition:'+str(r['league'])].append(r)
        groups['predicted_strength_gap:'+('large' if abs(r['line_margin'])>=threshold else 'small')].append(r)
        if pros:
            groups['XI_overlap:'+('high_20_to_22' if r['overlap']>=20 else 'medium_16_to_19' if r['overlap']>=16 else 'low_under_16')].append(r)
            groups['hours:'+('under_1' if r['hours']<1 else '1_to_6' if r['hours']<6 else '6_to_24' if r['hours']<24 else '24_plus')].append(r)
            groups['availability:'+('reports_present' if r['availability_records'] else 'no_reports_not_known_healthy')].append(r)
    return {k:summary(v) for k,v in groups.items()}

def main():
    x=read('lineup_value_inputs');h=read('lineup_value_history');rows,ex=historical(x,h)
    val=[r for r in rows if r['date']<'2024-07-01'];test=[r for r in rows if r['date']>='2024-07-01']
    threshold=float(np.median([abs(r['line_margin']) for r in val]))
    # Outcome-free club proxy: fit the expected lineup contribution using validation only.
    coef=np.linalg.lstsq([[1]+r['club_controls'] for r in val],[r['line_margin'] for r in val],rcond=None)[0]
    for r in rows:
        proxy=float(np.dot([1]+r['club_controls'],coef))
        r['scores']['club_proxy']=scores([r['base'][0]+proxy,*r['base'][1:]],None)
    keys=['none','predicted','actual','club_proxy']+[f'{v}_gk_{g}' for v in ['predicted','actual'] for g in GRID]
    validation=summary(val,keys);testing=summary(test,keys)
    selected={v:min(GRID,key=lambda g:validation['models'][f'{v}_gk_{g}']['log_loss']) for v in ['predicted','actual']}
    pro,allpro,market,pex=prospective(x,h)
    horizons={}
    for horizon in [1,6,24,48]:
        hr,ha,hm,he=prospective(x,h,horizon)
        horizons[str(horizon)]={'paired_XI':summary(hr),'predicted_ablation':summary(ha,('none','predicted')),'segments':breakdown(hr,threshold,True),'market':summary(hm,('none','predicted','actual','market'),'market'),'exclusions':he}
    gk_comparisons={}
    for variant in ['predicted','actual']:
        gk_comparisons[variant]=summary(test,[f'{variant}_gk_{g}' for g in GRID],variant)

    result={'status':'complete','evidence':'historical fixed-formula reconstruction plus small prospective capture cohort; no production changes',
      'audit':x['audit'],'horizon_cutoffs_hours':horizons,'gk_test_comparisons':gk_comparisons,'historical_exclusions':ex,'prospective_exclusions':pex,'validation':validation,'test':testing,'validation_selected_gk':selected,
      'large_gap_threshold_goals':threshold,'club_proxy_coefficients':coef.tolist(),'club_proxy_test':summary(test,('club_proxy','predicted','actual'),'club_proxy'),'historical_segments':breakdown(test,threshold),'prospective':summary(pro),'prospective_predicted_ablation':summary(allpro,('none','predicted')),
      'prospective_segments':breakdown(pro,threshold,True),'market_matched':summary(market,('none','predicted','actual','market'),'market'),
      'prospective_overlap':{'n':len(pro),'mean_correct_of_22':float(np.mean([r['overlap'] for r in pro])) if pro else None},
      'periods':{k:summary([r for r in test if (r['date']<'2025-07-01')==b]) for k,b in [('2024-25',True),('2025-onwards',False)]},
      'leagues':dict(h['leagues']),'provenance':{name:hashlib.sha256(gzip.decompress(Path('.cache/'+name+'.json.gz').read_bytes())).hexdigest() for name in ['lineup_value_inputs','lineup_value_history','player_club_strength_inputs']},
      'source_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),Path('thecornerfc/models/predictions.py'),Path('thecornerfc/models/player_ratings.py')]}}
    (ROOT/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    Path('.cache/lineup_value_rows.json.gz').write_bytes(gzip.compress(json.dumps({'historical':rows,'prospective':pro},allow_nan=False).encode()))
    print(json.dumps({'validation_n':len(val),'test_n':len(test),'prospective_n':len(pro),'prospective_ablation_n':len(allpro),'market_n':len(market),'selected_gk':selected,'exclusions':ex,'prospective_exclusions':pex}))
if __name__=='__main__':main()
