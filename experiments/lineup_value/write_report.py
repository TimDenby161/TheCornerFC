"""Render REPORT.md from results.json and weight_sensitivity.json. No computation beyond formatting."""
import json
from pathlib import Path
ROOT=Path(__file__).parent
r=json.loads((ROOT/'results.json').read_text());w=json.loads((ROOT/'weight_sensitivity.json').read_text())
T=r['test']['models'];V=r['validation']['models'];P=r['club_proxy_test']['models'];L=r['leagues']
GRID=['-0.005','0.0','0.0025','0.005','0.01','0.02']

def ci(c):return '—' if not c or c.get('ci95') is None else f'{c["ci95"][0]:+.5f} to {c["ci95"][1]:+.5f}'
def row(label,m,ref='none'):
    return f'| {label} | {m["log_loss"]:.5f} | {m["brier"]:.5f} | {m["classwise_ece"]:.5f} | {m["accuracy"]:.2%} | {m["goal_difference_mae"]:.4f} | {m["delta_log_loss_vs_"+ref]:+.5f} | {ci(m["log_loss_ci"])} |'
def seg(label,s):
    m=s['models']
    return (f'| {label} | {s["n"]:,} | {s["weeks"]} | {m["none"]["log_loss"]:.4f} | {m["predicted"]["delta_log_loss_vs_none"]:+.5f} | {ci(m["predicted"]["log_loss_ci"])} | '
            f'{m["actual"]["delta_log_loss_vs_predicted"]:+.5f} | {ci(m["actual"]["vs_predicted_ci"])} |')
def small(label,s):
    if not s.get('n'):return f'| {label} | 0 | — | — | — |'
    m=s['models'];return f'| {label} | {s["n"]} | {m["none"]["log_loss"]:.4f} | {m["predicted"]["log_loss"]:.4f} | {m["actual"]["log_loss"]:.4f} |'

gain=-T['predicted']['delta_log_loss_vs_none'];ceiling=-T['actual']['delta_log_loss_vs_predicted'];proxy=-P['predicted']['delta_log_loss_vs_club_proxy']
periods=r['periods'];pro=r['prospective'];mk=r['market_matched'];ov=r['prospective_overlap']
lines=['# Lineup value: what lineup information adds to match prediction','',
f'**Recommendation: keep the lineup system and all production formulas unchanged. Do not prioritise improving lineup prediction as a route to materially better match forecasts.**','',
f'On {r["test"]["n"]:,} held-out fixtures the current predicted-XI adjustment improves log loss by **{gain:.4f}** per fixture. About {1-proxy/gain:.0%} of that can be reproduced by a club-strength-only proxy with no lineup information, leaving about **{proxy:.4f}** attributable to lineups specifically. Knowing the actual starting XI would add only a further **{ceiling:.4f}**. The existing system therefore captures most of the value available from XI knowledge under this formula, and that value is small. Goalkeeper weight zero is supported. Prospective timing, availability and market evidence are too sparse to evaluate.','',
'## Answers','',
f'1. **How much value does the existing lineup system add?** {gain:.4f} log loss and {-T["predicted"]["delta_brier_vs_none"]:.4f} Brier per fixture versus no lineup adjustment (95% CI {ci(T["predicted"]["log_loss_ci"])}). It passes the 0.002 practical threshold only against a naive baseline. Against a club-strength-only proxy the lineup-specific gain is {proxy:.4f} ({ci(P["predicted"]["log_loss_ci"])}), below that threshold. Accuracy is unchanged ({T["none"]["accuracy"]:.2%} → {T["predicted"]["accuracy"]:.2%}).',
f'2. **How much more could perfect XI knowledge add?** {ceiling:.4f} log loss beyond the predicted XI ({ci(T["actual"]["vs_predicted_ci"])}): {periods["2024-25"]["models"]["actual"]["delta_log_loss_vs_predicted"]*-1:.4f} in 2024-25 and {periods["2025-onwards"]["models"]["actual"]["delta_log_loss_vs_predicted"]*-1:.4f} from 2025, whose interval crosses zero. Rescaling the outfield weights for the actual XI does not change this materially (see sensitivity).',
f'3. **Would better lineup prediction materially improve match prediction?** Unlikely. Even perfect prediction closes a gap of about {ceiling:.4f}, a quarter of the practical threshold, and a realistic improvement would capture only part of it. The gap is concentrated in close matches (predicted strength gap below {r["large_gap_threshold_goals"]:.3f} goals), where lineup errors matter relatively more. Timely lineup/availability inputs near kickoff may matter more than XI selection accuracy itself, but the prospective sample cannot test that yet.','',
'## Design and provenance','',
'- Frozen read-only extracts taken 2026-09-27 12:03 UTC (prediction/lineup snapshots) and 12:10 UTC (fixture history and odds). No API calls, database writes or production changes. Input SHA-256 fingerprints are in results.json.',
'- **Historical fixed-formula ablation** (the main evidence): every fixture from July 2023 in the covered player-data competitions with complete predicted and actual line ratings for both teams. The no-lineup baseline is the current `predict_match` rebuilt chronologically from club ranks and prior form, without injury or lineup inputs. The predicted and actual XI line ratings are then added with production weights (GK 0, DEF/MID/FWD 0.005 per rating point) on identical fixtures.',
'- Actual-XI ratings use each starter\'s rating **going into** the fixture, not their performance in it. It is an information counterfactual (who started, in which line), not a guaranteed upper bound for a fixed imperfect formula.',
f'- Validation: July 2023–June 2024 ({r["validation"]["n"]:,} fixtures). Test: July 2024 onward ({r["test"]["n"]:,} fixtures, {r["test"]["weeks"]} weeks). Exclusions from {r["historical_exclusions"]["considered"]:,} considered: {r["historical_exclusions"]["incomplete_predicted_or_rated_actual_XI"]:,} without eleven rated starters or a full predicted XI, {r["historical_exclusions"]["missing_line"]:,} with a missing line rating.',
'- Uncertainty: paired UTC ISO-week cluster bootstrap, 2,000 draws; pointwise, not multiplicity-adjusted. Brier is summed over three classes; ECE is mean classwise ten-bin calibration error (bin-sensitive, not a selection criterion alone).',
'- **Club-strength proxy (circularity control):** player ratings contain club strength, so part of any lineup gain may be club information the baseline under-uses. The proxy predicts each fixture\'s predicted-line margin from Current and Baseline rank differences only, fitted on validation without outcomes, and adds that instead of lineups.','',
'## Main held-out comparison (identical fixtures)','',
'| Model | Log loss | Brier | ECE | Accuracy | GD MAE | Δ log loss vs none | 95% CI |','|---|---:|---:|---:|---:|---:|---:|---|',
row('No lineup adjustment',T['none']),row('Club-strength proxy (no lineups)',T['club_proxy']),row('Current predicted XI',T['predicted']),row('Actual XI (retrospective)',T['actual']),'',
f'Validation shows the same ordering: none {V["none"]["log_loss"]:.5f}, proxy {V["club_proxy"]["log_loss"]:.5f}, predicted {V["predicted"]["log_loss"]:.5f}, actual {V["actual"]["log_loss"]:.5f}.','',
'| Comparison | Δ log loss | 95% CI | Δ Brier |','|---|---:|---|---:|',
f'| Predicted XI vs club proxy | {P["predicted"]["delta_log_loss_vs_club_proxy"]:+.5f} | {ci(P["predicted"]["log_loss_ci"])} | {P["predicted"]["delta_brier_vs_club_proxy"]:+.5f} |',
f'| Actual XI vs club proxy | {P["actual"]["delta_log_loss_vs_club_proxy"]:+.5f} | {ci(P["actual"]["log_loss_ci"])} | {P["actual"]["delta_brier_vs_club_proxy"]:+.5f} |',
f'| Actual XI vs predicted XI | {T["actual"]["delta_log_loss_vs_predicted"]:+.5f} | {ci(T["actual"]["vs_predicted_ci"])} | {T["actual"]["delta_brier_vs_none"]-T["predicted"]["delta_brier_vs_none"]:+.5f} |','',
f'Binned calibration error is mixed: on test ECE falls from {T["none"]["classwise_ece"]:.5f} to {T["predicted"]["classwise_ece"]:.5f}, but on validation it rises from {V["none"]["classwise_ece"]:.5f} to {V["predicted"]["classwise_ece"]:.5f}. ECE differences this small are within binning noise; log loss and Brier, which improve in both periods, are the primary evidence. Goal-difference MAE is essentially unchanged. Full calibration bins are in results.json.','',
'| Period | n | None | Predicted | Actual | Predicted vs none | Actual vs predicted |','|---|---:|---:|---:|---:|---:|---:|']
for k,s in periods.items():
    m=s['models'];lines.append(f'| {k} | {s["n"]:,} | {m["none"]["log_loss"]:.5f} | {m["predicted"]["log_loss"]:.5f} | {m["actual"]["log_loss"]:.5f} | {m["predicted"]["delta_log_loss_vs_none"]:+.5f} | {m["actual"]["delta_log_loss_vs_predicted"]:+.5f} |')
hs=r['historical_segments']
lines+=['','## Breakdowns (held-out, exploratory)','',
f'Large versus small predicted strength difference splits at the validation median absolute predicted-line margin, {r["large_gap_threshold_goals"]:.3f} goals.','',
'| Group | n | Weeks | None log loss | Predicted vs none | 95% CI | Actual vs predicted | 95% CI |','|---|---:|---:|---:|---:|---|---:|---|',
seg('Large predicted strength gap',hs['predicted_strength_gap:large']),seg('Small predicted strength gap',hs['predicted_strength_gap:small'])]
comps=sorted((k for k in hs if k.startswith('competition:')),key=lambda k:-hs[k]['n'])[:12]
lines+=[seg(f'{L.get(k.split(":")[1],k)} ({k.split(":")[1]})',hs[k]) for k in comps]
lines+=['','Most of the predicted-XI gain comes from fixtures where the predicted lines differ a lot; that is where the adjustment moves probabilities. The remaining value of perfect XI knowledge is larger in close fixtures. Per-competition intervals are wide and mostly cross zero; competition-specific weights are not supported. All competitions are in results.json.','',
'## Outfield weight sensitivity (post-result robustness check)','',
'Multiplier on production DEF/MID/FWD weights (1.0 = production, 0 = no lineup), GK weight zero. Chosen on validation log loss.','',
'| Multiplier | Predicted: validation | Predicted: test | Actual: validation | Actual: test |','|---:|---:|---:|---:|---:|']
pv,av=w['variants']['pred'],w['variants']['actual']
for k in map(str,w['multipliers']):
    lines.append(f'| {float(k):g} | {pv["validation_log_loss"][k]:.5f} | {pv["test_log_loss"][k]:.5f} | {av["validation_log_loss"][k]:.5f} | {av["test_log_loss"][k]:.5f} |')
best=min(av['test_log_loss'],key=av['test_log_loss'].get)
lines+=['',f'Validation selects the production scale (1.0) for both predicted and actual XI. The best test multiplier for the actual XI ({float(best):g}) beats production scaling by only {av["test_log_loss"]["1.0"]-av["test_log_loss"][best]:.5f}. The small perfect-XI gap is not caused by a mis-scaled weight.','',
'## Goalkeeper contribution','',
'The goalkeeper weight was selected on validation log loss from the grid below, with outfield weights fixed at production values. Negative weights are diagnostics, not football recommendations.','',
'| GK weight | Predicted: validation | Predicted: test Δ vs GK 0 | 95% CI | Actual: validation | Actual: test Δ vs GK 0 | 95% CI |','|---:|---:|---:|---|---:|---:|---|']
G=r['gk_test_comparisons']
for g in GRID:
    a=G['predicted']['models'][f'predicted_gk_{g}'];b=G['actual']['models'][f'actual_gk_{g}']
    lines.append(f'| {float(g):g} | {V[f"predicted_gk_{g}"]["log_loss"]:.5f} | {a["delta_log_loss_vs_predicted"]:+.5f} | {ci(a["log_loss_ci"])} | {V[f"actual_gk_{g}"]["log_loss"]:.5f} | {b["delta_log_loss_vs_actual"]:+.5f} | {ci(b["log_loss_ci"])} |')
lines+=['',f'Validation selects GK weight **{r["validation_selected_gk"]["predicted"]:g}** for the predicted XI and **{r["validation_selected_gk"]["actual"]:g}** for the actual XI. Small positive weights (0.0025–0.005) are statistically indistinguishable from zero on test. Weights of 0.01 and above are clearly worse. This supports the current zero weight *for this goalkeeper rating*; it does not show goalkeepers are unimportant. A keeper rating built from shot-stopping evidence might behave differently and would be a separate experiment.','',
'## Prospective captures: timing, XI accuracy, availability and market','',
f'Lineup-timing, predicted-player overlap and availability reports only exist in immutable prospective captures, which began on 2026-09-26. Only **{pro["n"]} finished fixtures** (one week) have a reproducible prospective prediction, a frozen predicted XI and an aligned official XI. A further {r["prospective_exclusions"].get("no_complete_line_adjustment",0)} captured fixtures had no complete line adjustment. Mean correctly predicted starters: {ov["mean_correct_of_22"]:.1f} of 22. **This sample cannot support any conclusion**; the rows below are shown only to document what the pipeline produces.','',
'| Group | n | None | Predicted | Actual |','|---|---:|---:|---:|---:|',small('All prospective',pro)]
ps=r['prospective_segments']
for k in sorted(k for k in ps if not k.startswith('competition')):lines.append(small(k.replace('_',' '),ps[k]))
for h in ('6','24','48'):
    lines.append(small(f'Captured ≥{h}h before kickoff',r['horizon_cutoffs_hours'][h]['paired_XI']))
lines+=['',f'**Model versus market:** {mk["n"]} fixtures have a complete same-bookmaker H/D/A price captured and inserted before the prediction cutoff. '+
(f'Market log loss {mk["models"]["market"]["log_loss"]:.4f} versus model {mk["models"]["predicted"]["log_loss"]:.4f} (predicted XI) and {mk["models"]["none"]["log_loss"]:.4f} (no lineup). ' if mk.get('n') else '')+
'No historical timestamped odds exist before 2026-09-26, so no historical model-versus-market comparison is possible and nothing should be inferred from this sample.','',
'## Limitations','',
'- The historical baseline is a chronological rebuild of the current formula without injury inputs. Historical predicted XIs mostly lack injury exclusions, so the production system (which uses live availability) may perform somewhat differently from this reconstruction.',
'- Historical player ratings are rebuilt with current code and full-history percentile references. Player windows are pre-match, but reference scaling and model development used these years. This is not a pristine prospective test.',
'- The actual XI reveals roles and line assignment, not only identities. It is not a strict upper bound for a better formula that could use lineups differently (for example interactions or per-line weights); only the scale of the existing linear adjustment was tested.',
'- Competition and strength-gap groups are exploratory and overlapping; intervals are pointwise without multiplicity adjustment. The club proxy and weight sensitivity were added as robustness checks.',
'- Covered competitions are those with player data (the player-club frozen fixture set), not every competition the site predicts.','',
'## Recommended next experiment','',
'Let prospective captures accumulate for a pre-registered period (sized by a week-clustered power calculation; likely several months) and repeat the paired comparison on production snapshots only. Test: (a) value by capture time before kickoff, especially predictions refreshed after official lineups; (b) availability-report presence and injury uncertainty; (c) model versus the timestamped market on identical fixtures. Separately, if goalkeeper impact is of interest, test a keeper-specific rating rather than re-weighting the current one. Do not spend effort on lineup-selection accuracy until (a) shows timing matters.','',
'## Reproduction','',
'```bash',
'# Optional fresh read-only extraction (needs .env DATABASE_URL; enforced read-only transaction):',
'python3 experiments/lineup_value/extract.py && python3 experiments/lineup_value/extract_history.py',
'# Requires the frozen player-club input cache; no database access:',
'OPENBLAS_NUM_THREADS=1 /opt/anaconda3/bin/python experiments/lineup_value/run.py',
'/opt/anaconda3/bin/python experiments/lineup_value/weight_sensitivity.py',
'python3 experiments/lineup_value/write_report.py',
'/opt/anaconda3/bin/python -m unittest discover -s tests -p "test_lineup_value_experiment.py"',
'```','',
'No production formulas, constants, ratings or database rows were changed.']
(ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n')
print('REPORT.md written')
