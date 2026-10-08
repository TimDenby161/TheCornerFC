import { describe, expect, it } from 'vitest';
import { bankAfter, betProbs, betScope, betTeams, gbp, onePerPick, signedGbp, summarise, tipLabel, type Bet } from './bets';

let nextId = 1;
const bet = (o: Partial<Bet>): Bet => ({ id: nextId++, strategy: 'early', fixture: 1, kickoff: '2026-10-01T19:00:00+00:00', league: 39, market: '1X2', selection: 'Home',
	model_prob: 0.6, fair_prob: 0.5, odds: 2, closing_odds: 1.9, clv: 0.05, result: null, profit: null, home: 'Arsenal', away: 'Leeds', home_id: 42, away_id: 63, score: null, cautious: true, ...o });

describe('one bet of each kind a match', () => {
	const bets = [bet({ fixture: 1, market: '1X2' }), bet({ fixture: 1, market: '1X2', strategy: 'late' }), bet({ fixture: 1, market: 'OU25', strategy: 'late' }),
		bet({ fixture: 1, market: 'OU35' }), bet({ fixture: 2, market: '1X2', strategy: 'late' })];
	it('counts the night-before bet when both runs bet the same kind, a goal line being one kind', () => {
		expect(onePerPick(bets).map((b) => [b.fixture, b.market, b.strategy])).toEqual([[1, '1X2', 'early'], [1, 'OU35', 'early'], [2, '1X2', 'late']]);
	});
	it('shows each run\'s own bets when one is picked, and narrows by market and to cautious bets', () => {
		expect(betScope(bets, { strategy: 'late', market: 'all', view: 'all' })).toHaveLength(3);
		expect(betScope(bets, { strategy: 'all', market: 'OU35', view: 'all' })).toHaveLength(1);
		expect(betScope([bet({ cautious: false }), bet({ fixture: 9 })], { strategy: 'all', market: 'all', view: 'cautious' })).toHaveLength(1);
	});
});

describe('summarise', () => {
	const bets = [bet({ result: 'win', profit: 1, clv: 0.05 }), bet({ result: 'loss', profit: -1, clv: -0.02 }), bet({ result: 'win', profit: 0.5, clv: null }), bet({ result: 'void', profit: 0 }), bet({})];
	const s = summarise(bets, 10);
	it('counts settled, won and pending, and the paper profit and return', () => {
		expect(s).toMatchObject({ placed: 5, settled: 3, pending: 1, atRisk: 10, wins: 2, profit: 5, staked: 30 });
		expect(s.roi).toBeCloseTo(1 / 6, 9);
	});
	it('counts how often it beat the closing price, among bets with one', () => {
		expect(s.beat).toBe(0.5);
		expect(summarise([bet({})], 10)).toMatchObject({ settled: 0, roi: null, beat: null });
	});
	it('runs the bank through the settled bets, oldest first', () => {
		const a = bet({ result: 'loss', profit: -1, kickoff: '2026-10-02T19:00:00+00:00' }), b = bet({ result: 'win', profit: 1.5, kickoff: '2026-10-01T19:00:00+00:00' });
		const bank = bankAfter([a, b, bet({})], 10, 1000);
		expect(bank.get(b.id)).toBe(1015);
		expect(bank.get(a.id)).toBe(1005);
		expect(bank.size).toBe(2);
	});
});

describe('words and money', () => {
	it('names a selection', () => {
		expect(tipLabel(bet({ selection: 'Away' }))).toBe('Leeds to win');
		expect(tipLabel(bet({ selection: 'Draw' }))).toBe('Draw');
		expect(tipLabel(bet({ market: 'BTTS', selection: 'No' }))).toBe('Both teams to score: No');
		expect(tipLabel(bet({ market: 'OU25', selection: 'Over 2.5' }))).toBe('Over 2.5 goals');
	});
	it('says what the model and the market thought when it was taken', () => {
		expect(betProbs(bet({ model_prob: 0.745, fair_prob: 0.621 }))).toBe('When taken: model 75% · market fair 62% · difference +13 pts');
		expect(betProbs(bet({ fair_prob: null }))).toBe('When taken: model 60% · market fair –');
	});
	it('writes pounds', () => {
		expect(gbp(1234.5)).toBe('£1,234.50');
		expect(gbp(-3)).toBe('−£3.00');
		expect(gbp(null)).toBe('–');
		expect(signedGbp(12)).toBe('+£12.00');
		expect(signedGbp(0)).toBe('£0.00');
	});
	it('gives a bet the badge of the team it backs, or both for a draw or goals bet', () => {
		expect(betTeams(bet({ selection: 'Away' }))).toEqual([{ id: 63, name: 'Leeds' }]);
		expect(betTeams(bet({ selection: 'Draw' }))).toHaveLength(2);
		expect(betTeams(bet({ market: 'OU25', home_id: null }))).toEqual([{ id: 63, name: 'Leeds' }]);
	});
});
