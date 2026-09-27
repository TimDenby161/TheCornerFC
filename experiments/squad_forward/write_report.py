"""Render numerical outputs of the frozen forward squad experiment."""
import json
from pathlib import Path
ROOT=Path(__file__).parent
r=json.loads((ROOT/'results.json').read_text())
B={'baseline':'Baseline only','current':'Current only','blend':'Existing 0.6/0.4 blend','both':'Current + Baseline separately'}
M={'club_only':'Club only','raw_squad':'+ Raw squad','residual_squad':'+ Squad residual',
   'history_only':'+ Embedded club history','history_raw':'+ History + raw squad','history_neutral':'+ History + neutral squad'}
T={'goal_difference':'Mean goal difference','points':'Points per game','adjusted_goal_difference':'Opponent/venue-adjusted goal difference'}
def gain(m,base):return 100*(1-m['mse']/base['mse'])
def ci(d):
 a=d['ci95']
 return f'{a[0]:+.5f} to {a[1]:+.5f}' if a else 'insufficient clusters'
def a(h,t='goal_difference',b='both'):return r['horizons'][str(h)][t][b]
lines=['# Does squad strength add forward information beyond club ratings?','',
'**Recommendation: retain production unchanged. Take a separate, context-neutral squad signal into prospective shadow forecasting; do not feed raw squad strength into club ratings.**','',
'There is evidence of modest incremental forecast information, not just a recycled club-strength term. A neutral squad component improves next-10/20-match raw goal-difference and points forecasts after controlling for both Current and Baseline strength and the club levels embedded in player ratings. However, opponent-adjusted gains are smaller, the 20-match adjusted result is uncertain, and several subgroup effects fail to replicate clearly. The experiment therefore does not establish a robust independent club-ability signal suitable for deployment.','',
'## Design, provenance and scope','',
f'- Input: the prior frozen player experiment ({r["provenance"]["fixtures"]:,} completed fixtures; last observed kickoff {r["provenance"]["last_fixture"]}). No new database queries or API requests were needed for this experiment.',
'- Player scores use prior 20 appearances within 540 days and pre-2022 statistical normalization. This is a chronological reconstruction of the rolling match-player formula, not a prospective archive of website career/season ratings. Centre-back team_xga was unavailable in early training and is omitted consistently.',
'- Squad strength is the prior-five-match-minutes-weighted mean of eligible recently observed players. Require at least eleven players, including a goalkeeper, each with at least 180 historical minutes. It represents observed playing resources, not the registered squad or confirmed transfer signings. New signings enter after an observed appearance; departures can persist in the previous-five-match pool.',
'- Anchor every fifth observed club match. Predict average performance over the immediately upcoming 5, 10 or 20 observed completed league matches, requiring a full horizon within 365 days.',
'- Training anchors: January 2022–June 2023; validation: July 2023–June 2024; test: July 2024 onward. **Training labels must finish before validation starts; validation labels must finish before test starts.** The same eligible rows are used by every model within an endpoint/horizon.',
'- Validation MSE selects augmentation shrinkage from 0, .25, .5, .75, 1. Refit coefficients on training+validation and apply that selected shrinkage to the held-out test. Baseline and historical-club-control models are OLS; their player additions are shrunk against the corresponding baseline.',
'- Common baseline controls: competition, month sine/cosine and early season, in addition to rank and its square. The fourth, stricter baseline retains Current and Baseline separately, their squares and interaction. This prevents a squad feature from being credited merely for undoing the fixed blend.',
'- The blend is the production near-anchor 0.6 Current / 0.4 Baseline rule. We do not test the production year-ahead interpolation curve or claim measured improvement over the entire deployed match model.',
'- Target adjustment uses the opponent blend **frozen at the anchor**, plus home advantage estimated before 2022. It never uses future opponent ratings. Actual future opponents define this retrospective adjusted target; they are not future-information predictors.',
'- No production formulas, rating tables, database rows, migrations or deployed model inputs were changed.','',
'## Chronological samples and boundary exclusions','',
'| Horizon | Training anchors | Validation anchors | Test anchors | Test clubs | Adjusted-target test anchors | Purged crossing split boundaries |',
'|---|---:|---:|---:|---:|---:|---:|']
for h in (5,10,20):
 z=a(h);lines.append(f'| {h} matches | {z["train_n"]:,} | {z["validation_n"]:,} | {z["test_n"]:,} | {z["test_clubs"]} | {a(h,"adjusted_goal_difference")["test_n"]:,} | {r["provenance"]["diagnostics"][f"h{h}_purged_boundary"]:,} |')
lines+=['','Adjusted targets require a known pre-anchor opponent strength for every future opponent, so their sample is smaller. Results across different horizons are not directly comparable as identical populations; results across models within each table are paired. “All clubs” means all eligible clubs in the covered league dataset, not worldwide coverage.','',
'## Baseline, Current and blend comparisons','',
'Lower MSE is better. Raw and residual squad additions have numerically identical predictions here, so they share one column. Positive percentage improvement means lower test MSE. These are averaged future outcomes, not single-match probability scores.','',
'| Target | Horizon | Club baseline | Club-only MSE | + Raw/residual squad MSE | Improvement | Paired Δ MSE 95% CI |',
'|---|---:|---|---:|---:|---:|---|']
for target in T:
 for h in (5,10,20):
  for baseline in B:
   z=a(h,target,baseline)['models'];m=z['raw_squad'];base=z['club_only']
   lines.append(f'| {T[target]} | {h} | {B[baseline]} | {base["mse"]:.5f} | {m["mse"]:.5f} | {gain(m,base):.2f}% | {ci(m["delta_vs_club"])} |')
lines+=['','The fixed blend is a stronger simple baseline than Current alone in these held-out forecasts. Adding raw squad strength to Current alone therefore overstates the practical gain available relative to the existing blend. Against the blend, raw squad additions improve GD MSE by 0.71%, 1.62% and 2.32% at 5/10/20 matches, respectively.','',
'## Circularity and genuinely incremental information','',
f'Raw squad strength correlates **{a(10,b="blend")["raw_squad_vs_blend_test_correlation"]:.3f}** with the existing blend on the ten-match test sample. Much of its level is already club information.',
'',
'**Residualization is not an independent test by itself.** The squad residual is raw squad strength minus its training-only expectation from the complete club baseline. Adding either variable to that same linear baseline spans the same predictors. Predictions agree to numerical precision (maximum differences recorded in results.json). A smaller residual correlation does not prove new information.',
'',
'The stronger test below keeps both club ratings separately, adds the squad’s embedded historical club-strength mean and mean square, then adds either raw squad rating or the neutral squad component. Neutral ratings keep the existing statistical/position transformation but fix the explicit club-strength input to 1000. The remaining statistics can still reflect club tactics and environment; “neutral” does not mean causal intrinsic talent.','',
'| Target | Horizon | Strong club/history baseline MSE | + Raw squad MSE | + Neutral squad MSE | Neutral improvement | Neutral Δ MSE 95% CI |',
'|---|---:|---:|---:|---:|---:|---|']
for target in T:
 for h in (5,10,20):
  z=a(h,target)['models'];base=z['history_only'];m=z['history_neutral']
  lines.append(f'| {T[target]} | {h} | {base["mse"]:.5f} | {z["history_raw"]["mse"]:.5f} | {m["mse"]:.5f} | {gain(m,base):.2f}% | {ci(m["delta_vs_history"])} |')
lines+=['','This supports some incremental statistical information beyond explicit club scaling: the neutral component retains gains, and raw squad strength is not materially necessary to obtain them. But adjusted-performance gains are only 0.38%, 0.76% and 0.69%; the 20-match interval includes zero. The review criterion of at least 1% MSE improvement beyond historical-club controls with consistent support across direct and adjusted outcomes is not satisfied overall.','',
'## Cohorts: strongest controls plus neutral squad','',
'All cohorts are defined at prediction time and overlap. Promotion/relegation requires observed prior-season membership in mapped domestic tiers. Missing membership is unknown. Early season is fewer than five prior league-season matches. The transfer-window proxy is January/July/August in mapped European leagues, not exact registration deadlines. Large squad change is at least 0.35 total-variation distance between minutes shares in the previous five and preceding five matches; it also captures injuries, rotation and coverage effects.','',
'The ten-match horizon illustrates the cohort results; all 5/10/20 grids and intervals are retained in results.json. Negative Δ MSE favours adding the neutral component.','',
'| Cohort | GD/points anchors | Clubs | Adjusted anchors | GD improvement | GD Δ MSE 95% CI | Points improvement | Adjusted GD improvement | Adjusted Δ MSE 95% CI |',
'|---|---:|---:|---:|---:|---|---:|---:|---|']
for cohort in ('all','promoted','relegated','early_season','transfer_window_proxy','large_squad_change'):
 gs=[a(10,target)['cohorts'][cohort] for target in T]
 gains=[gain(g['models']['history_neutral'],g['models']['history_only']) for g in gs]
 lines.append(f'| {cohort} | {gs[0]["n"]:,} | {gs[0]["clubs"]} | {gs[2]["n"]:,} | {gains[0]:.2f}% | {ci(gs[0]["models"]["history_neutral"]["delta_vs_history"])} | {gains[1]:.2f}% | {gains[2]:.2f}% | {ci(gs[2]["models"]["history_neutral"]["delta_vs_history"])} |')
lines+=['',
'- **Promoted:** promising direct-outcome gains at ten matches (3.32% GD; 2.77% points), but only 0.11% adjusted-GD improvement. At twenty matches adjusted GD worsens by 1.57%, with a wide interval. Do not treat the direct gains as confirmed independent ability measurement.',
'- **Relegated:** limited to 19 test clubs at the ten/twenty-match horizons; longer-horizon intervals are wide. No reliable special coefficient follows.',
'- **Early season:** no clear long-horizon advantage; ten-match GD and points gains are under 1%, with intervals spanning zero.',
'- **Transfer-window calendar proxy:** direct point estimates are positive, but intervals are generally inconclusive. Calendar months are not verified transfer events.',
'- **Large observed squad change:** the most promising targeted follow-up. At ten matches the neutral component improves GD by 1.83%, points by 1.72%, and adjusted GD by 1.27%, with pointwise club-bootstrap intervals below zero. This subgroup was predefined, but multiple comparisons and noisy turnover measurement still require prospective confirmation. At twenty matches the adjusted-GD interval crosses zero.','',
'## Temporal dependence and stability','',
'Anchors every five matches overlap for the 10/20-match targets. The principal bootstrap resamples entire clubs, retaining within-club horizon overlap. As a sensitivity, circular moving blocks of 26 calendar weeks retain stretches of common calendar shocks. The test period supplies only about four such blocks, so those intervals should not be read as abundant independent temporal evidence. Neither method fully captures all shared-opponent dependence or model-fitting uncertainty.','',
'| Target | Horizon | Club-cluster Δ MSE 95% CI | 26-week-block Δ MSE 95% CI | Nonoverlapping test anchors | Nonoverlapping improvement |',
'|---|---:|---|---|---:|---:|']
for target in T:
 for h in (5,10,20):
  z=a(h,target);m=z['models']['history_neutral'];g=z['cohorts']['nonoverlapping']
  lines.append(f'| {T[target]} | {h} | {ci(m["delta_vs_history"])} | {ci(m["calendar_block_delta_vs_history"])} | {g["n"]:,} | {gain(g["models"]["history_neutral"],g["models"]["history_only"]):.2f}% |')
lines+=['','Nonoverlapping sensitivity selects every Hth club-match anchor from the test predictions of the same fitted models; it is not another tuning exercise. Direct-outcome gains persist. The uncertain twenty-match adjusted result also persists.','',
'| Horizon | Period | GD improvement | Points improvement | Adjusted-GD improvement |',
'|---:|---|---:|---:|---:|']
for h in (5,10,20):
 for period in ('2024-25','2025-onward'):
  values=[]
  for target in T:
   g=a(h,target)['cohorts'][period]['models'];values.append(gain(g['history_neutral'],g['history_only']))
  lines.append(f'| {h} | {period} | '+' | '.join(f'{v:.2f}%' for v in values)+' |')
lines+=['','Twenty-match adjusted performance is slightly worse in the earlier period and better in the later one. That limits claims of stable long-horizon independent skill information.','',
'## Limits and recommended next experiment','',
'- These are forward chronological predictions with purged labels, but reconstructed inputs and statistical weights were developed using historical data, including these years. They are not pristine prospective or untouched development holdouts.',
'- Observed completed league matches may differ from the next actual fixtures when a club exits coverage. Full-horizon requirements select clubs that remain observable; relegation/transfer coverage exits are not missing at random.',
'- Current registered squads, signed-but-not-yet-observed players, reliable historical injury availability and prospective squad component snapshots are unavailable. Deployment changes do not equal transfer changes.',
'- Subgroup intervals are pointwise and not adjusted for the many horizons, outcomes, baselines and cohorts. A positive subgroup result alone is not a production rule.',
'- Effects on direct performance need not be effects on intrinsic club ability. Adjusting for frozen opponent strength reduces some of the apparent gain, particularly among promoted clubs.',
'',
'**Next experiment:** freeze the production club model and run a separate ten-match shadow forecast. Capture dated registered squads, eligibility/availability, incoming/outgoing player IDs, prior minutes, the neutral player component and its club-history controls before outcomes. Preregister the full sample and a large-squad-change interaction, rather than fitting a special promoted/relegated coefficient from these results. Require replicated improvements in both raw and opponent-adjusted performance, use verified transfer events instead of month proxies, retain coverage exits, and select the evaluation duration from a club-clustered power analysis.',
'',
'The experiment supports investigating a separate forward-looking squad forecast feature. **It does not support feeding raw squad rating into production club strength, which would risk reinforcing the club information already present in player ratings. No implementation changes were made.**','',
'## Reproduction','',
'```bash',
'/tmp/thecornerfc-experiment-venv/bin/pip install -r experiments/player_club_strength/requirements.txt',
'# Requires the prior frozen player replay and membership caches; no database access:',
'OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 /tmp/thecornerfc-experiment-venv/bin/python experiments/squad_forward/run.py',
'# To refit using the already frozen squad anchors:',
'OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 /tmp/thecornerfc-experiment-venv/bin/python experiments/squad_forward/run.py --cached-rows',
'/tmp/thecornerfc-experiment-venv/bin/python experiments/squad_forward/write_report.py',
'/tmp/thecornerfc-experiment-venv/bin/python -m unittest discover -s tests -p "test_squad_forward_experiment.py"',
'```','',
f'Run source SHA-256: `{r["code_sha256"]}`. Frozen squad-row SHA-256: `{r["rows_sha256"]}`. Source-data, membership and upstream replay fingerprints are recorded in `results.json`. Frozen inputs remain in ignored `.cache/`; tracked artifacts contain no credentials.','']
(ROOT/'REPORT.md').write_text('\n'.join(lines))
