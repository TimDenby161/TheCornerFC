// The paper simulation: bets the model would take where it disagrees with the bookmakers enough,
// at a UK bookmaker's recorded price, with a flat paper stake. No real money. "bets" holds the
// rules and every bet; everything on the two betting pages is counted from it here.
export type Bet = {
	id: number; strategy: 'early' | 'late'; fixture: number; kickoff: string; league: number; market: string; selection: string;
	model_prob: number; fair_prob: number | null; odds: number; closing_odds: number | null; clv: number | null;
	result: 'win' | 'loss' | 'void' | null; profit: number | null; home: string; away: string; home_id: number | null; away_id: number | null;
	score: string | null; cautious: boolean; intl?: boolean | number;
};
export type BetsDoc = { rules: { min_edge: number; max_odds: number; stake_gbp?: number; bank?: number }; bets: Bet[] };
export const SEL_LABELS: Record<string, string> = { Home: 'Home win', Draw: 'Draw', Away: 'Away win', Yes: 'Both score', No: 'Not both score' };
export const BET_MARKETS = ['1X2', 'OU15', 'OU25', 'OU35', 'OU45', 'BTTS'];

// Each kind of bet placed once per match (result, goal line, both teams score): when both runs
// bet it, the night-before bet (placed first) counts
const betKind = (b: Bet) => `${b.fixture}|${b.market.startsWith('OU') ? 'OU' : b.market}`;
export function onePerPick(bets: Bet[]): Bet[] {
	const early = new Set(bets.filter((b) => b.strategy === 'early').map(betKind));
	return bets.filter((b) => b.strategy === 'early' || !early.has(betKind(b)));
}
// Bets on the strategy / market / cautious choices, before the competition menu
export type BetChoices = { strategy: 'all' | 'early' | 'late'; market: string; view: 'all' | 'cautious' };
export function betScope(bets: Bet[], ch: BetChoices): Bet[] {
	return (ch.strategy === 'all' ? onePerPick(bets) : bets).filter((b) =>
		(ch.strategy === 'all' || b.strategy === ch.strategy) && (ch.market === 'all' || b.market === ch.market) && (ch.view === 'all' || b.cautious));
}
export type Summary = { placed: number; settled: number; pending: number; atRisk: number; wins: number; profit: number; staked: number; roi: number | null; beat: number | null };
export function summarise(bets: Bet[], stake: number): Summary {
	const settled = bets.filter((b) => b.result === 'win' || b.result === 'loss');
	const clvs = settled.map((b) => b.clv).filter((c): c is number => c != null);
	const profit = stake * settled.reduce((a, b) => a + (b.profit || 0), 0);
	const staked = stake * settled.length;
	const pending = bets.filter((b) => !b.result).length;
	return {
		placed: bets.length, settled: settled.length, pending, atRisk: stake * pending,
		wins: settled.filter((b) => b.result === 'win').length, profit, staked,
		roi: staked ? profit / staked : null,
		// took better odds than the last price before kickoff
		beat: clvs.length ? clvs.filter((c) => c > 0).length / clvs.length : null
	};
}
// The bank after each settled bet, oldest first: bet id -> bank
export function bankAfter(bets: Bet[], stake: number, bank: number): Map<number, number> {
	const out = new Map<number, number>();
	let running = bank;
	for (const b of bets.filter((b) => b.result).sort((a, b) => Date.parse(a.kickoff) - Date.parse(b.kickoff) || a.id - b.id)) {
		running += stake * (b.profit || 0);
		out.set(b.id, running);
	}
	return out;
}

// ---- Words and money
export const gbp = (x: number | null | undefined) => (x == null ? '–' : `${x < 0 ? '−' : ''}£${Math.abs(x).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
export const signedGbp = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}£${Math.abs(x).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export function tipLabel(b: Bet): string {
	if (b.market === '1X2') return b.selection === 'Draw' ? 'Draw' : `${b.selection === 'Home' ? b.home : b.away} to win`;
	if (b.market === 'BTTS') return b.selection === 'Yes' ? 'Both teams to score: Yes' : 'Both teams to score: No';
	return `${b.selection} goals`;
}
// A paper bet's model probability, market fair probability and the difference, in whole points,
// as they were when it was taken (the match card's bars show the latest prices)
export function betProbs(b: Bet): string {
	const model = Math.round(100 * b.model_prob), fair = b.fair_prob != null ? Math.round(100 * b.fair_prob) : null;
	const diff = fair == null ? '' : ` · difference ${model >= fair ? '+' : '−'}${Math.abs(model - fair)} pts`;
	return `When taken: model ${model}% · market fair ${fair == null ? '–' : `${fair}%`}${diff}`;
}
// the teams whose badge a bet carries: the one it backs, or both for a draw or goals bet
export const betTeams = (b: Bet): { id: number; name: string }[] =>
	(b.market === '1X2' && b.selection !== 'Draw' ? [b.selection === 'Home' ? [b.home_id, b.home] : [b.away_id, b.away]] : [[b.home_id, b.home], [b.away_id, b.away]])
		.filter(([id]) => id).map(([id, name]) => ({ id: id as number, name: name as string }));
