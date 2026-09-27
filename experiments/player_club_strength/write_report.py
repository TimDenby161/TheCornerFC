"""Render the completed offline experiment without any database/API access."""
import json
from pathlib import Path
ROOT=Path(__file__).parent
r=json.loads((ROOT/'results.json').read_text())
LABELS={'club_controls':'Context controls only','scaled':'Production-formula scaled',
        'preclub_percentile':'Pre-club percentile','fixed_club':'Fixed-club formula','residual':'Club residual'}
def ci(m):
 a=m.get('ci95')
 return f'{a[0]:+.6f} to {a[1]:+.6f}' if a else 'insufficient clusters'
def f(x):return 'n/a' if x is None else f'{x:.3f}'
lines=['# Does player rating depend too strongly on club strength?','',
'**Recommendation: do not remove or weaken production club scaling on this evidence. Keep production unchanged; collect prospective component snapshots and test player information against a stronger club-history baseline.**','',
'Strong club dependence is confirmed, but the out-of-sample results do not support broadly removing it. After controlling for historical club level, scaled, fixed-club and residual player signals improve future provider-rating MSE by about 2.1%; their differences are practically negligible. Future-minutes gains are about 0.25%. Scaled player information retains a small match-prediction benefit beyond club history, below the practical threshold set for this experiment. Transfer direction exposes a useful follow-up hypothesis rather than a universal winning representation.','',
'## Scope and chronological controls','',
f'- Frozen database extract: {r["fixture_n"]:,} completed regulation-time fixtures and {r["appearance_n"]:,} positive-minute appearances, {r["first_kickoff"]} through {r["last_kickoff"]}. Extracted {r["data_extracted_at"]}.',
f'- Immutable captures: {len(r["captures"])} observations, from {r["captures"][0][0]} to {r["captures"][-1][0]}; their model-version IDs differ. This is insufficient for meaningful prospective transfer validation.',
'- Norms, league rating offsets and percentile references use pre-2022 records only. Prediction training: January 2022–June 2023; validation: July 2023–June 2024; held-out test: July 2024 onward. Validation selects regularization, then coefficients are refitted on training + validation.',
'- Last-20-appearance / 540-day player windows use only prior matches. All fixtures sharing a kickoff are scored before any of their results update the windows. Every variant uses identical eligible observations within each endpoint.',
'- Current website season/career ratings are audited descriptively. They are not used as historical predictors because later career evidence and rebuilt history may leak. The predictive experiment replays the rolling match-player formula with chronological reference distributions; it is not an exact backtest of website season ratings.',
'- Centre-back team-xG-against is unavailable in the early normalization sample and is omitted consistently in every variant. No production functions or constants were changed.',
'- All database extraction was READ ONLY / REPEATABLE READ. No API-Football calls, migrations, writes, or production rating changes. The restricted database role exposed zero rows, so the main connection was used with writes disabled.','',
'## What is being compared?','',
'1. **Production-formula scaled**: existing `final_rank(percentile, window_club_strength, position)`, with chronological inputs. The active formula uses an additive club-level base, a position-weighted statistical adjustment and a soft ceiling. Dividing today’s rating by a club factor would not recover the pre-club signal.',
'2. **Pre-club percentile**: the weighted, shrunk statistical score converted to a position-specific percentile using only the pre-2022 reference. This is not context-free ability: passing volume, provider ratings and other statistics can themselves depend on team tactics and competition.',
'3. **Fixed-club formula**: the same `final_rank` transformation with club strength fixed at 1000 for everyone. Removes explicit club scaling while retaining position offsets, elite bonuses and the ceiling.',
'4. **Club residual**: scaled rating minus a position-specific quadratic expectation from window club strength, fitted on prediction-training observations only. Residuals are not guaranteed uncorrelated with club strength out of sample.',
'', '## 1–2. Correlation by position and within-club distributions','',
f'Current website exports: club rankings timestamp {r["current_snapshot"]["rankings_generated_at"]}. Players must have a linked club with a published LT strength. The between-club fraction below is descriptive, unadjusted, and inflated when clubs have few players; it is not the fraction causally explained by strength. Within-club summaries require at least three players in the same position group.','',
'| Position | Players | Clubs | Pearson | Spearman | Between-club variance fraction | Median within-club SD | Median within-club P90−P10 |',
'|---|---:|---:|---:|---:|---:|---:|---:|']
for pos,m in sorted(r['current_snapshot']['positions'].items()):
 lines.append(f'| {pos} | {m["n"]:,} | {m["clubs"]} | {f(m["pearson"])} | {f(m["spearman"])} | {f(m["between_club_variance_fraction"])} | {f(m["median_within_club_sd"])} | {f(m["median_within_club_p90_p10"])} |')
lines+=['','Full-backs show the strongest association in this export. Centre-backs and defensive midfielders are also strongly associated with club strength. Within-club spreads remain material, so the rating is not simply a club label. Better clubs recruiting better players, role/tactical opportunity and the explicit formula all contribute; these correlations cannot separate them.','',
'Historical held-out correlations below use one observation per player per UTC month (latest eligible observation) to reduce fixture-frequency weighting; they remain repeated-player descriptive statistics. Club strength here is the minutes-weighted historical window club input, rather than the current employer’s strength.','',
'| Position | Player-months | Scaled Pearson | Pre-club Pearson | Fixed-club Pearson | Residual Pearson |',
'|---|---:|---:|---:|---:|---:|']
for pos,m in r['historical_correlations'].items():
 lines.append('| '+pos+f' | {m["n"]:,} | '+' | '.join(f(m['variants'][v]['pearson']) for v in ('scaled','preclub_percentile','fixed_club','residual'))+' |')
lines+=['','## 3–5. Transfers and direction of club-strength change','',
'Transfers are proxies inferred from changes of observed club in covered domestic competitions, with no more than 365 days between observations. Strong→weak and weak→strong require at least 50 LT points at the move. They are not verified registration transactions. Compare the last old-club pre-match score with pre-match scores at the fifth and twentieth new-club appearances. Early stability is partly mechanical because the window retains old-club appearances. The twentieth-appearance cohort is a selected group that stayed observable and played enough games; it still has one old appearance in a full 20-game pre-match window. Residual transfer trajectories hold the expected-rating position group fixed at transfer entry; actual roles can change.','',
'| Checkpoint | Direction | Moves | Players | Scaled mean change | Fixed-club mean change | Residual mean change | Scaled pre/post correlation |',
'|---|---|---:|---:|---:|---:|---:|---:|']
for checkpoint,key in [('5th','transfer_stability'),('20th','transfer_stability_20th')]:
 for direction,g in r[key].items():
  v=g['variants']
  lines.append(f'| {checkpoint} | {direction} | {g["n"]:,} | {g["players"]:,} | {f(v["scaled"]["mean_change"])} | {f(v["fixed_club"]["mean_change"])} | {f(v["residual"]["mean_change"])} | {f(v["scaled"]["pre_vs_post_pearson"])} |')
lines+=['','| 20th-appearance cohort | Scaled change 95% CI | Fixed-club change 95% CI | Scaled change vs club-change correlation | Fixed-club change vs club-change correlation |',
'|---|---|---|---:|---:|']
for direction,g in r['transfer_stability_20th'].items():
 v=g['variants'];lines.append(f'| {direction} | {ci(v["scaled"]["mean_change_ci"])} | {ci(v["fixed_club"]["mean_change_ci"])} | {f(v["scaled"]["change_vs_club_change"])} | {f(v["fixed_club"]["change_vs_club_change"])} |')
lines+=['','Scaling makes ratings follow the new club’s level, while unscaled statistical output can improve in an easier environment and decline in a harder one. This is compatible with useful competition adjustment as well as excessive club dependence. Transfer continuity alone cannot decide which representation is better.','',
'## 6. Out-of-sample future minutes and performance','',
'Candidates are players in each club’s previous five observed matches with at least 180 historical minutes. Next-match minutes include zero for absence only when both teams have adequate recorded lineup coverage. This includes injuries, departures and rotation in the outcome; it excludes entirely unseen recruits. Performance is the league/defensive-goal-adjusted provider match rating conditional on at least 30 played minutes and a recorded rating. It is a selected outcome, not independent ground-truth talent.',
'', 'Controls include current and baseline club/opponent strength, home status, age and age squared, position, competition, prior-five-match minutes share and historical window minutes. Lower MSE/MAE is better. Intervals are paired player-cluster bootstraps.']
for endpoint in ('minutes','performance'):
 a=r[endpoint]
 lines+=['',f'### {endpoint.capitalize()}', '',f'Train **{a["train_n"]:,}**, validation **{a["validation_n"]:,}**, test **{a["test_n"]:,}**, **{a["test_players_or_weeks"]:,} test players**.','',
 '| Model | Test MSE | MAE | Δ MSE vs controls | 95% CI | Improvement vs controls |','|---|---:|---:|---:|---|---:|']
 base=a['models']['club_controls']['mse']
 for name,m in a['models'].items():
  lines.append(f'| {LABELS[name]} | {m["mse"]:.6f} | {m["mae"]:.6f} | {m["delta_vs_club_controls"]["mean"]:+.6f} | {ci(m["delta_vs_club_controls"])} | {(base-m["mse"])/base:.2%} |')
 lines+=['','**Stricter historical-club controls** add position-specific linear/quadratic window club strength, so the player rating must add information beyond its own club-level input.','',
 '| Model | Test MSE | Δ MSE vs stronger controls | 95% CI | Δ MSE vs scaled | 95% CI vs scaled |',
 '|---|---:|---:|---|---:|---|']
 for name,m in a['history_controlled']['models'].items():
  lines.append(f'| {LABELS[name]} | {m["mse"]:.6f} | {m["delta_vs_club_controls"]["mean"]:+.6f} | {ci(m["delta_vs_club_controls"])} | {m["delta_vs_scaled"]["mean"]:+.6f} | {ci(m["delta_vs_scaled"])} |')
 lines+=['','Position and transfer checks, using the first control set (held-out; exploratory):','',
 '| Group | n | Controls MSE | Scaled MSE | Fixed-club MSE | Residual MSE |',
 '|---|---:|---:|---:|---:|---:|']
 for group,g in a['subgroups'].items():
  lines.append(f'| {group} | {g["n"]:,} | '+' | '.join(f'{g["models"][name]["loss"]:.6f}' for name in ('club_controls','scaled','fixed_club','residual'))+' |')
lines+=['','The residual and scaled player regressions with position-specific quadratic historical-club controls span the same linear predictor space: the residual subtracts a function already in the controls. Tiny differences between them are regularization effects, not independent proof that residualization discovers new information. Fixed-club performance is also effectively tied with scaled performance: its MSE difference versus scaled is +0.000032 (95% CI −0.000066 to +0.000153).','',
'Transfer prediction subgroups include eligible observations among the first five new-club appearances; the first appearance itself is usually absent because the player was not previously observed at the new club. These subsets condition on playing and therefore omit new-club nonselections. They do not measure the ability to forecast an unseen signing’s playing time.','',
'The first-control-set transfer check is asymmetric: for 4,775 strong→weak observations, scaled minutes MSE falls from 1757.99 to 1595.42 (about 9.2%); for 3,435 weak→strong observations, it rises from 1455.14 to 1524.77 (about 4.8%). The fixed-club and residual versions do better for upward movers. This is an exploratory, selected subgroup result; test transfer-specific adaptation prospectively with zero-minute nonselections included before changing scaling.','',
'## 7–8. Incremental match value and alternatives','',
'An offline multinomial model predicts Home/Draw/Away from club Current/Baseline differences, average levels and competition. The added player feature is the difference between predicted-XI means. Each XI is one goalkeeper plus ten outfield players selected using only prior-five-match minutes; require eleven eligible players per team. No actual future lineup or retrospective injury list is used. This is an incremental information test against a club baseline, not a replacement or measured lift to the deployed match predictor.']
a=r['matches']
lines+=['',f'Train **{a["train_n"]:,}**, validation **{a["validation_n"]:,}**, test **{a["test_n"]:,} fixtures**, **{a["test_players_or_weeks"]} test weeks**.']
for title,g in [('Club controls',a),('Stricter historical-club controls',a['history_controlled'])]:
 lines+=['',f'### {title}','',
 '| Added feature | Log loss | Brier | ECE | Accuracy | Δ log loss vs controls | 95% CI |',
 '|---|---:|---:|---:|---:|---:|---|']
 for name,m in g['models'].items():
  lines.append(f'| {LABELS[name]} | {m["log_loss"]:.6f} | {m["brier"]:.6f} | {m["ece"]:.5f} | {m["accuracy"]:.2%} | {m["delta_vs_club_controls"]["mean"]:+.6f} | {ci(m["delta_vs_club_controls"])} |')
lines+=['','The stricter baseline adds the predicted XI’s historical window club-strength means and mean squares, as home-away differences and combined means. The scaled-rating improvement shrinks from 0.001746 to 0.001226 log loss but survives this check (95% improvement CI 0.000139–0.002377). Thus some benefit is duplicated club information, but not all of the measured gain disappears. The point estimate remains below the 0.002 practical threshold. Brier improves; binned ECE worsens from 0.00668 to 0.00785. Neither the neutral-club nor residual signal beats the scaled version on match proper scores. The scaled-versus-neutral loss advantage is only 0.000268, too small to settle broader rating-design decisions.','',
'| Test period | n | Controls loss | Scaled loss | Fixed-club loss | Residual loss |',
'|---|---:|---:|---:|---:|---:|']
for period,g in a['subgroups'].items():
 lines.append(f'| {period} | {g["n"]:,} | '+' | '.join(f'{g["models"][name]["loss"]:.6f}' for name in ('club_controls','scaled','fixed_club','residual'))+' |')
lines+=['','## Confidence and interpretation limits','',
'- 1,000 paired bootstrap draws; player clusters for player targets/transfers, UTC ISO-week clusters for matches. Pointwise 95% intervals, without multiple-testing adjustment. Shared-club dependence, longer temporal dependence, model-fitting uncertainty and revised historical data are not fully captured.',
'- Calibration is mean classwise ECE in 0.1-width bins; full counts, predicted probabilities and observed frequencies are in results.json. It is bin-sensitive and is not used to choose a coefficient alone. Brier uses the sum across three classes.',
'- The practical review criteria are 1% player-target MSE improvement or 0.002 match-log-loss improvement with corroborating Brier, uncertainty and temporal consistency. Smaller statistically detectable changes need not justify model complexity.',
'- Existing statistical weights and position adjustments were designed using historical results, including these years. Chronological inputs prevent direct lookahead but cannot undo model-development leakage. This is not a pristine untouched historical holdout.',
'- Historical-club controls were added after a diagnostic fit to probe confounding; they are a robustness check, not independent confirmation. No coefficient was optimized around an individual club.',
'- Provider ratings reflect team outcomes and match roles; neither those ratings nor minutes isolate intrinsic player ability. Transfers out of covered competitions and players not selected are incompletely observed.',
'- The actual website season/career rating has only two immutable captures, under different model versions. Its out-of-sample incremental value remains unresolved; do not substitute reconstructed rolling results for that claim.','',
'## Recommended next experiment','',
'Freeze the current production model. Prospectively capture, for every eligible squad member and each forecast time, the exact website season rating, rolling rating, raw score/percentile, window club strength, neutral-club value, residual, position, history minutes, team and model version. Use the same candidate set and predicted XI for all variants; retain nonselections and coverage exits rather than selecting only future appearances.',
'',
'Preregister a fixed evaluation window and a player/club-clustered power calculation. Compare (a) full club-history baseline, (b) baseline plus scaled player signal, (c) baseline plus neutral signal and (d) baseline plus residual. Test future minutes, adjusted performance and match proper scores, with separate verified-transfer and CB/FB cohorts. Keep normalization/residual fits frozen or update them on past data only, and explicitly test models against a later untouched period. Extend capture metadata to retain component values before drawing conclusions about weakening the website formula.',
'',
'**Review decision: retain production ratings. The evidence supports testing a separate context-neutral statistical component alongside the contextual rating; it does not justify automatically replacing the current rating or changing the defender/full-back club coefficient.**','',
'## Reproduction and artifacts','',
'- Protocol: `DESIGN.md`; read-only extraction: `extract.py`; replay/model fitting: `run.py`; numerical results and subgroup intervals: `results.json`.',
f'- Input SHA-256: `{r["input_sha256"]}`. Run source SHA-256: `{r["code_sha256"]}`. Production source and current-export fingerprints are recorded in results.json.',
'- Inputs remain in ignored `.cache/player_club_strength_inputs.json.gz`; the replay cache is also local and ignored. No credentials are included in tracked artifacts.',
'', '```bash',
'/tmp/thecornerfc-experiment-venv/bin/pip install -r experiments/player_club_strength/requirements.txt',
'# Optional fresh extraction; requires .env DATABASE_URL and uses enforced read-only mode:',
'/tmp/thecornerfc-experiment-venv/bin/python experiments/player_club_strength/extract.py',
'OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 /tmp/thecornerfc-experiment-venv/bin/python experiments/player_club_strength/run.py',
'/tmp/thecornerfc-experiment-venv/bin/python experiments/player_club_strength/write_report.py',
'/tmp/thecornerfc-experiment-venv/bin/python -m unittest discover -s tests -p "test_player_club_experiment.py"',
'```','']
(ROOT/'REPORT.md').write_text('\n'.join(lines))
