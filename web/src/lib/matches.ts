// Matches as the database's site_matches gives them: rows in the order of the "site" row's
// match_fields. A visitor who isn't a subscriber gets the paid fields of matches to come as null.
export type Match = {
	id: number; kickoff: string; league: number; round: string | null; home: number; away: number; status: string;
	hg: number | null; ag: number | null; pen_h: number | null; pen_a: number | null;
	p_home: number | null; p_draw: number | null; p_away: number | null;
	home_xg: number | null; away_xg: number | null; likely: string | null;
	home_rank: number | null; away_rank: number | null; source: string | null;
	home_xi: number | null; away_xi: number | null; home_missing: number | null; away_missing: number | null;
	home_recent_xi: number | null; away_recent_xi: number | null;
	// how the prediction did, 1 to 5, once the match is over, and its five parts
	rating: number | null; r_winner: number | null; r_margin: number | null; r_clean_sheets: number | null; r_shape: number | null; r_goals: number | null;
	// the market's chances with the margin taken out (away is what is left), over 2.5 and both to score
	m_home: number | null; m_draw: number | null; p_over25: number | null; p_btts: number | null;
	intl: number | null;
	// the key reasons its card shows: [input, goals of margin (+ favours the home side)]
	reasons?: [string, number][];
};
export type MatchesAnswer = { matches: (string | number | null)[][]; reasons?: Record<string, [string, number][]>; paywall?: boolean };

export const FINISHED = new Set(['FT', 'AET', 'PEN', 'AWD', 'WO']);
export const LIVE = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE', 'INT', 'SUSP']);
export const CALLED_OFF = new Set(['CANC', 'PST', 'ABD']);
// ... and on a match card, one awarded or walked over has nothing to predict either
export const NO_GAME = new Set(['PST', 'CANC', 'ABD', 'AWD', 'WO']);

export const matchRows = (fields: string[], answer: MatchesAnswer): Match[] =>
	answer.matches
		.map((row) => Object.fromEntries(fields.map((f, i) => [f, row[i]])) as unknown as Match)
		.map((m) => (answer.reasons?.[m.id] ? { ...m, reasons: answer.reasons[m.id] } : m))
		.sort((a, b) => a.kickoff.localeCompare(b.kickoff) || a.id - b.id);
// still to be played (or being played), oldest first
export const upcoming = (list: Match[]) => list.filter((m) => !FINISHED.has(m.status) && !CALLED_OFF.has(m.status));
export const roundName = (r: string) => r.replace(/^Regular Season - /, 'Round ').replace(/^League Stage - /, 'League phase ');
