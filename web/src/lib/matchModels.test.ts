import { describe, expect, it } from 'vitest';
import { MATCH_MODEL_LABELS, MATCH_MODELS, apartRow, asModelCompare, isMatchModel, otherModel, scoreRows, upcomingSummary } from './matchModels.ts';

describe('the two match models', () => {
	it('knows the two names and nothing else', () => {
		expect(MATCH_MODELS.every(isMatchModel)).toBe(true);
		for (const bad of ['', 'A18', 'base ', null, undefined, 1]) expect(isMatchModel(bad)).toBe(false);
		expect(Object.keys(MATCH_MODEL_LABELS).sort()).toEqual([...MATCH_MODELS].sort());
	});
	it('offers the one that is not live', () => {
		expect(otherModel('base')).toBe('a18');
		expect(otherModel('a18')).toBe('base');
	});
});



describe('the two models compared', () => {
	const upcoming = { n: 200, different_favourite: 10, mean_gap: { home: 0.024, draw: 0.011, away: 0.021 }, a18_home_higher: 90 };
	it('takes only an administrator’s answer', () => {
		expect(asModelCompare({ ok: false })).toBeNull();
		expect(asModelCompare(null)).toBeNull();
		expect(asModelCompare({ ok: true, start: '2026-10-15', finished: {}, upcoming, apart: [] })?.upcoming.n).toBe(200);
	});
	it('marks each measure better or worse for A18, lower log loss and Brier, more right results', () => {
		const { n, rows } = scoreRows({ base: { n: 600, log_loss: 1.0, brier: 0.6, accuracy: 0.5 }, a18: { n: 600, log_loss: 0.99, brier: 0.61, accuracy: 0.52 } });
		expect(n).toBe(600);
		expect(rows.map((r) => r.mark)).toEqual(['better', 'worse', 'better']);
		expect(rows[0].gap).toBe('−0.0100');
		expect(rows[2]).toMatchObject({ base: '50.0%', a18: '52.0%', gap: '+2.0 pts' });
	});
	it('shows nothing before any match has finished', () => {
		expect(scoreRows({}).rows).toEqual([]);
		expect(scoreRows({ base: { n: 0, log_loss: 0, brier: 0, accuracy: 0 }, a18: { n: 0, log_loss: 0, brier: 0, accuracy: 0 } }).n).toBe(0);
	});
	it('puts an upcoming fixture’s two predictions side by side', () => {
		const r = apartRow({ fixture: 1, kickoff: '2026-10-17T14:00:00Z', league: 'FA Cup', home: 'Altrincham', away: 'Man Utd', differ: true, gap: 0.2057,
			base: [0.39, 0.25, 0.36, 1.72, 1.63], a18: [0.6, 0.2, 0.2, 2.26, 1.24] });
		expect(r).toMatchObject({ match: 'Altrincham v Man Utd', base: '39% · 25% · 36%', a18: '60% · 20% · 20%', baseXg: '1.72–1.63', gap: '20.6 pts', differ: true });
	});
	it('says how far apart they are', () => {
		expect(upcomingSummary(upcoming)).toContain('different favourite in 10 (5.0%)');
		expect(upcomingSummary({ ...upcoming, n: 0 })).toMatch(/No upcoming/);
	});
});
