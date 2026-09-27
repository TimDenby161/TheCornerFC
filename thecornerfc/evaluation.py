"""Read-only chronological evaluation of captured evidence, never reconstructed implicitly."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import hashlib
from decimal import Decimal
import math
from pathlib import Path


def average(values):
    values=list(values)
    return sum(values)/len(values) if values else None


def bucket(p):
    lo=min(9,max(0,int(p*10)))
    return f'{lo/10:.1f}-{(lo+1)/10:.1f}'


def calibration(probabilities, outcomes):
    bins=defaultdict(list)
    for p,y in zip(probabilities,outcomes):
        bins[bucket(p)].append((p,y))
    return {k:{'n':len(v),'mean_probability':average(p for p,y in v),
               'observed_rate':average(y for p,y in v)} for k,v in sorted(bins.items())}


def probability_metrics(probabilities, outcomes):
    """Multiclass Brier is summed across classes (range 0..2), not divided by K."""
    if len(probabilities)!=len(outcomes):
        raise ValueError('Probability and outcome lengths differ')
    for p,y in zip(probabilities,outcomes):
        if not p or not all(math.isfinite(x) and 0<=x<=1 for x in p) or abs(sum(p)-1)>1e-6 or not 0<=y<len(p):
            raise ValueError('Invalid probability vector or outcome')
    n=len(outcomes)
    return {'n':n,'accuracy':average(int(max(range(len(p)),key=p.__getitem__)==y) for p,y in zip(probabilities,outcomes)),
            'log_loss':average(-math.log(max(p[y],1e-15)) for p,y in zip(probabilities,outcomes)),
            'brier':average(sum((q-int(k==y))**2 for k,q in enumerate(p)) for p,y in zip(probabilities,outcomes)),
            'calibration':{str(k):calibration([p[k] for p in probabilities],[int(y==k) for y in outcomes])
                           for k in range(len(probabilities[0]))} if n else {}}


def binary_metrics(probabilities,outcomes):
    result=probability_metrics([[1-p,p] for p in probabilities],outcomes)
    result['brier']=average((p-y)**2 for p,y in zip(probabilities,outcomes))
    result['calibration']=calibration(probabilities,outcomes)
    return result


def group_metrics(rows,key,fn):
    groups=defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row)
    return {name:fn(items) for name,items in sorted(groups.items())}


def match_metrics(rows):
    out=probability_metrics([r['probabilities'] for r in rows],[r['outcome'] for r in rows])
    scores=[r for r in rows if r.get('likely_score') is not None]
    out['exact_score']={'n':len(scores),'accuracy':average(r['likely_score']==r['actual_score'] for r in scores)}
    return out


def matches_report(rows):
    paired=[r for r in rows if r.get('market') is not None]
    return {'overall':match_metrics(rows),
            'by_competition':group_metrics(rows,lambda r:r['league_id'],match_metrics),
            'by_model_version':group_metrics(rows,lambda r:r['model_version_id'],match_metrics),
            'by_probability_bucket':group_metrics(rows,lambda r:bucket(max(r['probabilities'])),match_metrics),
            'paired_market':{'n':len(paired),'model':match_metrics(paired),
                'market':probability_metrics([r['market'] for r in paired],[r['outcome'] for r in paired])},
            'by_disagreement':group_metrics(paired,lambda r:('different_favourite' if
                max(range(3),key=r['probabilities'].__getitem__)!=max(range(3),key=r['market'].__getitem__)
                else 'same_favourite'),match_metrics),
            'by_model_market_gap':group_metrics(paired,lambda r:bucket(max(abs(a-b) for a,b in zip(r['probabilities'],r['market']))),match_metrics)}


def lineup_metrics(rows):
    from .player_ratings import line_of
    correct=[];fp=fn=0;roles=[];lines=[];probs=[];outcomes=[]
    for r in rows:
        predicted={p['player']:p for p in r['players'] if p.get('predicted_starter')}
        actual={p['player']:p for p in r['official'] if p.get('starter')}
        shared=predicted.keys() & actual.keys()
        correct.append(len(shared));fp+=len(predicted.keys()-actual.keys());fn+=len(actual.keys()-predicted.keys())
        for pid in shared:
            a,b=predicted[pid],actual[pid]
            if a.get('role') and b.get('role'):
                roles.append(a['role']==b['role'])
            al=a.get('line');bl=line_of(b.get('role'),b.get('position'))
            if al and bl:
                lines.append(al==bl)
        for p in r['players']:
            if p.get('start_probability') is not None:
                probs.append(p['start_probability']);outcomes.append(int(p['player'] in actual))
    return {'n':len(rows),'correct_starters_mean':average(correct),'correct_starters_out_of_11':average(x/11 for x in correct),
            'false_positives':fp,'false_negatives':fn,
            'role_accuracy':{'n':len(roles),'accuracy':average(roles)},
            'line_accuracy':{'n':len(lines),'accuracy':average(lines)},
            'start_probability_metrics':binary_metrics(probs,outcomes)}


def horizon_bucket(hours):
    return '<1h' if hours<1 else '1-6h' if hours<6 else '6-24h' if hours<24 else '24h+'


def edge_bucket(edge):
    return '<0' if edge<0 else '0-0.05' if edge<.05 else '0.05-0.10' if edge<.1 else '0.10-0.20' if edge<.2 else '0.20+'


def betting_metrics(rows):
    settled=[r for r in rows if r.get('result') is not None]
    scored=[r for r in settled if r['result'] in ('win','loss')]
    stake=sum(float(r['stake_units']) for r in settled)
    pnl=sum(float(r['profit_units']) for r in settled)
    return {'n':len(rows),'settled_n':len(settled),'unsettled_n':len(rows)-len(settled),
            'void_n':sum(r['result']=='void' for r in settled),'stake':stake,'pnl':pnl,'roi':pnl/stake if stake else None,
            'average_odds':{'n':len(rows),'value':average(float(r['odds_taken']) for r in rows)},
            'model_probability':{'n':len(rows),'value':average(r['model_probability'] for r in rows)},
            'market_fair_probability':summarize(rows,'fair_probability'),
            'price_clv':summarize(settled,'price_clv'),'probability_movement':summarize(settled,'probability_movement'),
            'model':binary_metrics([r['model_probability'] for r in scored],[int(r['result']=='win') for r in scored]),
            'market':binary_metrics([r['fair_probability'] for r in scored if r['fair_probability'] is not None],
                                   [int(r['result']=='win') for r in scored if r['fair_probability'] is not None])}


def summarize(rows,field):
    values=[float(r[field]) for r in rows if r.get(field) is not None]
    return {'n':len(values),'value':average(values)}


def query(conn,sql,params=()):
    cur=conn.execute(sql,params)
    names=[c.name for c in cur.description]
    return [dict(zip(names,row)) for row in cur.fetchall()]


def load_matches(conn,args,market=True):
    """market=False skips the per-fixture odds lookups; every row's market is then None."""
    rows=query(conn,'''SELECT DISTINCT ON(s.fixture_id) s.*,f.ft_home,f.ft_away,f.status_short,
        f.home_goals,f.away_goals FROM match_prediction_snapshots s JOIN fixtures f USING(fixture_id)
        WHERE s.source=%s AND s.effective_at >= %s AND s.effective_at < %s
          AND s.captured_at<=%s AND s.created_at<=%s
          AND (%s='reconstruction' OR (s.captured_at<=s.effective_at-make_interval(secs=>%s)
               AND s.created_at<=s.effective_at-make_interval(secs=>%s)))
          AND s.effective_at=f.kickoff
          AND f.status_short IN ('FT','AET','PEN')
        ORDER BY s.fixture_id,s.captured_at DESC,s.snapshot_id DESC''',
        [args.source,args.start,args.end,args.as_of,args.as_of,args.source,args.hours_before*3600,args.hours_before*3600])
    from .paper_evidence import latest_quotes,market_evidence
    valid=[]
    for r in rows:
        h,a=r['ft_home'],r['ft_away']
        if r['status_short']=='FT':
            h=r['home_goals'] if h is None else h;a=r['away_goals'] if a is None else a
        if h is None or a is None:
            continue # Never substitute extra-time totals for unknown regulation scores.
        r.update(probabilities=[r['p_home'],r['p_draw'],r['p_away']],outcome=0 if h>a else 1 if h==a else 2,
                 actual_score=f'{h}-{a}',market=None)
        if not market:
            valid.append(r)
            continue
        cutoff=min(r['captured_at'],r['effective_at'])
        quotes=latest_quotes(conn,r['fixture_id'],1,cutoff,strict=True)
        books={}
        for oid,bm,sel,odd,captured in quotes:
            if sel in ('Home','Draw','Away'):
                books.setdefault(bm,{})[sel]=float(odd)
        fair,_=market_evidence(books,('Home','Draw','Away'),None)
        if fair:
            r['market']=[fair[s] for s in ('Home','Draw','Away')]
        r['market_observation_ids']=[q[0] for q in quotes]
        valid.append(r)
    return valid,{'selected':len(rows),'missing_regulation_score':len(rows)-len(valid)}


def load_lineups(conn,args):
    rows=query(conn,'''SELECT DISTINCT ON(s.fixture_id,s.team_id) s.*,o.players AS official,o.snapshot_id AS official_snapshot_id,
        o.captured_at AS official_captured_at FROM lineup_prediction_snapshots s
        LEFT JOIN LATERAL (SELECT * FROM official_lineup_snapshots o
            WHERE o.fixture_id=s.fixture_id AND o.team_id=s.team_id AND o.effective_at=s.effective_at
              AND o.captured_at<=%s AND o.created_at<=%s ORDER BY o.captured_at DESC,o.snapshot_id DESC LIMIT 1) o ON true
        WHERE s.source='prospective' AND s.effective_at >= %s AND s.effective_at < %s
          AND s.captured_at<=%s AND s.created_at<=%s AND s.created_at<s.effective_at
          AND s.captured_at<=s.effective_at-make_interval(secs=>%s)
          AND s.created_at<=s.effective_at-make_interval(secs=>%s)
          AND s.captured_at < coalesce((SELECT min(first_xi.captured_at) FROM official_lineup_snapshots first_xi
              WHERE first_xi.fixture_id=s.fixture_id AND first_xi.team_id=s.team_id
                AND first_xi.effective_at=s.effective_at),'infinity'::timestamptz)
        ORDER BY s.fixture_id,s.team_id,s.captured_at DESC,s.snapshot_id DESC''',
        [args.as_of,args.as_of,args.start,args.end,args.as_of,args.as_of,args.hours_before*3600,args.hours_before*3600])
    valid=[r for r in rows if r['official'] and len({p['player'] for p in r['official'] if p.get('starter')})==11]
    return valid,{'selected':len(rows),'missing_or_incomplete_official_xi':len(rows)-len(valid)}


def load_betting(conn,args):
    return query(conn,'''SELECT d.*,o.result,o.profit_units,o.price_clv,o.probability_movement,
        o.outcome_id,o.captured_at AS outcome_captured_at FROM paper_decisions d
        LEFT JOIN LATERAL (SELECT * FROM paper_outcomes o WHERE o.decision_id=d.decision_id
            AND o.captured_at<=%s AND o.created_at<=%s ORDER BY o.captured_at DESC,o.outcome_id DESC LIMIT 1) o ON true
        WHERE d.captured_at >= %s AND d.captured_at < %s AND d.captured_at<=%s AND d.created_at<=%s
          AND d.captured_at<d.effective_at
        ORDER BY d.captured_at,d.decision_id''',[args.as_of,args.as_of,args.start,args.end,args.as_of,args.as_of])


def load_fantasy(conn,args):
    """Latest prospective snapshot per gameweek/model version before the deadline (at the current
    known deadline), scored per player against the latest FPL-final (data_checked) points by as_of."""
    snaps=query(conn,'''SELECT DISTINCT ON(s.season,s.event_id,s.model_version_id) s.snapshot_id,s.season,s.event_id,
            s.model_version_id,s.input_capture_id,s.captured_at,s.effective_at,s.seconds_to_deadline,s.predictions,
            r.result_capture_id,r.captured_at AS result_captured_at
        FROM fantasy_prediction_snapshots s
        LEFT JOIN LATERAL (SELECT * FROM fpl_result_captures r WHERE r.season=s.season AND r.event_id=s.event_id
            AND r.data_checked AND r.captured_at<=%s AND r.created_at<=%s
            ORDER BY r.captured_at DESC,r.result_capture_id DESC LIMIT 1) r ON true
        WHERE s.source='prospective' AND s.effective_at >= %s AND s.effective_at < %s
          AND s.captured_at<=%s AND s.created_at<=%s AND s.created_at<s.effective_at
          AND s.captured_at<=s.effective_at-make_interval(secs=>%s)
          AND s.created_at<=s.effective_at-make_interval(secs=>%s)
          AND s.effective_at=(SELECT g.deadline FROM fpl_gameweeks g WHERE g.season=s.season AND g.event_id=s.event_id
              ORDER BY g.first_captured_at DESC,g.deadline DESC LIMIT 1)
        ORDER BY s.season,s.event_id,s.model_version_id,s.captured_at DESC,s.snapshot_id DESC''',
        [args.as_of,args.as_of,args.start,args.end,args.as_of,args.as_of,args.hours_before*3600,args.hours_before*3600])
    labelled=[s for s in snaps if s['result_capture_id'] is not None]
    points={}
    if labelled:
        for rid,pid,total in conn.execute('''SELECT result_capture_id,fpl_player_id,total_points FROM fpl_player_results
                                           WHERE result_capture_id=ANY(%s)''',[[s['result_capture_id'] for s in labelled]]).fetchall():
            points[rid,pid]=total
    rows=[];missing=0
    for s in labelled:
        for p in s['predictions']:
            actual=points.get((s['result_capture_id'],p['fpl_player_id']))
            if actual is None:
                missing+=1
                continue
            rows.append({k:s[k] for k in ('snapshot_id','season','event_id','model_version_id','input_capture_id','captured_at',
                         'effective_at','seconds_to_deadline','result_capture_id','result_captured_at')}
                        |{'fpl_player_id':p['fpl_player_id'],'player_id':p['fpl_player_id'],
                          'expected_points':float(p['expected_points']),'actual_points':actual})
    return rows,{'selected_snapshots':len(snaps),'snapshots_without_final_points':len(snaps)-len(labelled),
                 'predictions_without_player_result':missing}


def fantasy_metrics(rows):
    errors=[r['expected_points']-r['actual_points'] for r in rows]
    return {'n':len(rows),'snapshots':len({r['snapshot_id'] for r in rows}),
            'mae':average(abs(e) for e in errors),
            'rmse':math.sqrt(average(e*e for e in errors)) if errors else None,
            'bias':average(errors),
            'mean_expected':average(r['expected_points'] for r in rows),
            'mean_actual':average(r['actual_points'] for r in rows)}


def evaluate(conn,args):
    provenance={'source':args.source,'as_of':args.as_of.isoformat(),'start':args.start.isoformat(),'end':args.end.isoformat(),
                'hours_before':args.hours_before,'selection':'latest eligible snapshot per fixture/team; no current-state reconstruction',
                'period_basis':'decision capture time' if args.domain=='betting' else 'rating capture time' if args.domain=='players'
                    else 'known FPL deadline' if args.domain=='fantasy' else 'known kickoff',
                'official_policy':'latest official XI as of report cutoff; predictions must precede first observed official XI',
                'metric_conventions':'multiclass Brier sums classes; binary Brier is (p-y)^2; log probabilities clipped at 1e-15',
                'labels':'Match results are current database regulation-time results at evaluation, not immutable as-of result observations.'}
    if args.domain=='fantasy':
        provenance['labels']='Latest FPL points observation marked final (data_checked) and captured by as_of; corrections append.'
    coverage={}
    if args.domain in ('matches','clubs'):
        rows,coverage=load_matches(conn,args)
        if args.domain=='matches':
            metrics=matches_report(rows)
        else:
            metrics={'n':len(rows),'status':'experiment_evidence_only',
                     'description':'Club strengths embedded in match snapshots, not an independent club-rating validation target.',
                     'by_model_version':group_metrics(rows,lambda r:r['model_version_id'],lambda v:{'n':len(v)})}
    elif args.domain=='lineups':
        rows,coverage=load_lineups(conn,args)
        metrics={'overall':lineup_metrics(rows),'by_hours_before':group_metrics(rows,
            lambda r:horizon_bucket(r['seconds_to_kickoff']/3600),lineup_metrics),
            'by_model_version':group_metrics(rows,lambda r:r['model_version_id'],lineup_metrics)}
    elif args.domain=='betting':
        rows=load_betting(conn,args)
        metrics={'overall':betting_metrics(rows),'by_edge_bucket':group_metrics(rows,lambda r:edge_bucket(r['edge']),betting_metrics),
                 'by_strategy_version':group_metrics(rows,lambda r:r['strategy_version_id'],betting_metrics)}
    elif args.domain=='players':
        rows=query(conn,'''SELECT * FROM player_rating_snapshot_history
            WHERE captured_at >= %s AND captured_at < %s AND captured_at<=%s AND created_at<=%s
            ORDER BY captured_at,player_id''',[args.start,args.end,args.as_of,args.as_of])
        metrics={'n':len(rows),'players':len({r['player_id'] for r in rows}),'captures':len({r['capture_id'] for r in rows}),
                 'status':'experiment_evidence_only','description':'Observed rating trajectories; movement is not itself predictive validation.',
                 'by_model_version':group_metrics(rows,lambda r:r['model_version_id'],lambda v:{'n':len(v)})}
    else:
        rows,coverage=load_fantasy(conn,args)
        metrics={'overall':fantasy_metrics(rows),'by_model_version':group_metrics(rows,lambda r:r['model_version_id'],fantasy_metrics),
                 'by_gameweek':group_metrics(rows,lambda r:f"{r['season']}-GW{r['event_id']:02d}",fantasy_metrics),
                 'by_hours_before':group_metrics(rows,lambda r:horizon_bucket(r['seconds_to_deadline']/3600),fantasy_metrics)}
    rows.sort(key=lambda r:(r.get('captured_at',args.as_of),r.get('fixture_id',r.get('player_id',0))))
    result={'evaluation_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'generated_at':datetime.now(timezone.utc).isoformat(),'domain':args.domain,'n':len(rows),'provenance':provenance,'coverage':coverage,'metrics':metrics}
    if args.include_records:
        result['records']=rows
    return result


def run(args):
    result=_read(args)
    text=json.dumps(result,default=json_value,allow_nan=False,indent=2)
    if args.output:
        Path(args.output).write_text(text+'\n',encoding='utf-8')
    print(text)
    return 0


def json_value(value):
    if isinstance(value,Decimal):
        return float(value)
    if isinstance(value,datetime):
        return value.isoformat()
    raise TypeError(f'Unsupported report value: {type(value).__name__}')


def _read(args):
    from .db import connect
    # Read-only repeatable-read transaction, even when the CLI is run in production.
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        result=evaluate(conn,args)
    return result


def add_parser(sub):
    parser=sub.add_parser('evaluate',help='Evaluate immutable evidence without API calls or database writes')
    parser.add_argument('domain',choices=['matches','lineups','clubs','players','betting','fantasy'])
    parser.add_argument('--source',choices=['prospective','reconstruction'],default='prospective')
    parser.add_argument('--from',dest='start',type=parse_time)
    parser.add_argument('--to',dest='end',type=parse_time)
    parser.add_argument('--as-of',type=parse_time,default=None)
    parser.add_argument('--hours-before',type=float,default=0)
    parser.add_argument('--output',help='Write JSON report to this path')
    parser.add_argument('--include-records',action='store_true',help='Include immutable experiment rows and selected labels')


def parse_time(raw):
    value=datetime.fromisoformat(raw.replace('Z','+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def prepare(args):
    args.as_of=args.as_of or datetime.now(timezone.utc)
    args.end=args.end or args.as_of
    args.start=args.start or args.end-timedelta(days=90)
    if args.start>=args.end or not math.isfinite(args.hours_before) or args.hours_before<0:
        raise ValueError('Use an increasing date range and non-negative hours-before')
    if args.source=='reconstruction' and args.domain not in ('matches','clubs'):
        raise ValueError('Reconstruction evaluation is supported only for match snapshot evidence')
    return args
