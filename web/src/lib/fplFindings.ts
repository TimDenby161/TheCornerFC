// The FPL page's findings: how the fantasy expected-points model did on matches it had never seen
// (the "fpl" document, from experiments/fantasy_v1). No FPL data is in it: points are rebuilt from
// match stats with FPL's scoring rules. Everything is turned into the words and figures the page
// shows, here, so the page only lays them out.
import { FPL_POS } from './fantasy.ts';
import { pctText as pct } from './stats.ts';

type Err = { n: number; mae: number; rmse: number; spearman: number };
type Diff = { diff: number; lo: number; hi: number };
type Seg = Record<string, { model: Err; recent5: Err; ppg: Err }>;
type Calib = { bins: [number, number, number][] };
type Top = Record<string, { hit_rate: number; mean_points: number }>;
export type FplFindings = {
	overall: Record<string, Err>;
	criteria: ({ key: string; pass: boolean } & Record<string, unknown>)[];
	top_n: Record<string, Top>;
	test: { rows: number };
	round_wins: { model_lower_mae: number; rounds: number };
	segments: { position: Seg; round_bucket: Seg; ability_band: Seg; regular: Seg };
	minutes: { mae: number; rmse: number; recent5_mae: number; recent5_rmse: number };
	availability_minutes_mae: number;
	start_calibration: Calib; clean_sheet_calibration: Calib; validation_clean_sheet_ece: number;
	saves: { validation_terciles: { mean_pred: number; mean_actual: number }[]; posthoc_gk_bias: number };
	prospective: { state: string; first_capture?: string; finished_fixtures?: number; finished_rounds?: number; target_rounds: number };
};

const NAMES: Record<string, string> = {
	model: 'Our model', recent5: 'Last-5 average', ppg: 'Points per game',
	flat_team_goals: 'Our model, no match model', v1_1: 'v1.1 (next version)'
};
const n2 = (x: number | null | undefined) => (x == null ? '–' : x.toFixed(2));
const n3 = (x: number | null | undefined) => (x == null ? '–' : x.toFixed(3));
const ci = (d: Diff) => `${d.diff > 0 ? '+' : '−'}${Math.abs(d.diff).toFixed(3)} (95% range ${d.lo.toFixed(3)} to ${d.hi.toFixed(3)})`;
const pctSigned = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(x).toFixed(Math.abs(x) < 10 ? 1 : 0)}%`;

function segRows(seg: Seg, order: string[], name = (g: string) => g) {
	return order.filter((g) => seg[g]).map((g) => {
		const x = seg[g];
		return {
			name: name(g), rows: x.model.n.toLocaleString('en-GB'), cls: x.model.mae < x.recent5.mae ? 'gap-ok' : 'gap-off',
			model: n3(x.model.mae), recent: n3(x.recent5.mae), ppg: n3(x.ppg.mae), rank: n2(x.model.spearman), recentRank: n2(x.recent5.spearman)
		};
	});
}
const calibRows = (c: Calib) => c.bins.map(([count, p, rate]) => {
	const gap = Math.abs(rate - p);
	return { said: pct(p, 0), count: count.toLocaleString('en-GB'), hit: pct(rate, 0), cls: gap <= 0.03 ? 'gap-ok' : gap > 0.06 ? 'gap-off' : '', bar: Math.round(rate * 60) };
});

export function findingsView(f: FplFindings) {
	const o = f.overall;
	const passed = f.criteria.filter((c) => c.pass).length;
	const by = Object.fromEntries(f.criteria.map((c) => [c.key, c])) as Record<string, unknown>;
	const b = by.bias as { pass: boolean; overall_bias_pct: number; position_bias_pct: Record<string, number> };
	const cal = by.calibration as { pass: boolean; start_ece: number; team_cs_ece: number };
	const bench = by.benchmarks as { pass: boolean; mae_vs_recent: Diff };
	const mm = by.match_model as { pass: boolean; mae_vs_flat: Diff };
	const mi = f.minutes, reg = f.segments.regular.regular, pr = f.prospective;
	const rounds = pr.finished_rounds || 0;
	return {
		ok: passed === f.criteria.length,
		verdict: `${passed === f.criteria.length ? 'Validated' : 'Promising, not yet validated'} · ${passed} of ${f.criteria.length} checks pass`,
		testRows: f.test.rows.toLocaleString('en-GB'),
		cards: [
			['Average error', `${n2(o.model.mae)} pts`, `Last-5 average: ${n2(o.recent5.mae)} · points per game: ${n2(o.ppg.mae)}`],
			['Rounds won', `${f.round_wins.model_lower_mae} / ${f.round_wins.rounds}`, 'Rounds where it beat the last-5 average'],
			['Top-10 picks that hit', pct(f.top_n.model.top10.hit_rate, 0), `Last-5 average: ${pct(f.top_n.recent5.top10.hit_rate, 0)}. Hits = reached that round's actual top 10`],
			['Regular starters', `${n2(reg.model.mae)} pts`, `Error for players starting 3+ of the last 5. Last-5 average: ${n2(reg.recent5.mae)}`]
		],
		// [passed, the claim, the evidence]
		checks: [
			[bench.pass, 'Beats the simple guesses.', `Lower average error than both the last-5 average and points per game, and the gap is clear of noise: ${ci(bench.mae_vs_recent)} points per player vs last-5 average.`],
			[b.pass, 'Predicts the right amount of points.', `Overall ${pctSigned(b.overall_bias_pct)} (limit ±5%), but goalkeepers ${pctSigned(b.position_bias_pct.G)} (limit ±10%): save points were left out after failing their own check (see below).`],
			[cal.pass, 'Its probabilities are honest.', `Start chances off by ${pct(cal.start_ece)} on average, clean-sheet chances by ${pct(cal.team_cs_ece)} (limit 3%).`],
			[mm.pass, 'The match model earns its place.', `Using our match predictions instead of league-average goals lowers the error by ${Math.abs(mm.mae_vs_flat.diff).toFixed(3)}.`]
		] as [boolean, string, string][],
		bench: ['model', 'recent5', 'ppg', 'flat_team_goals', 'v1_1'].filter((k) => o[k] && f.top_n[k]).map((k) => ({
			name: NAMES[k] + (k === 'v1_1' ? ' *' : ''), hl: k === 'model', mae: n3(o[k].mae), rmse: n3(o[k].rmse), rank: n2(o[k].spearman),
			hit: pct(f.top_n[k].top10.hit_rate, 0), pts: n2(f.top_n[k].top10.mean_points)
		})),
		byPosition: segRows(f.segments.position, ['G', 'D', 'M', 'F'], (g) => FPL_POS[g]),
		posTop: ['G', 'D', 'M', 'F'].map((p) => {
			const top = p === 'G' || p === 'F' ? 5 : 10;
			return { name: `${FPL_POS[p]} top ${top}`, hits: ['model', 'recent5', 'ppg', 'flat_team_goals'].map((k) => pct(f.top_n[k][`${p}_top${top}`].hit_rate, 0)) };
		}),
		minutes: [
			['Average error (mins)', mi.mae.toFixed(1), mi.recent5_mae.toFixed(1), mi.mae < mi.recent5_mae, mi.recent5_mae < mi.mae],
			['RMSE (mins)', mi.rmse.toFixed(1), mi.recent5_rmse.toFixed(1), mi.rmse < mi.recent5_rmse, mi.recent5_rmse < mi.rmse]
		] as [string, string, string, boolean, boolean][],
		minutesWithNews: f.availability_minutes_mae.toFixed(1),
		startCalib: calibRows(f.start_calibration), csCalib: calibRows(f.clean_sheet_calibration),
		csValidation: pct(f.validation_clean_sheet_ece),
		saves: {
			pred: f.saves.validation_terciles[2].mean_pred.toFixed(2), actual: f.saves.validation_terciles[2].mean_actual.toFixed(2),
			without: pctSigned(b.position_bias_pct.G), withThem: pctSigned(f.saves.posthoc_gk_bias)
		},
		byRound: segRows(f.segments.round_bucket, ['1-5', '6-19', '20-38']),
		byRank: segRows(f.segments.ability_band, ['80+', '70-80', '60-70']),
		live: {
			rounds, target: pr.target_rounds, share: Math.round(Math.min(100, (100 * rounds) / pr.target_rounds)),
			state: pr.state, since: pr.first_capture ?? null, fixtures: pr.finished_fixtures ?? 0
		}
	};
}
export type FindingsView = ReturnType<typeof findingsView>;
