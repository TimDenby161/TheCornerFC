import { describe, expect, it } from 'vitest';
import { matchDetail, type Why } from './matchDetail';
import type { Match } from './matches';

const m = { id: 1, status: 'NS', hg: null, intl: 0, p_home: 0.62, p_draw: 0.213, p_away: 0.167, m_home: 0.684, m_draw: 0.196, home_xg: 1.9, away_xg: 0.8,
	p_over25: 0.55, p_btts: 0.46, home_xi: 88.4, away_xi: 79.6, home_recent_xi: 87, away_recent_xi: 80, home_missing: 0.4, away_missing: 1.2 } as Match;
const why: Why & { model_info: { name: string; code: string } } = {
	fallback: [false, true], current: [1094, 1025], baseline: [1096, 1017], match: [1095, 1021],
	margin: { strength: 0.74, home_advantage: 0.3, absences: -0.02 }, exp_diff: 1.02, league_goals: 2.9, tendencies: -0.12,
	missing: [0.4, 1.2], lines: [[90, 88, 89, 87], [80, 79, 81, 78]], captured_at: '2026-10-07T10:24:16+00:00', source: 'prospective',
	injuries_at: '2026-10-07T09:54:25+00:00', odds_at: null, model: 'abcdef0123456789', model_info: { name: 'match-prediction', code: 'c355108' }
};

describe('matchDetail', () => {
	const { sections, notes } = matchDetail(m, why, 'Arsenal', 'Leeds');
	const section = (title: string) => sections.find((s) => s.title === title)!;
	const value = (title: string, label: string) => section(title).rows.find((r) => r.label === label)?.value;
	it('sets the strengths out side by side, and says when a club had no history', () => {
		expect(value('Strength', 'Current Strength')).toBe('1,094 · 1,025');
		expect(section('Strength').note).toBe("No rating history yet for Leeds: the competition's starting strength was used.");
	});
	it('lists what moved the expected margin, in goals', () => {
		expect(section('Expected margin').rows.map((r) => [r.label, r.value])).toEqual([['Strength gap', '+0.7'], ['Home advantage', '+0.3'], ['Known absences', '≈0'], ['Total', '+1.0']]);
		expect(section('Expected margin').unit).toBe('goals, + favours home');
	});
	it('gives goals, absences and line-ups', () => {
		expect(value('Goals', 'Projected total')).toBe('2.7');
		expect(value('Goals', 'Over 2.5 · both score')).toBe('55% · 46%');
		expect(value('Known absences', 'Missing players')).toBe('0.4 · 1.2');
		expect(value('Predicted line-ups', 'Predicted XI rating')).toBe('88 · 80');
		expect(value('Predicted line-ups', 'Model input, MID')).toBe('89 · 81');
	});
	it('compares the model with the market in whole points', () => {
		expect(value('Model vs market', 'Model')).toBe('62 · 21 · 17%');
		expect(value('Model vs market', 'Difference')).toBe('−6 · +1 · +5 pts');
	});
	it('says when the inputs were seen and which model it was, leaving out what it has no time for', () => {
		expect(value('Data', 'Model inputs')).toEqual({ when: '2026-10-07T10:24:16+00:00' });
		expect(section('Data').rows.map((r) => r.label)).toEqual(['Model inputs', 'Injury list seen', 'Model version']);
		expect(value('Data', 'Model version')).toBe('match-prediction · c355108');
		expect(notes).toHaveLength(1);
	});
	it('says so when a prediction has no stored explanation, and still shows what the match holds', () => {
		const bare = matchDetail(m, null, 'Arsenal', 'Leeds');
		expect(bare.notes[0]).toMatch(/No breakdown/);
		expect(bare.sections.map((s) => s.title)).toEqual(['Goals', 'Known absences', 'Predicted line-ups', 'Model vs market']);
	});
	it('names a finished match\'s line-ups as the ones that started, and a national match by its own labels', () => {
		expect(matchDetail({ ...m, status: 'FT', hg: 2 } as Match, null, 'A', 'B').sections.some((s) => s.title === 'Line-ups')).toBe(true);
		const intl = matchDetail({ ...m, intl: 1 } as Match, why, 'England', 'Wales');
		expect(intl.sections.find((s) => s.title === 'Expected margin')!.rows[1].tip).toMatch(/national team/);
		expect(intl.sections.find((s) => s.title === 'Goals')!.rows[0].label).toBe('Two level sides');
	});
	it('works through the steps from goals records to chances, with the weights used', () => {
		const steps: NonNullable<Why['steps']> = {
			now_share: 0.6, record: [[1.67, 1.03, 17], [1.1, 1.5, 16]], league: [1.5, 1.2], shrunk: [1.62, 1.39, 1.13, 1.12], plain: [1.51, 1.13],
			open_total: 2.81, base: [1.6, 1.2], scale: 1.123, xg: [1.8, 1.07], poisson: [0.52, 0.24, 0.24], boost: 1.051, chances: [0.508, 0.252, 0.24], likely: '1-1',
			weights: { now: [0.6, 0.2], shrink: 6, open: 0.75, draw: [1.1, 1.5], absence: 0.1, line: 0.005 }
		};
		const d = matchDetail(m, { ...why, steps }, 'Arsenal', 'Leeds');
		const v = (title: string, label: string) => d.sections.find((s) => s.title === title)?.rows.find((r) => r.label === label)?.value;
		expect(d.sections.map((s) => s.title).slice(0, 6)).toEqual(['Strength', 'Expected margin', "Each side's usual goals", 'How open the game is', 'Projected goals', 'Chances']);
		expect(v('Strength', 'Blend')).toBe('60% Current · 40% Baseline');
		expect(v("Each side's usual goals", 'Home goals, Arsenal')).toBe('(1.62 + 1.39) ÷ 2 = 1.51');
		expect(d.sections.find((s) => s.title === "Each side's usual goals")!.note).toMatch(/counts 6 games/);
		expect(v('How open the game is', 'Blended')).toBe('25% × 2.64 + 75% × 2.81 = 2.80');
		expect(v('Projected goals', 'Scaled')).toBe('1.60 × 1.123 · 1.20 ÷ 1.123');
		expect(v('Chances', 'From the projected goals')).toBe('52 · 24 · 24%');
		expect(v('Chances', 'Final chances')).toBe('51 · 25 · 24%');
		expect(v('Chances', 'Draw boost')).toBe('× 1.051');
		const plain = matchDetail(m, { ...why, steps: { ...steps, open_total: null, now_share: null } }, 'Arsenal', 'Leeds');
		expect(plain.sections.some((s) => s.title === 'How open the game is')).toBe(false);
		expect(plain.sections.find((s) => s.title === 'Strength')!.rows.some((r) => r.label === 'Blend')).toBe(false);
	});
});
