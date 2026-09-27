"""Offline chronological player/club ablation. See DESIGN.md for interpretation limits."""
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path
import gzip
import hashlib
import json
import math
import pickle
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from scipy.stats import spearmanr
from thecornerfc import player_ratings as pr

ROOT = Path(__file__).parent
NORM_END = '2022-01-01'
VAL_START = '2023-07-01'
TEST_START = '2024-07-01'
POSITIONS = list(pr.WEIGHTS)
VARIANTS = ('scaled', 'preclub_percentile', 'fixed_club', 'residual')
SEED = 20260927
CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def corr(x, y, rank=False):
    x, y = np.asarray(x), np.asarray(y)
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(spearmanr(x, y).statistic if rank else np.corrcoef(x, y)[0, 1])


def interval(delta, clusters, repeats=1000):
    totals = defaultdict(lambda: [0., 0])
    for d, c in zip(delta, clusters):
        totals[c][0] += float(d)
        totals[c][1] += 1
    a = np.asarray(list(totals.values()))
    if len(a) < 8:
        return {'clusters':len(a), 'ci95':None}
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(repeats):
        s = a[rng.integers(0, len(a), len(a))].sum(axis=0)
        draws.append(s[0] / s[1])
    return {'clusters':len(a), 'ci95':np.quantile(draws, [.025,.975]).tolist()}


def normalize_fit(x):
    mean, sd = x.mean(axis=0), x.std(axis=0)
    sd[sd < 1e-8] = 1
    return mean, sd


def design(x, mean, sd):
    return np.column_stack((np.ones(len(x)), (x - mean) / sd))


def ridge(x, y, alpha):
    penalty = np.eye(x.shape[1]) * alpha
    penalty[0,0] = 0
    return np.linalg.solve(x.T @ x + penalty, x.T @ y)


def logistic(x, y, alpha):
    target = np.eye(3)[y]
    def fun(flat):
        w = flat.reshape(x.shape[1], 3)
        logits = x @ w
        lp = logits - logsumexp(logits, axis=1)[:,None]
        penalized = w.copy(); penalized[0] = 0
        loss = -np.sum(target * lp) / len(y) + alpha * np.sum(penalized**2) / 2
        grad = x.T @ (np.exp(lp) - target) / len(y) + alpha * penalized
        return loss, grad.ravel()
    fit = minimize(fun, np.zeros(x.shape[1]*3), jac=True, method='L-BFGS-B',
                   options={'maxiter':400, 'ftol':1e-11})
    if not fit.success:
        raise RuntimeError('Logistic optimization did not converge: ' + fit.message)
    return fit.x.reshape(x.shape[1], 3)


def probs(x,w):
    logits=x@w
    return np.exp(logits-logsumexp(logits,axis=1)[:,None])


def calibration(p,y):
    bins = {}; total=0
    for k in range(3):
        bins[str(k)] = []
        for lo in np.arange(0,1,.1):
            sel=(p[:,k]>=lo)&(p[:,k]<lo+.1)
            if not sel.any():continue
            rate=float(np.mean(y[sel]==k)); pred=float(p[sel,k].mean())
            bins[str(k)].append({'lo':round(float(lo),1),'n':int(sel.sum()),'predicted':pred,'observed':rate})
            total+=sel.sum()*abs(pred-rate)
    return float(total/(3*len(y))), bins


def snapshot_audit():
    players=json.loads(Path('docs/data/players.json').read_text())
    rankings=json.loads(Path('docs/data/rankings.json').read_text())
    ranks={r[0]:r[4] for r in rankings['rankings'] if r[4] is not None}
    grouped=defaultdict(list)
    for r in players['players']:
        pos=pr.role_group(r[2]) or r[2]
        if r[5] in ranks and r[3] is not None:
            grouped[pos].append((r[3],ranks[r[5]],r[5]))
    out={}
    for pos, rows in grouped.items():
        a=np.array(rows)
        clubs=defaultdict(list)
        for rating,_,club in rows:clubs[club].append(rating)
        eligible=[v for v in clubs.values() if len(v)>=3]
        within=sum(sum((x-np.mean(v))**2 for x in v) for v in clubs.values())
        total=sum((a[:,0]-a[:,0].mean())**2)
        out[pos]={'n':len(rows),'clubs':len(clubs),'pearson':corr(a[:,0],a[:,1]),
                  'spearman':corr(a[:,0],a[:,1],True),
                  'between_club_variance_fraction':float(1-within/total),
                  'clubs_with_3_players':len(eligible),
                  'median_within_club_sd':float(np.median([np.std(v) for v in eligible])) if eligible else None,
                  'median_within_club_p90_p10':float(np.median([np.quantile(v,.9)-np.quantile(v,.1) for v in eligible])) if eligible else None}
    return {'rankings_generated_at':rankings.get('generated_at'),'positions':out,
            'export_hashes':{n:hashlib.sha256(Path('docs/data/'+n+'.json').read_bytes()).hexdigest() for n in ('players','rankings')}}


def temporal_norms(apps, offsets):
    seasons=defaultdict(lambda:{'sums':dict.fromkeys(pr.SUMS,0.),'roles':Counter(),'broad':Counter()})
    for row in apps:
        if row[9] in pr.REFERENCE:
            pr._add_season(seasons[(row[2],row[8])],row,pr._adjusted(row,offsets))
    groups=defaultdict(list)
    for entry in seasons.values():
        pos=pr.season_group(entry)
        if entry['sums']['minutes']>=900 and pos in pr.WEIGHTS:
            groups[pos].append(pr.metrics(entry['sums']))
    norms={}
    for pos,rows in groups.items():
        norms[pos]={}
        for key in pr.WEIGHTS[pos]:
            values=[r[key] for r in rows if r[key] is not None]
            if values:
                norms[pos][key]=(float(np.mean(values)),float(np.std(values)) or 1.)
    return norms


def replay(data):
    fixtures=data['fixtures']; byfid={f[0]:f for f in fixtures}
    apps=defaultdict(list); norm_apps=[]
    offsets=defaultdict(lambda:[0.,0.]); broad=defaultdict(lambda:[0.,0.])
    for a in data['apps']:
        f=byfid[a[0]]
        row=a[:8]+[f[3],f[2],'FT']+a[8:]+[f[12] if a[1]==f[4] else f[13]]
        apps[a[0]].append(row)
        if f[1][:10]<NORM_END:
            norm_apps.append(row)
            if row[7] is not None:
                for agg,key in ((offsets,(row[9],row[5])),(broad,row[5])):
                    agg[key][0]+=row[7]*row[3];agg[key][1]+=row[3]
    offsets={k:s/n-broad[k[1]][0]/broad[k[1]][1] for k,(s,n) in offsets.items()}
    norms=temporal_norms(norm_apps,offsets)
    windows=defaultdict(pr.Window); recent=defaultdict(lambda:deque(maxlen=5))
    cdf=defaultdict(list); candidates=[]; matches=[]; transfers=[]; last={}; spell={}
    born={p[0]:p[2] for p in data['players']}
    counts=Counter()

    def raw(player,dt):
        w=windows.get(player)
        if w is None:return None
        w.expire(dt)
        pos=w.position();mins=w.sums['minutes']
        if mins<180 or pos not in norms:return None
        m=pr.metrics(w.sums)
        score=sum(pr.WEIGHTS[pos][k]*(m[k]-mean)/sd for k,(mean,sd) in norms[pos].items()
                  if m[k] is not None)
        score=(score*mins+pr.MINUTES_PRIOR*pr.SHRINK_MINUTES)/(mins+pr.SHRINK_MINUTES)
        return (score,w.sums['club_mins']/mins,pos,mins)

    def ratings(s):
        score,club,pos,mins=s
        ref=cdf.get(pos)
        if not ref:return None
        pct=pr.stretched_pct(score,ref)
        return [pr.final_rank(pct,club,pos),pct,pr.final_rank(pct,1000,pos)]

    # Same-kickoff batches prevent a simultaneous match from contaminating another's inputs.
    for kickoff,batch in groupby(fixtures,key=lambda f:f[1]):
        batch=list(batch); dt=datetime.fromisoformat(kickoff); date=kickoff[:10]
        if date>=NORM_END and not counts['cdf_frozen']:
            cdf={pos:sorted(v) for pos,v in cdf.items()};counts['cdf_frozen']=1
        for f in batch:
            fid,_,league,season,home,away,hg,ag,hcur,hlt,acur,alt,*_=f
            if any(x is None for x in (hcur,hlt,acur,alt,hg,ag)):continue
            aa=apps[fid]
            teamapps={t:[a for a in aa if a[1]==t] for t in (home,away)}
            # Protect absence=0 against partial or absent provider records.
            coverage=all(sum(a[3] for a in teamapps[t])>=850 and len(teamapps[t])>=11 for t in (home,away))
            rawcache={p:raw(p,dt) for p in {a[2] for a in aa}|{p for t in (home,away) for g in recent[t] for p in g}}
            if date<NORM_END:
                if league in pr.REFERENCE:
                    for a in aa:
                        s=rawcache.get(a[2])
                        if s and s[3]>=900:cdf[s[2]].append(s[0])
                continue
            predictions={}; event_byplayer={}
            # Transfers are observed club changes, never future registration information.
            for a in aa:
                p=a[2];team=a[1];club=hlt if team==home else alt;s=rawcache.get(p)
                before=last.get(p)
                if before and before['team']!=team:
                    if (dt-before['dt']).days<=365 and s and before['values']:
                        move={'player':p,'date':date,'position':s[2], 'old_team':before['team'],'new_team':team,
                              'club_delta':club-before['club'],'pre':before['values'],'pre_window_club':before['window_club'],
                              'first':ratings(s),'first_window_club':s[1], 'fifth':None,'fifth_window_club':None,
                              'twentieth':None,'twentieth_window_club':None}
                        transfers.append(move);spell[p]=[team,1,move]
                    else:spell[p]=[team,1,None]
                elif p in spell and spell[p][0]==team:spell[p][1]+=1
                else:spell[p]=[team,1,None]
                sp=spell[p]
                if sp[2] and sp[1]<=5:
                    event_byplayer[p]=sp[2]['club_delta']
                    if sp[1]==5 and s:
                        sp[2]['fifth']=ratings(s);sp[2]['fifth_window_club']=s[1]
                if sp[2] and sp[1]==20 and s:
                    sp[2]['twentieth']=ratings(s);sp[2]['twentieth_window_club']=s[1]
            for team,club,cur,opp,oppcur in ((home,hlt,hcur,alt,acur),(away,alt,acur,hlt,hcur)):
                history=recent[team];minutes=Counter()
                for g in history:minutes.update(g)
                scored=[]
                for p,m in minutes.most_common():
                    s=rawcache.get(p)
                    if not s:continue
                    values=ratings(s)
                    if values is None:continue
                    scored.append((p,m,s,values))
                xi=[a for a in scored if a[2][2]=='GK'][:1]+[a for a in scored if a[2][2]!='GK'][:10]
                if len(xi)==11:
                    predictions[team]=xi
                if not coverage:continue
                actual={a[2]:a for a in teamapps[team]}
                for p,m,s,values in scored:
                    age=(dt.date()-datetime.fromisoformat(born[p]).date()).days/365.25 if born.get(p) else 27.
                    a=actual.get(p)
                    performance=pr._adjusted(a,offsets) if a and a[3]>=30 else None
                    candidates.append({'player':p,'team':team,'date':date,'position':s[2],'league':league,
                        'club':s[1],'values':values,'minutes':float(a[3]) if a else 0.,'performance':performance,
                        'transfer_delta':event_byplayer.get(p),
                        'controls':[club,cur,opp,oppcur,int(team==home),age,age**2,m/(90*max(1,len(history))),
                                    math.log1p(s[3])]+[int(s[2]==pos) for pos in POSITIONS]})
            if coverage and len(predictions)==2:
                matches.append({'date':date,'week':dt.strftime('%G-%V'),'fixture':fid,'league':league,
                    'y':0 if hg>ag else 1 if hg==ag else 2,
                    'controls':[(hcur-acur)/100,(hlt-alt)/100,(hcur+acur)/200,(hlt+alt)/200],
                    'home':[(s[2],s[1],v) for _,m,s,v in predictions[home]],
                    'away':[(s[2],s[1],v) for _,m,s,v in predictions[away]]})
            for a in aa:
                s=rawcache.get(a[2]);v=ratings(s) if s else None
                last[a[2]]={'team':a[1],'dt':dt,'club':hlt if a[1]==home else alt,'values':v,'window_club':s[1] if s else None}
        # Only now consume outcomes of every fixture at this kickoff.
        for f in batch:
            fid=f[0];aa=apps[fid]
            for a in aa:
                club=f[9] if a[1]==f[4] else f[11]
                if club is None:continue
                st=pr._row_stats({'stats':a[11:-1],'minutes':a[3],'rating':pr._adjusted(a,offsets),'opp_xg':a[-1]})
                st['club_mins']=club*a[3]
                windows[a[2]].add(dt,st,a[6],a[5])
            for team in (f[4],f[5]):
                played={a[2]:a[3] for a in aa if a[1]==team}
                if played:recent[team].append(played)
    return candidates,matches,transfers,{'norm_appearances':len(norm_apps),'cdf_n':{k:len(v) for k,v in cdf.items()},
        'unavailable_training_metrics':{p:[k for k in pr.WEIGHTS[p] if k not in norms.get(p,{})] for p in POSITIONS}}


def add_residual(candidates,matches,transfers):
    coefficients={}
    for pos in POSITIONS:
        rows=[r for r in candidates if r['date']<VAL_START and r['position']==pos]
        x=np.array([[1,r['club']/1000,(r['club']/1000)**2] for r in rows])
        coefficients[pos]=np.linalg.lstsq(x,[r['values'][0] for r in rows],rcond=None)[0]
    def expected(pos,club):return float(np.array([1,club/1000,(club/1000)**2])@coefficients[pos])
    for r in candidates:r['values'].append(r['values'][0]-expected(r['position'],r['club']))
    for r in matches:
        h=np.array([[club/1000,(club/1000)**2] for _,club,_ in r['home']]).mean(axis=0)
        a=np.array([[club/1000,(club/1000)**2] for _,club,_ in r['away']]).mean(axis=0)
        r['history_controls']=list(h-a)+list((h+a)/2)
        for side in ('home','away'):
            r[side]=[v[:3]+[v[0]-expected(pos,club)] for pos,club,v in r[side]]
        r['values']=(np.mean(r['home'],axis=0)-np.mean(r['away'],axis=0)).tolist()
        del r['home'];del r['away']
    for r in transfers:
        for stage in ('pre','first','fifth','twentieth'):
            if r[stage] is not None:
                r[stage]=list(r[stage][:3])+[r[stage][0]-expected(r['position'],r[stage+'_window_club'])]
    return {k:v.tolist() for k,v in coefficients.items()}


def fit_evaluate(rows, classification=False, history_controls=False):
    dates=np.array([r['date'] for r in rows])
    train=dates<VAL_START;val=(dates>=VAL_START)&(dates<TEST_START);test=dates>=TEST_START
    y=np.array([r['y'] for r in rows] if classification else [r['target'] for r in rows])
    controls=np.array([r['controls'] for r in rows],dtype=float)
    if history_controls:
        extras=[r['history_controls'] for r in rows] if classification else [
            [v*int(r['position']==pos) for pos in POSITIONS
             for v in (r['club']/1000,(r['club']/1000)**2)] for r in rows]
        controls=np.column_stack((controls,extras))
    leagues=sorted({r['league'] for r in rows if r['date']<VAL_START})
    controls=np.column_stack((controls,[[int(r['league']==lg) for lg in leagues] for r in rows]))
    results={}; losses={}; test_predictions={}
    for name,col in [('club_controls',None)]+list(zip(VARIANTS,range(4))):
        x=controls if col is None else np.column_stack((controls,[r['values'][col] for r in rows]))
        mean,sd=normalize_fit(x[train]);xx=design(x,mean,sd)
        best=None
        for alpha in ([.0001,.001,.01,.1] if classification else [1.,100.,10000.]):
            w=logistic(xx[train],y[train],alpha) if classification else ridge(xx[train],y[train],alpha)
            pred=probs(xx[val],w) if classification else np.clip(xx[val]@w,0,90) if rows[0].get('endpoint')=='minutes' else xx[val]@w
            score=float(-np.log(pred[np.arange(val.sum()),y[val]]).mean()) if classification else float(np.mean((pred-y[val])**2))
            if best is None or score<best[0]:best=(score,alpha)
        dev=train|val;mean,sd=normalize_fit(x[dev]);xx=design(x,mean,sd)
        w=logistic(xx[dev],y[dev],best[1]) if classification else ridge(xx[dev],y[dev],best[1])
        pred=probs(xx[test],w) if classification else xx[test]@w
        if not classification and rows[0].get('endpoint')=='minutes':pred=np.clip(pred,0,90)
        if classification:
            loss=-np.log(pred[np.arange(test.sum()),y[test]])
            brier=((pred-np.eye(3)[y[test]])**2).sum(axis=1)
            ece,bins=calibration(pred,y[test])
            results[name]={'log_loss':float(loss.mean()),'brier':float(brier.mean()),'accuracy':float((pred.argmax(axis=1)==y[test]).mean()),'ece':ece,'calibration':bins}
            losses[name]=(loss,brier)
        else:
            loss=(pred-y[test])**2
            results[name]={'mse':float(loss.mean()),'mae':float(np.abs(pred-y[test]).mean())}
            losses[name]=(loss,)
        results[name].update({'validation_score':best[0],'alpha':best[1]})
        test_predictions[name]=pred
    test_rows=[r for r,b in zip(rows,test) if b]
    clusters=[r['week'] if classification else r['player'] for r in test_rows]
    for name in results:
        for ref in ('club_controls','scaled'):
            delta=losses[name][0]-losses[ref][0]
            results[name]['delta_vs_'+ref]={'mean':float(delta.mean()),**interval(delta,clusters)}
        if classification:
            delta=losses[name][1]-losses['club_controls'][1]
            results[name]['brier_delta_vs_club_controls']={'mean':float(delta.mean()),**interval(delta,clusters)}
    subgroup={}
    groups={'2024-25':[r['date']<'2025-07-01' for r in test_rows],
            '2025-onward':[r['date']>='2025-07-01' for r in test_rows]}
    if not classification:
        groups.update({pos:[r['position']==pos for r in test_rows] for pos in POSITIONS})
        groups.update({'strong_to_weak':[(r['transfer_delta'] or 0)<=-50 for r in test_rows],
                       'weak_to_strong':[(r['transfer_delta'] or 0)>=50 for r in test_rows]})
    for group,mask in (groups.items() if not history_controls else []):
        mask=np.array(mask)
        if not mask.any():continue
        subgroup[group]={'n':int(mask.sum()),'models':{}}
        for name in results:
            delta=losses[name][0][mask]-losses['club_controls'][0][mask]
            subgroup[group]['models'][name]={'loss':float(losses[name][0][mask].mean()),
                'delta_vs_club':float(delta.mean()),**interval(delta,[c for c,b in zip(clusters,mask) if b])}
    return {'train_n':int(train.sum()),'validation_n':int(val.sum()),'test_n':int(test.sum()),
            'test_players_or_weeks':len(set(clusters)),'models':results,'subgroups':subgroup}


def transfer_summary(rows, milestone='fifth'):
    out={}
    for label,sel in [('all',lambda r:True),('strong_to_weak',lambda r:r['club_delta']<=-50),('weak_to_strong',lambda r:r['club_delta']>=50)]:
        rr=[r for r in rows if r['date']>=TEST_START and r[milestone] is not None and sel(r)]
        out[label]={'n':len(rr),'players':len({r['player'] for r in rr}),'variants':{}}
        for i,name in enumerate(VARIANTS):
            pre=[r['pre'][i] for r in rr];after=[r[milestone][i] for r in rr]
            change=np.array(after)-pre
            out[label]['variants'][name]={'pre_vs_post_pearson':corr(pre,after),
                'mean_change':float(np.mean(change)) if rr else None,
                'median_absolute_change':float(np.median(np.abs(change))) if rr else None,
                'change_vs_club_change':corr(change,[r['club_delta'] for r in rr]),
                'mean_change_ci':interval(change,[r['player'] for r in rr]),
                'first_match_mean_change':float(np.mean([r['first'][i]-r['pre'][i] for r in rr])) if rr else None}
    return out


def main():
    encoded=gzip.decompress(Path('.cache/player_club_strength_inputs.json.gz').read_bytes())
    data=json.loads(encoded)
    print('replaying',len(data['apps']),'appearances',flush=True)
    candidates,matches,transfers,meta=replay(data)
    print('replay complete',len(candidates),len(matches),len(transfers),flush=True)
    coef=add_residual(candidates,matches,transfers)
    with gzip.open('.cache/player_club_strength_replay.pkl.gz','wb') as cache:
        pickle.dump((candidates,matches,transfers,meta,coef),cache,protocol=5)
    output={'generated_at':datetime.now(timezone.utc).isoformat(),'input_sha256':hashlib.sha256(encoded).hexdigest(),
        'code_sha256':CODE_SHA256,
        'production_source_hashes':{name:hashlib.sha256(Path('thecornerfc',name+'.py').read_bytes()).hexdigest()
                                    for name in ('player_ratings','positions','config')},
        'data_extracted_at':data['extracted_at'],'captures':data['captures'],
        'fixture_n':len(data['fixtures']),'appearance_n':len(data['apps']),
        'first_kickoff':data['fixtures'][0][1],'last_kickoff':data['fixtures'][-1][1],
        'replay':meta,'residual_coefficients':coef,'current_snapshot':snapshot_audit(),
        'transfer_stability':transfer_summary(transfers),
        'transfer_stability_20th':transfer_summary(transfers,'twentieth')}
    for target in ('minutes','performance'):
        rows=[dict(r,target=r[target],endpoint=target) for r in candidates if r[target] is not None]
        print('evaluating',target,len(rows),flush=True)
        output[target]=fit_evaluate(rows)
        print('checking historical-club confounding',target,flush=True)
        output[target]['history_controlled']=fit_evaluate(rows,history_controls=True)
    print('evaluating matches',len(matches),flush=True)
    output['matches']=fit_evaluate(matches,True)
    output['matches']['history_controlled']=fit_evaluate(matches,True,True)
    output['historical_correlations']={}
    for pos in POSITIONS:
        rows=[r for r in candidates if r['date']>=TEST_START and r['position']==pos]
        # One observation per player per UTC month limits repeated fixture weighting.
        rows=list({(r['player'],r['date'][:7]):r for r in rows}.values())
        output['historical_correlations'][pos]={'n':len(rows),'variants':{name:{
            'pearson':corr([r['values'][i] for r in rows],[r['club'] for r in rows]),
            'spearman':corr([r['values'][i] for r in rows],[r['club'] for r in rows],True)} for i,name in enumerate(VARIANTS)}}
    (ROOT/'results.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print('results written',flush=True)

if __name__=='__main__':main()
