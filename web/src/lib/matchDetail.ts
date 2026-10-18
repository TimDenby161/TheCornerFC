// A match's model detail: everything here sets out what the prediction's own explanation holds
// (predictions.explain(), stored with the match); none of it is worked out again.
import { signedGoals, shownProbs } from './matchday.ts';
import type { Match } from './matches.ts';
import { FINISHED } from './matches.ts';

export type Why = {
	fallback?: boolean[]; current: [number | null, number | null]; baseline: [number | null, number | null]; match: [number | null, number | null];
	margin: Record<string, number>; exp_diff: number; league_goals: number; tendencies?: number | null;
	missing: [number | null, number | null]; lines?: (number | null)[][] | null; neutral?: boolean;
	captured_at: string; source: string; injuries_at?: string | null; odds_at?: string | null; model?: string | null;
	// a national match: each side's predicted XI, [player, name, role]
	xi?: Record<string, [number, string, string][]>;
	steps?: Steps;
};
// The arithmetic from the inputs to the chances, with the weights the model used
// (site_matches.worked_steps): home first in every pair
export type Steps = {
	now_share: number | null;
	record: [number | null, number | null, number][]; league: [number, number];
	shrunk: [number, number, number, number]; plain: [number, number]; open_total: number | null; base: [number, number];
	scale: number; xg: [number, number]; poisson: [number, number, number]; boost: number;
	chances: [number, number, number]; likely: string;
	weights: { now: [number, number]; shrink: number; open: number; draw: [number, number]; absence: number; line: number };
};
// a row's value: words, or a moment (shown in the visitor's own time)
export type DetailRow = { label: string; value: string | { when: string }; tip?: string; teams?: boolean };
export type DetailSection = { title: string; unit?: string; rows: DetailRow[]; note?: string };

const MARGIN_LABELS: Record<string, [string, string]> = {
	strength: ['Strength gap', 'Home minus away match strength (the blend of Current and Baseline Strength), 100 points = 1 goal'],
	home_advantage: ['Home advantage', 'The same for every club: 0.3 goals'],
	europe_home: ['European tie', 'Extra home margin in UEFA club competitions'],
	home_edges: ["Clubs' home/away record", "The home side's own home edge plus the away side's own away weakness, from past results"],
	absences: ['Known absences', 'Players listed injured, suspended or doubtful, weighted by their recent minutes'],
	lineups: ['Predicted line-ups', 'Predicted XI ratings by line (defence, midfield, attack)']
};
// National team matches: the national ranking's own strengths and home advantage
const INTL_MARGIN_LABELS: Record<string, [string, string]> = {
	strength: ['Strength gap', 'Home minus away Current Strength (the national team ranking), 100 points = 1 goal'],
	home_advantage: ['Home advantage', 'The same for every national team: 0.5 goals. None at a neutral ground']
};
const SOURCE_TEXT: Record<string, string> = {
	prospective: 'captured before kickoff', late_observation: 'captured after kickoff', reconstruction: 'reconstructed afterwards from pre-match data'
};
const whole = (v: number) => Math.round(v).toLocaleString('en-GB');
const pair = (h: number | null | undefined, a: number | null | undefined, f: (v: number) => string = whole) =>
	h == null && a == null ? null : `${h == null ? '–' : f(h)} · ${a == null ? '–' : f(a)}`;

export function matchDetail(m: Match, x: (Why & { model_info?: { name?: string; code?: string } | null }) | null, home: string, away: string): { sections: DetailSection[]; notes: string[] } {
	const finished = FINISHED.has(m.status) && m.hg != null;
	const sections: DetailSection[] = [], notes: string[] = [];
	const add = (title: string, rows: (DetailRow | null)[], o: { unit?: string; note?: string } = {}) => {
		const kept = rows.filter((r): r is DetailRow => !!r);
		if (kept.some((r) => !r.teams)) sections.push({ title, rows: kept, ...o });
	};
	const row = (label: string, value: string | { when: string } | null | undefined, tip = ''): DetailRow | null =>
		value == null || value === '' ? null : { label, value, ...(tip ? { tip } : {}) };

	if (x) {
		const missing = x.fallback?.map((f, i) => (f ? (i ? away : home) : null)).filter(Boolean) || [];
		add('Strength', [
			{ label: '', value: `${home} · ${away}`, teams: true },
			row('Current Strength', pair(...x.current), 'Elo rating now, from recent results'),
			row('Baseline Strength', pair(...x.baseline), 'Long-term level (LT ALGO)'),
			row('Used for this match', pair(...x.match), 'A blend of Current and Baseline Strength; matches further away lean more on Baseline'),
			x.steps?.now_share != null ? row('Blend', `${Math.round(x.steps.now_share * 100)}% Current · ${100 - Math.round(x.steps.now_share * 100)}% Baseline`,
				`${Math.round(x.steps.weights.now[0] * 100)}% Current for a match today, sliding to ${Math.round(x.steps.weights.now[1] * 100)}% for one a year or more away`) : null
		], missing.length ? { note: `No rating history yet for ${missing.join(' or ')}: the competition's starting strength was used.` } : {});
		add('Expected margin', [
			...Object.entries(x.margin).map(([k, v]) => { const [label, tip] = (m.intl && INTL_MARGIN_LABELS[k]) || MARGIN_LABELS[k] || [k, '']; return row(label, signedGoals(v), tip); }),
			row('Total', signedGoals(x.exp_diff), "The model's expected home minus away goals")
		], { unit: 'goals, + favours home' });
		if (x.steps) workedSteps(x.steps, x.exp_diff, home, away, add, row);
	}

	add('Goals', [
		x && m.intl ? row('Two level sides', `${x.league_goals.toFixed(1)} a game`, 'The goals a match between two evenly ranked national teams is expected to have; the expected margin moves it from there') : null,
		x && !m.intl ? row('Competition average', `${x.league_goals.toFixed(1)} a game`, 'Average goals per game in this competition over the last 12 months') : null,
		x?.tendencies != null ? row('Attack/defence tendencies', `${signedGoals(x.tendencies)} total`, "How much both clubs' attacking and defensive styles move the expected total, against level sides") : null,
		m.home_xg != null && m.away_xg != null ? row('Projected total', (m.home_xg + m.away_xg).toFixed(1)) : null,
		m.p_over25 != null && m.p_btts != null ? row('Over 2.5 · both score', `${Math.round(m.p_over25 * 100)}% · ${Math.round(m.p_btts * 100)}%`) : null
	]);

	const [missH, missA] = x ? x.missing : [m.home_missing, m.away_missing];
	add('Known absences', [row('Missing players', pair(missH, missA, (v) => v.toFixed(1)),
		'Players listed injured, suspended or doubtful, weighted by their share of recent minutes (1.0 = one ever-present player). – = no injury list')]);

	const xi = m.home_xi != null && m.away_xi != null;
	add(finished ? 'Line-ups' : 'Predicted line-ups', [
		xi ? row(`${finished ? 'Starting' : 'Predicted'} XI rating`, `${Math.round(m.home_xi!)} · ${Math.round(m.away_xi!)}`, 'Average player rank (0–100)') : null,
		xi && m.home_recent_xi != null && m.away_recent_xi != null ? row('Last 5 XIs', `${Math.round(m.home_recent_xi)} · ${Math.round(m.away_recent_xi)}`) : null,
		...(x?.lines ? ['DEF', 'MID', 'FWD'].map((k, j) => row(`Model input, ${k}`, pair(x.lines![0][j + 1], x.lines![1][j + 1]), "The predicted XI's average rank in this line, as the model used it")) : [])
	]);

	if (m.m_home != null && m.m_draw != null && m.p_home != null && m.p_draw != null) {
		const model = shownProbs(m.p_home, m.p_draw), market = shownProbs(m.m_home, m.m_draw);
		const diff = model.map((v, i) => { const d = v - market[i]; return `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d)}`; });
		add('Model vs market', [
			row('Model', `${model.join(' · ')}%`),
			row('Market fair', `${market.join(' · ')}%`, 'The average across bookmakers with their margin removed'),
			row('Difference', `${diff.join(' · ')} pts`, 'Model probability minus market fair probability, in percentage points. A difference is a disagreement with the market, not a betting edge or proof of value.')
		], { unit: 'H · D · A', note: 'A disagreement with the market, not a betting edge.' });
	}

	if (x) {
		const v = x.model_info;
		add('Data', [
			x.neutral ? row('Venue', 'Neutral ground', 'No home advantage counted') : null,
			row('Model inputs', { when: x.captured_at }, `Inputs ${SOURCE_TEXT[x.source] || x.source}`),
			x.source !== 'prospective' ? row('Captured', SOURCE_TEXT[x.source] || x.source) : null,
			row('Injury list seen', x.injuries_at ? { when: x.injuries_at } : null),
			row('Odds seen', x.odds_at ? { when: x.odds_at } : null),
			row('Model version', v?.name ? `${v.name}${v.code ? ` · ${v.code}` : ''}` : null, x.model ? `Version id ${x.model.slice(0, 11)}` : '')
		]);
	} else if (m.p_home != null) notes.push("No breakdown for this prediction: its captured model inputs aren't available.");
	notes.push("These are the model's inputs and how much each moved its numbers, not a statement of what will decide the match.");
	return { sections, notes };
}

const two = (v: number | null) => (v == null ? '–' : v.toFixed(2));
const pct = (p: [number, number, number]) => `${shownProbs(p[0], p[1]).join(' · ')}%`;
type Add = (title: string, rows: (DetailRow | null)[], o?: { unit?: string; note?: string }) => void;
type Row = (label: string, value: string | null | undefined, tip?: string) => DetailRow | null;

// From each side's goals record to the chances, one step at a time, with the numbers and weights
// the model used. Every figure is the stored one; the sums only show how they follow
function workedSteps(s: Steps, expDiff: number, home: string, away: string, add: Add, row: Row) {
	const [h, a] = s.record, w = s.weights;
	add("Each side's usual goals", [
		{ label: '', value: `${home} · ${away}`, teams: true },
		row('Scored', `${two(h[0])} · ${two(a[0])}`, `${home} at home and ${away} away, over the last 12 months. xG is used instead of goals for any match that has it`),
		row('Conceded', `${two(h[1])} · ${two(a[1])}`),
		row('Games', `${h[2]} · ${a[2]}`),
		row('Competition average', `${two(s.league[0])} home · ${two(s.league[1])} away`),
		row(`Home goals, ${home}`, `(${two(s.shrunk[0])} + ${two(s.shrunk[1])}) ÷ 2 = ${two(s.plain[0])}`, `${home}'s scoring at home and ${away}'s conceding away, each pulled towards the competition's average`),
		row(`Away goals, ${away}`, `(${two(s.shrunk[2])} + ${two(s.shrunk[3])}) ÷ 2 = ${two(s.plain[1])}`, `${away}'s scoring away and ${home}'s conceding at home, each pulled towards the competition's average`)
	], { unit: 'a game', note: `Each average counts ${w.shrink} games at the competition's average as well as the side's own, so a short record moves the numbers less.` });
	if (s.open_total != null) {
		const records = s.plain[0] + s.plain[1];
		add('How open the game is', [
			row('From the goals records', records.toFixed(2), 'The two numbers above added up'),
			row('From attack and defence', s.open_total.toFixed(2), "Both clubs' attacking and defensive ratings, for two level sides"),
			row('Blended', `${Math.round((1 - w.open) * 100)}% × ${records.toFixed(2)} + ${Math.round(w.open * 100)}% × ${s.open_total.toFixed(2)} = ${(s.base[0] + s.base[1]).toFixed(2)}`),
			row('Goals before the margin', `${two(s.base[0])} · ${two(s.base[1])}`, 'The two sides keep their shares of the total')
		], { unit: 'total goals' });
	}
	add('Projected goals', [
		row('Expected margin', signedGoals(expDiff), 'From the expected margin above'),
		row('Scaled', `${two(s.base[0])} × ${s.scale.toFixed(3)} · ${two(s.base[1])} ÷ ${s.scale.toFixed(3)}`, "One factor raises the home side's goals and lowers the away side's until the gap between them is the expected margin"),
		row('Projected goals', `${two(s.xg[0])} · ${two(s.xg[1])}`)
	]);
	add('Chances', [
		row('From the projected goals', pct(s.poisson), "Each side's goals as a Poisson distribution, 0 to 10 goals, every scoreline's chance added up"),
		row('Draw boost', `× ${s.boost.toFixed(3)}`, `Up to × ${w.draw[0]} in a close game, none once the projected margin reaches ${w.draw[1]} goals: models like this one under-count draws`),
		row('Final chances', pct(s.chances)),
		row('Most likely score', s.likely)
	], { unit: 'H · D · A' });
}
