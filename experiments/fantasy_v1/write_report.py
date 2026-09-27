"""REPORT.md from results.json. Numbers only come from results.json."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
R = json.loads((ROOT / 'results.json').read_text())
T = R['test']
NAMES = {'model': 'Fantasy v1', 'recent5': 'Recent average (last 5)', 'ppg': 'Points per game',
         'flat_team_goals': 'Ablation: flat team goals', 'availability_variant': 'Variant: + injury lists (timing unverified)',
         'v1_1': 'v1.1: + injury lists + saves (chosen after test)'}
POS = {'G': 'GK', 'D': 'DEF', 'M': 'MID', 'F': 'FWD'}


def f(x, n=3):
    return '–' if x is None or x != x else f'{x:.{n}f}'


def ci(v, n=3):
    return f"{v['diff']:+.{n}f} ({v['lo']:+.{n}f} to {v['hi']:+.{n}f})"


def yes(b):
    return 'PASS' if b else 'FAIL'


def metric_table(block, keys):
    out = ['| Predictor | MAE | RMSE | Pearson | Spearman | Mean pred | Mean actual |', '|---|---:|---:|---:|---:|---:|---:|']
    for k in keys:
        m = block[k]
        out.append(f"| {NAMES[k]} | {f(m['mae'])} | {f(m['rmse'])} | {f(m['pearson'])} | {f(m['spearman'])} | {f(m['mean_pred'])} | {f(m['mean_actual'])} |")
    return out


def segment_table(seg, order=None, label=lambda g: g):
    s = T['segments'][seg]
    out = ['| Segment | Rows | v1 MAE | Recent MAE | PPG MAE | v1 RMSE | Recent RMSE | v1 Spearman | Recent Spearman | v1 bias vs total |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for g in order or s:
        if g not in s:
            continue
        m, r, p = s[g]['model'], s[g]['recent5'], s[g]['ppg']
        out.append(f"| {label(g)} | {m['n']:,} | {f(m['mae'])} | {f(r['mae'])} | {f(p['mae'])} | {f(m['rmse'])} | {f(r['rmse'])} | "
                   f"{f(m['spearman'])} | {f(r['spearman'])} | {f(m['bias_pct'], 1)}% |")
    return out


def calib_table(c):
    out = ['| Bin | n | Mean predicted | Observed |', '|---|---:|---:|---:|']
    out += [f"| {b['bin']} | {b['n']:,} | {f(b['mean_p'])} | {f(b['rate'])} |" for b in c['bins']]
    return out


def main():
    s, o, vs, vr = R['success'], T['overall'], T['vs'], T['vs_regulars']
    reg = T['segments']['regular']
    tc, vc = R['test_team_checks'], R['validation_team_checks']
    mins, top = T['minutes'], T['top_n']
    ph = R['posthoc_with_saves']
    audit = R['prospective_audit']
    passed = sum(bool(s[k]) for k in s if k[0].isdigit() and not k.endswith('detail'))
    L = [
        '# Fantasy v1: validation of a simple FPL expected-points model', '',
        f"**Verdict: not yet validated. {passed} of 4 preregistered criteria pass.** The model clearly beats points-per-game and "
        f"recent-average benchmarks (MAE {f(o['model']['mae'])} vs {f(o['recent5']['mae'])} and {f(o['ppg']['mae'])}; lower in "
        f"{T['round_wins']['recent5']['model_lower_mae']} of {T['round_wins']['recent5']['rounds']} test rounds), is well calibrated on starts and "
        f"clean sheets, and the match model adds measurable value. It fails the bias criterion because goalkeepers are "
        f"under-predicted by {f(-s['2_detail']['position_bias_pct']['G'], 0)}%: the save component was dropped by the preregistered "
        f"validation rule. That is a narrow, diagnosable failure, not a reason to scrap the approach. It is still a reason not to build fantasy UI on v1 as it stands.", '',
        '**Three limits frame every number below:**',
        '1. **No official FPL data exists in the database** (every FPL table is empty; capture is off pending the licensing decision). '
        'Official FPL expected points and price **could not be benchmarked**, and the target is *reconstructed* FPL points from '
        'API-Football stat lines, without bonus, own goals, penalty misses or defensive contributions.',
        f"2. **Team goal expectations in the test are reconstructions**, by the current match model, which was tuned on 2023/24. Prospective match "
        f"snapshots start {audit['first_prospective_match_snapshot'][:10]}, after the last finished fixture ({audit['last_finished_kickoff'][:10]}), so "
        f"**{audit['finished_with_prospective_match_input']} test fixtures had a genuinely pre-kickoff input**.",
        '3. Positions are API-Football G/D/M/F, not FPL\'s. Gameweeks are API-Football rounds, so there are no FPL doubles or blanks.', '',
        '## Preregistered criteria (DESIGN.md)', '',
        '| # | Criterion | Result | Detail |', '|---|---|---|---|',
        f"| 1 | Beat PPG and recent average on MAE and RMSE, 95% CI excluding 0 | {yes(s['1_beats_ppg_and_recent_on_mae_and_rmse'])} | "
        f"MAE vs recent {ci(vs['recent5']['mae'])}; MSE vs recent {ci(vs['recent5']['mse'])} |",
        f"| 2 | Bias ≤ ±5% overall, ≤ ±10% per position (v1-scope target) | {yes(s['2_bias_within_limits'])} | overall {f(s['2_detail']['overall_bias_pct'], 1)}%; "
        + ', '.join(f"{POS[p]} {f(v, 1)}%" for p, v in s['2_detail']['position_bias_pct'].items()) + ' |',
        f"| 3 | Start ECE ≤ 0.03 and team clean-sheet ECE ≤ 0.03 | {yes(s['3_calibration'])} | start {f(s['3_detail']['start_ece'], 4)}; clean sheet {f(s['3_detail']['team_cs_ece'], 4)} |",
        f"| 4 | Beat the flat-team-goals ablation on MAE | {yes(s['4_beats_flat_team_goals'])} | {ci(vs['flat_team_goals']['mae'], 4)} |", '',
        f"Criterion 2 fails on goalkeepers alone. Saves were dropped because on validation (2023/24) the busiest tercile's saves were under-predicted "
        f"({f(vc['saves_terciles'][2]['mean_pred'], 2)} vs {f(vc['saves_terciles'][2]['mean_actual'], 2)}, beyond the ±10% rule). That season scored "
        f"{f(vc['team_goals']['mean_goals'], 2)} goals per team-match against a predicted {f(vc['team_goals']['mean_lambda'], 2)}. "
        f"*Post hoc and not preregistered:* with saves included on test, goalkeeper bias would be {f(ph['position_v1_bias_pct']['G'], 1)}% and every position within ±10%, "
        f"at a small cost in overall MAE ({f(ph['overall']['mae'])} vs {f(o['model']['mae'])}). That is evidence for putting saves back in v1.1, confirmed on fresh prospective gameweeks, not a retroactive pass.", '',
        '## Test results (2024/25 to 2026/27 so far)', '',
        f"{R['rows']['test']:,} player-fixtures ({R['rows']['train']:,} train, {R['rows']['validation']:,} validation). The target is reconstructed total points. "
        f"Players outside the universe (mostly debut appearances for a club) scored {f(R['coverage']['outside_share'] * 100, 1)}% of test points and are not scored here.", '',
        *metric_table(o, ['model', 'recent5', 'ppg', 'flat_team_goals', 'availability_variant', 'v1_1']), '',
        'Paired differences (v1 minus benchmark; negative favours v1). Cluster bootstrap over (season, round), 2,000 draws:', '',
        '| Versus | ΔMAE, all rows | ΔMSE, all rows | ΔMAE, regulars | ΔMSE, regulars |', '|---|---|---|---|---|',
        *[f"| {NAMES[k]} | {ci(vs[k]['mae'])} | {ci(vs[k]['mse'])} | {ci(vr[k]['mae'])} | {ci(vr[k]['mse'])} |" for k in vs], '',
        f"Most rows are fringe players who score about 0 whatever anyone predicts, so correlation and all-row MAE flatter every predictor. "
        f"The **regulars** subset (started ≥ 3 of the team's last 5, defined before kickoff; {reg['regular']['model']['n']:,} rows) is the relevant one for picking. "
        f"There, v1's MAE is {f(reg['regular']['model']['mae'])} vs {f(reg['regular']['recent5']['mae'])} for recent average, and Spearman is "
        f"{f(reg['regular']['model']['spearman'])} vs {f(reg['regular']['recent5']['spearman'])}. "
        f"A rank correlation of {f(reg['regular']['model']['spearman'], 2)} among regulars is modest: single-gameweek points are mostly noise.", '',
        '### Top-N hit rates (per round, across all players)', '',
        'Hit = a predicted top-N player whose actual points reach that round\'s actual N-th best. Also shown: mean actual points of the predicted top N.', '',
        '| Predictor | Top 10 | Top 25 | Top 50 | GK top 5 | DEF top 10 | MID top 10 | FWD top 5 | Top-10 mean pts |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
        *[f"| {NAMES[k]} | " + ' | '.join(f"{top[k][x]['hit_rate'] * 100:.1f}%" for x in ('top10', 'top25', 'top50', 'G_top5', 'D_top10', 'M_top10', 'F_top5'))
          + f" | {f(top[k]['top10']['mean_points'], 2)} |" for k in ('model', 'recent5', 'ppg', 'flat_team_goals', 'availability_variant', 'v1_1')], '',
        'The match model matters more for ranking than for MAE. Without it (flat team goals), the defender and goalkeeper hit rates fall most, as expected, since clean sheets depend on the opponent.', '',
        '### Expected minutes', '',
        f"| | v1 | Recent 5-match average minutes |", '|---|---:|---:|',
        f"| MAE (minutes) | {f(mins['mae'], 1)} | {f(mins['recent5_mae'], 1)} |",
        f"| RMSE (minutes) | {f(mins['rmse'], 1)} | {f(mins['recent5_rmse'], 1)} |",
        f"| Mean vs actual {f(mins['mean_actual'], 1)} | {f(mins['mean_pred'], 1)} | {f(mins['recent5_mean'], 1)} |",
        f"| Availability variant MAE | {f(T['availability_variant_detail']['minutes_mae'], 1)} | |", '',
        f"**v1's minutes MAE is slightly worse than the naive 5-match average** ({f(mins['mae'], 1)} vs {f(mins['recent5_mae'], 1)}), though its RMSE is better. Minutes are close to "
        "0-or-90, and MAE rewards committing to one end: a regular who averaged 90 is predicted 90 by the naive rule, while v1's calibrated expectation is around 76. "
        "Expected points need the expectation, so v1 keeps it, but the minutes component is not better than naive on the preregistered minutes metric. "
        "By position: " + '; '.join(f"{POS[p]} {f(v['mae'], 1)} vs {f(v['recent5_mae'], 1)}" for p, v in mins['by_position'].items()) + '.', '',
        f"The injury-list variant cuts minutes MAE to {f(T['availability_variant_detail']['minutes_mae'], 1)} and points MAE by {f(vs['availability_variant']['mae']['diff'])}. "
        "The injury table has no capture times (every row was rewritten 2026-09-23), so historical lists may contain post-kickoff knowledge. "
        "Treat that gain as an upper bound until prospective availability (FPL status flags or timed injury captures) confirms it.", '',
        f"**Start calibration**: ECE {f(T['start_calibration']['ece'], 4)}, Brier {f(T['start_calibration']['brier'], 4)}; mean {f(T['start_calibration']['mean_p'])} vs {f(T['start_calibration']['rate'])} observed. "
        f"P(play) ECE {f(T['play_calibration']['ece'], 4)}, P(60+) ECE {f(T['p60_calibration']['ece'], 4)}.", '',
        *calib_table(T['start_calibration']), '',
        '### Clean sheets', '',
        f"Team level, e^(−λ against) from the match model: test ECE {f(tc['team_clean_sheet']['ece'], 4)}, mean {f(tc['team_clean_sheet']['mean_p'])} vs {f(tc['team_clean_sheet']['rate'])} observed "
        f"({tc['team_clean_sheet']['n']:,} team-matches). On validation the ECE was {f(vc['team_clean_sheet']['ece'], 4)}, above the 0.03 bar, with clean sheets over-predicted in that high-scoring season. "
        f"So clean-sheet calibration inherits the match model's season-level goal errors. On test the model predicted {f(tc['team_goals']['mean_lambda'], 2)} goals per team-match against {f(tc['team_goals']['mean_goals'], 2)} actual. "
        f"Player level (GK/DEF, needs 60+): ECE {f(T['player_cs_calibration']['ece'], 4)}.", '',
        *calib_table(tc['team_clean_sheet']), '',
        '### Components (test means per player-fixture)', '',
        '| Component | Predicted | Actual |', '|---|---:|---:|',
        *[f"| {k} | {f(v['mean_pred'], 4)} | {f(v['mean_actual'], 4)} |" for k, v in T['components'].items()], '',
        'Goals and assists by position (allocation uses attacking evidence and role, not overall rank):', '',
        '| Position | xG pred | Goals | Pearson | xA pred | Assists | Pearson |', '|---|---:|---:|---:|---:|---:|---:|',
        *[f"| {POS[p]} | {f(T['components']['exp_goals']['by_position'][p]['mean_pred'], 4)} | {f(T['components']['exp_goals']['by_position'][p]['mean_actual'], 4)} | "
          f"{f(T['components']['exp_goals']['by_position'][p]['pearson'])} | {f(T['components']['exp_assists']['by_position'][p]['mean_pred'], 4)} | "
          f"{f(T['components']['exp_assists']['by_position'][p]['mean_actual'], 4)} | {f(T['components']['exp_assists']['by_position'][p]['pearson'])} |" for p in POS], '',
        '## Segments (exploratory)', '',
        '"Bias vs total" compares with the full reconstructable total, which includes cards that v1 does not model. So a few percent of over-prediction is expected.', '',
        '### By position', '', *segment_table('position', ['G', 'D', 'M', 'F'], POS.get), '',
        '### By ability band (stand-in for price, which is not captured)', '',
        'Latest player rank before the fixture. **This is not FPL price.** The price-tier question stays open until prices are captured.', '',
        *segment_table('ability_band', ['80+', '70-80', '60-70', '<60', 'unrated']), '',
        '### By regular status', '', *segment_table('regular', ['regular', 'other']), '',
        '### By season', '', *segment_table('season'), '',
        '### By gameweek', '', *segment_table('round_bucket', ['1-5', '6-19', '20-38'], lambda g: f'Rounds {g}'), '',
        '<details><summary>Every round number (pooled over test seasons)</summary>', '',
        *segment_table('gameweek', sorted(T['segments']['gameweek'], key=int), lambda g: f'GW {g}'), '', '</details>', '',
        '## Selection and parameters', '',
        f"On validation, decay was chosen on minutes MAE ({', '.join(f'{k}: {f(v, 2)}' for k, v in R['selection']['decay'].items())}), which gave **{R['chosen']['decay']}**. "
        f"K was chosen on points MAE ({', '.join(f'{k}: {f(v, 4)}' for k, v in R['selection']['K'].items())}), which gave **{R['chosen']['K']}** pseudo-minutes. "
        "The differences are tiny, so neither choice matters much. The parameters were refitted on train + validation, then frozen for test; the full set is in results.json.", '',
        '## What this means for building on it', '',
        '- **Do not build major fantasy UI on v1 yet.** It beats the simple benchmarks convincingly, but it has not been compared with the benchmark that matters (official FPL xP), '
        'nor with price, and its test inputs are reconstructions. None of that can change until the FPL licensing decision is made: FPL IDs are also needed '
        'to write `fantasy_prediction_snapshots` (the table keys predictions by FPL player id).',
        '- **v1.1, small and justified by this run:** restore goalkeeper saves; capture availability prospectively; score it on prospective gameweeks against official xP once licensed.',
        '- Consider judging expected minutes by RMSE or a proper score (calibration and Brier are good), since MAE penalises a calibrated expectation of bimodal minutes.', '',
        '## v1.1 and prospective validation', '',
        f"v1.1 = v1 + goalkeeper saves + injury-list availability. On this test it scores MAE {f(o['v1_1']['mae'])}, with goalkeeper bias vs total "
        f"{f(T['segments']['position']['G']['v1_1']['bias_pct'], 1)}%. But it was **chosen after seeing these test results**, so those numbers are not evidence for it. "
        "Its parameters are frozen in `thecornerfc/fantasy_params.json`. `thecornerfc/fantasy_snapshots.py` now stores every component for every upcoming "
        "Premier League player before kickoff, with the timed availability and the benchmark values, in `fantasy_fixture_snapshots`. "
        "It is judged only on those prospective snapshots, under protocol P8 (`experiments/prospective/PROTOCOLS.md`): 10 rounds, then unblinded once.", '',
        '## Provenance', '',
        f"- Frozen read-only extract at {R['extracted_at'][:16]} UTC, input SHA-256 `{R['input_sha256'][:16]}…`; code `{R['code_sha256'][:16]}…`; model `{R['model_sha256'][:16]}…`.",
        f"- FPL tables at extraction: {', '.join(f'{k} {v}' for k, v in R['fpl_audit'].items())}.",
        f"- Every test component is stored as immutable content-hashed records ({R['snapshot_archive']['records']} rounds) in the local archive `{R['snapshot_archive']['path']}` "
        f"(SHA-256 `{R['snapshot_archive']['sha256'][:16]}…`), model version `{R['model_version_id'][:20]}…` (ModelType.FANTASY identity; not registered in the database). "
        'Nothing was written to the database.',
        '- Reproduce: `python3 experiments/fantasy_v1/extract.py` (needs psycopg), then `python3.13 experiments/fantasy_v1/run.py` and `write_report.py` (need numpy and scipy).', '']
    (ROOT / 'REPORT.md').write_text('\n'.join(L))


if __name__ == '__main__':
    main()
