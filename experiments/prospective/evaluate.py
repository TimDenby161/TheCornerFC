"""Prospective shadow evaluation for protocols P3, P4, P6 and P7 (see PROTOCOLS.md).

Read-only: one READ ONLY / REPEATABLE READ transaction, no API calls, nothing written to the
database or read by production. Production code is imported, never modified.

Blinded by default: without --unblind the output contains sample accrual only, never outcome
metrics. --unblind refuses until the protocol's registered target is reached; --interim overrides
that and labels the output as a protocol deviation that cannot support a decision.
"""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import hashlib,json,math,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from thecornerfc import config,predictions as p,player_ratings as pr
from thecornerfc.evaluation import probability_metrics
ROOT=Path(__file__).parent

# Registered in PROTOCOLS.md; change only by a dated amendment there.
TARGETS={'P3':600,'P4':6500,'P6':2000,'P7':6500}
P7_GRID=[0.,.1,.2,.3,.4,.6]
P7_MIN_DAYS=7
REESTIMATE_AT=500
TOLERANCE=1e-8


def dt(v):return v if isinstance(v,datetime) else datetime.fromisoformat(str(v))
def created(s):return max(dt(s['captured_at']),dt(s['created_at']))
def outcome(hg,ag):return 0 if hg>ag else 1 if hg==ag else 2
def loss(q,y):return -math.log(max(q[y],1e-15))


def complete(lines):return bool(lines) and len(lines)==2 and all(len(side)==4 and all(v is not None for v in side) for side in lines)


def shift(lines,weights=p.XI_LINE_WEIGHTS):
    if not complete(lines):return 0.
    return sum(w*(float(h)-float(a)) for w,h,a in zip(weights,*lines))


def rescore(s,*,h_rank=None,a_rank=None,missing=True,lines='stored'):
    """predict_match on a snapshot's own inputs, optionally varying one component."""
    i=s['inputs']
    out=p.predict_match(i['home_match_rank'] if h_rank is None else h_rank,
                        i['away_match_rank'] if a_rank is None else a_rank,
                        i['home_records'],i['away_records'],i['league_home_goals'],i['league_away_goals'],
                        s['league_id'],(i.get('home_missing') or 0.) if missing else 0.,
                        (i.get('away_missing') or 0.) if missing else 0.,i.get('sides'),
                        i.get('predicted_lines') if lines=='stored' else lines)
    return list(out[3:6])


def reproduces(s):
    """The snapshot must be reproducible by today's formula before any component is varied."""
    out=rescore(s)
    stored=[s['p_home'],s['p_draw'],s['p_away']]
    return max(abs(a-b) for a,b in zip(out,stored))<=TOLERANCE


def year_rank(now,lt,days_ahead,year_weight):
    frac=min(max(days_ahead,0.)/365,1.)
    w=p.MATCH_RANK_NOW_TODAY+(year_weight-p.MATCH_RANK_NOW_TODAY)*frac
    return w*now+(1-w)*(lt if lt is not None else now)


def latest_before_kickoff(snaps):
    chosen={}
    for s in snaps:
        if s['source']!='prospective' or created(s)>=dt(s['kickoff']):continue
        if s['fixture_id'] not in chosen or created(s)>created(chosen[s['fixture_id']]):chosen[s['fixture_id']]=s
    return chosen


def earliest_ahead(snaps,min_days):
    chosen={}
    for s in snaps:
        days=(dt(s['effective_at'])-dt(s['model_reference_at'])).total_seconds()/86400
        if s['source']!='prospective' or days<min_days or created(s)>=dt(s['kickoff']):continue
        if s['fixture_id'] not in chosen or created(s)<created(chosen[s['fixture_id']]):chosen[s['fixture_id']]=s
    return chosen


def official_lines(s,team,lineups,officials):
    """Official starters rated with the pre-kickoff lineup snapshot's own candidate ratings.

    Production currently records official XIs only with results, after kickoff. Starters do not
    change after kickoff and ratings come from the pre-kickoff snapshot, so the counterfactual is
    leakage-free; hours before kickoff is negative when the XI was recorded late (PROTOCOLS.md P3).
    """
    ls=[l for l in lineups.get((s['fixture_id'],team),[]) if l['source']=='prospective' and created(l)<=created(s)]
    os=officials.get((s['fixture_id'],team),[])
    if not ls or not os:return None,None
    l=max(ls,key=created);o=min(os,key=lambda a:dt(a['captured_at']))
    starters=[v for v in o['players'] if v.get('starter')]
    ratings={v['player']:v['player_rating'] for v in l['selection_inputs'].get('scored_candidates',[]) if v.get('player_rating') is not None}
    if len(starters)!=11 or any(v['player'] not in ratings for v in starters):return None,None
    lines=pr._by_line([(ratings[v['player']],pr.line_of(v.get('role'),v.get('position'))) for v in starters])
    if any(v is None for v in lines):return None,None
    return lines,(dt(s['kickoff'])-dt(o['captured_at'])).total_seconds()/3600


def consensus(odds,cutoff):
    """Mean of per-bookmaker normalised implied H/D/A probabilities, latest complete set <= cutoff."""
    books=defaultdict(dict)
    for o in odds:
        if max(dt(o['captured_at']),dt(o['created_at']))>cutoff:continue
        key=o['selection'];prev=books[o['bookmaker_id']].get(key)
        if prev is None or dt(o['captured_at'])>dt(prev['captured_at']):books[o['bookmaker_id']][key]=o
    sets=[]
    for sel in books.values():
        if all(k in sel for k in ('Home','Draw','Away')):
            raw=[1/float(sel[k]['odds']) for k in ('Home','Draw','Away')];total=sum(raw)
            sets.append([x/total for x in raw])
    return [sum(x[i] for x in sets)/len(sets) for i in range(3)] if sets else None


def build(data):
    """Paired rows per protocol: {'fixture','week','y','models':{name:probabilities}}."""
    fixtures={f['fixture_id']:f for f in data['fixtures']}
    xi_weights={v['model_version_id']:v['configuration'].get('XI_LINE_WEIGHTS') for v in data['versions']}
    snaps=[dict(s,kickoff=fixtures[s['fixture_id']]['kickoff']) for s in data['snapshots'] if s['fixture_id'] in fixtures]
    lineups=defaultdict(list);officials=defaultdict(list);odds=defaultdict(list)
    for l in data['lineups']:lineups[(l['fixture_id'],l['team_id'])].append(l)
    for o in data['officials']:officials[(o['fixture_id'],o['team_id'])].append(o)
    for o in data['odds']:odds[o['fixture_id']].append(o)
    rows={k:[] for k in TARGETS};excluded={k:defaultdict(int) for k in TARGETS}
    def base(f,s):return {'fixture':f['fixture_id'],'league':f['league_id'],'week':dt(f['kickoff']).strftime('%G-%V'),
                          'kickoff':str(f['kickoff']),'y':outcome(f['home_goals'],f['away_goals']),'models':{}}
    current_weights=list(p.XI_LINE_WEIGHTS)
    for fid,s in latest_before_kickoff(snaps).items():
        f=fixtures[fid];ok=xi_weights.get(s['model_version_id'])==current_weights and reproduces(s)
        # P6: stored production probabilities versus the market at the snapshot's creation time.
        market=consensus(odds.get(fid,[]),created(s))
        if market is None:excluded['P6']['no_complete_prior_market']+=1
        else:
            r=base(f,s);r['models']={'model':[s['p_home'],s['p_draw'],s['p_away']],'market':market};rows['P6'].append(r)
        if not ok:
            for k in ('P3','P4'):excluded[k]['not_reproducible_by_current_formula']+=1
            continue
        # P4: availability adjustment on versus off, in the injury-model competitions.
        if s['league_id'] in config.INJURY_MODEL_LEAGUES:
            r=base(f,s);r['models']={'production':rescore(s),'no_availability':rescore(s,missing=False)}
            r['adjusted']=bool(s['inputs'].get('home_missing') or s['inputs'].get('away_missing'));rows['P4'].append(r)
        else:excluded['P4']['not_injury_model_competition']+=1
        # P3: re-score with the official XI in place of the predicted XI.
        if not complete(s['inputs'].get('predicted_lines')):
            excluded['P3']['no_complete_predicted_lines']+=1;continue
        sides=[official_lines(s,team,lineups,officials) for team in (f['home_team_id'],f['away_team_id'])]
        if any(l is None for l,_ in sides):excluded['P3']['no_aligned_official_XI']+=1;continue
        r=base(f,s);r['models']={'predicted_XI':rescore(s),'official_XI':rescore(s,lines=[sides[0][0],sides[1][0]])}
        r['official_hours_before_kickoff']=min(h for _,h in sides);r['official_recorded_before_kickoff']=r['official_hours_before_kickoff']>0
        rows['P3'].append(r)
    # P7: earliest snapshot at least a week ahead; vary the year-ahead Current weight only.
    for fid,s in earliest_ahead(snaps,P7_MIN_DAYS).items():
        f=fixtures[fid];i=s['inputs'];days=(dt(s['effective_at'])-dt(s['model_reference_at'])).total_seconds()/86400
        same=all(abs(year_rank(i[f'{side}_current_rank'],i[f'{side}_lt_algo'],days,p.MATCH_RANK_NOW_YEAR)-i[f'{side}_match_rank'])<=1e-6
                 for side in ('home','away'))
        if not same or not reproduces(s):excluded['P7']['not_reproducible_by_current_formula']+=1;continue
        r=base(f,s);r['days_ahead']=days
        for y in P7_GRID:
            r['models'][str(y)]=rescore(s,h_rank=year_rank(i['home_current_rank'],i['home_lt_algo'],days,y),
                                          a_rank=year_rank(i['away_current_rank'],i['away_lt_algo'],days,y))
        rows['P7'].append(r)
    return rows,{k:dict(v) for k,v in excluded.items()}


def paired(rows,a,b,repeats=2000):
    """Mean log-loss difference a-b with a paired UTC-week cluster bootstrap interval."""
    blocks=defaultdict(list)
    for r in rows:blocks[r['week']].append(loss(r['models'][a],r['y'])-loss(r['models'][b],r['y']))
    values=[(sum(v),len(v)) for v in blocks.values()];n=sum(c for _,c in values)
    mean=sum(x for x,_ in values)/n if n else None
    if len(values)<8:return {'delta_log_loss':mean,'weeks':len(values),'ci95':None,'reason':'fewer than 8 weekly blocks'}
    rng=random.Random(20260927);draws=[]
    for _ in range(repeats):
        sample=rng.choices(values,k=len(values));draws.append(sum(x for x,_ in sample)/sum(c for _,c in sample))
    draws.sort()
    return {'delta_log_loss':mean,'weeks':len(values),'ci95':[draws[int(.025*repeats)],draws[int(.975*repeats)]]}


def reestimate(rows,a,b,delta):
    """Blinded one-time sample-size re-estimate: SD of paired differences only, never their mean."""
    d=[loss(r['models'][a],r['y'])-loss(r['models'][b],r['y']) for r in rows]
    m=sum(d)/len(d);sd=math.sqrt(sum((x-m)**2 for x in d)/(len(d)-1))
    return {'n':len(d),'sd':sd,'fixtures_required':max(REESTIMATE_AT,math.ceil(((1.959964+.841621)*sd/delta)**2))}


COMPARISONS={'P3':('official_XI','predicted_XI',.002),'P4':('production','no_availability',.002),
             'P6':('model','market',.01),'P7':(None,'0.2',.002)}


def analyse(key,rows):
    models=list(rows[0]['models']) if rows else []
    metrics={m:probability_metrics([r['models'][m] for r in rows],[r['y'] for r in rows]) for m in models}
    a,b,delta=COMPARISONS[key]
    if key=='P7':
        rows=sorted(rows,key=lambda r:(r['kickoff'],r['fixture']));half=len(rows)//2
        select,confirm=rows[:half],rows[half:]
        chosen=min(P7_GRID,key=lambda y:sum(loss(r['models'][str(y)],r['y']) for r in select))
        return {'selection_n':len(select),'confirmation_n':len(confirm),'selected_year_weight':chosen,
                'confirmation':paired(confirm,str(chosen),b) if str(chosen)!=b else 'production weight selected',
                'metrics_confirmation':{m:probability_metrics([r['models'][m] for r in confirm],[r['y'] for r in confirm]) for m in models},
                'threshold':delta}
    out={'comparison':f'{a} minus {b}','threshold':delta,'paired':paired(rows,a,b),'metrics':metrics}
    if key=='P4':out['adjusted_fixtures_only']=paired([r for r in rows if r['adjusted']],a,b)
    if key=='P3':
        out['operational_subset_recorded_before_kickoff']=paired([r for r in rows if r['official_recorded_before_kickoff']],a,b)
        hours=sorted(r['official_hours_before_kickoff'] for r in rows);out['official_hours_before_kickoff_median']=hours[len(hours)//2]
    if key=='P6':
        out['disagreement_over_10pp']=paired([r for r in rows if max(abs(x-y) for x,y in zip(r['models']['model'],r['models']['market']))>.10],a,b)
    return out


def extract():
    from dotenv import dotenv_values
    import psycopg
    from psycopg.rows import dict_row
    url=dotenv_values('.env')['DATABASE_URL'].strip()
    with psycopg.connect(url,connect_timeout=15,options='-c default_transaction_read_only=on',row_factory=dict_row) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY');c.execute("SET LOCAL statement_timeout='300s'")
        q=lambda sql:c.execute(sql,binary=True).fetchall()
        data={'extracted_at':c.execute('select now() t').fetchone()['t']}
        # Regulation-time results only; extra-time and penalty matches are excluded, not relabelled.
        data['fixtures']=q("""select fixture_id,kickoff,league_id,home_team_id,away_team_id,home_goals,away_goals from fixtures
            where status_short='FT' and home_goals is not null and away_goals is not null
              and fixture_id in (select fixture_id from match_prediction_snapshots where source='prospective')""")
        ids=[f['fixture_id'] for f in data['fixtures']]
        data['snapshots']=c.execute("""select fixture_id,league_id,model_version_id,source,captured_at,created_at,effective_at,model_reference_at,
            p_home,p_draw,p_away,inputs from match_prediction_snapshots where source='prospective' and fixture_id=any(%s)""",[ids],binary=True).fetchall()
        data['versions']=q('select model_version_id,configuration from model_versions')
        data['lineups']=c.execute("""select fixture_id,team_id,source,captured_at,created_at,selection_inputs from lineup_prediction_snapshots
            where fixture_id=any(%s)""",[ids],binary=True).fetchall()
        data['officials']=c.execute('select fixture_id,team_id,captured_at,players from official_lineup_snapshots where fixture_id=any(%s)',[ids],binary=True).fetchall()
        data['odds']=c.execute("""select fixture_id,bookmaker_id,selection,odds::float8 odds,captured_at,created_at from odds_observations
            where market_id=1 and fixture_id=any(%s)""",[ids],binary=True).fetchall()
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--unblind',choices=sorted(TARGETS),help='Compute outcome metrics for one protocol once its target is reached')
    parser.add_argument('--interim',action='store_true',help='Allow --unblind before target; output is labelled a protocol deviation')
    parser.add_argument('--reestimate',choices=sorted(TARGETS),help=f'One-time blinded sample-size re-estimate (needs {REESTIMATE_AT} fixtures)')
    args=parser.parse_args()
    data=extract();rows,excluded=build(data)
    accrual={k:{'accrued':len(v),'target':TARGETS[k],'weeks':len({r['week'] for r in v}),
                'reached':len(v if k!='P7' else v[len(v)//2:])>=TARGETS[k]} for k,v in rows.items()}
    accrual['P3']['official_XI_recorded_before_kickoff']=sum(r['official_recorded_before_kickoff'] for r in rows['P3'])
    status={'generated_at':datetime.now(timezone.utc).isoformat(),'extracted_at':str(data['extracted_at']),
            'evaluator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'accrual':accrual,'exclusions':excluded,'blinded':args.unblind is None}
    if args.reestimate:
        k=args.reestimate;a,b,delta=COMPARISONS[k]
        if k=='P7':sys.exit('P7 uses a fixed confirmation target; no re-estimation')
        if len(rows[k])<REESTIMATE_AT:sys.exit(f'{k}: {len(rows[k])} fixtures accrued; re-estimation needs {REESTIMATE_AT}')
        status['reestimate']={k:reestimate(rows[k],a,b,delta)}
    if args.unblind:
        k=args.unblind
        if not accrual[k]['reached'] and not args.interim:
            sys.exit(f'{k}: {accrual[k]["accrued"]} of {TARGETS[k]} fixtures; refusing to unblind before the registered target')
        status['results']={k:analyse(k,rows[k])}
        if not accrual[k]['reached']:status['results'][k]['label']='INTERIM - protocol deviation; not decision-grade'
        (ROOT/f'results_{k}.json').write_text(json.dumps(status,indent=2,default=str)+'\n')
    else:
        (ROOT/'status.json').write_text(json.dumps(status,indent=2,default=str)+'\n')
    print(json.dumps({k:status[k] for k in ('accrual','reestimate') if k in status},indent=2,default=str))

if __name__=='__main__':main()
