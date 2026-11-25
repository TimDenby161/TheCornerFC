// Beat the Model (T-095): what the game page needs to decide about each match of a round
// (site/client/src/BeatTheModelPage.tsx). The database holds the rules
// (db/migrations/20261123_beat_the_model.sql); this only draws them.

export type BtmMatch = {
	id: number; kickoff: string; home: number; away: number; status: string | null;
	hg: number | null; ag: number | null;
	pick: [number, number] | null; points: number | null;
	model: string | null; model_points: number | null;
};
export type BtmRound = {
	ok: boolean; error?: string; season?: number; round?: number | null; name?: string | null;
	matches?: BtmMatch[]; teams?: Record<string, string>;
};
// [position, name, points, exact, results, played, is it me]
export type BtmRow = [number, string, number, number, number, number, boolean];
export type BtmTable = {
	ok: boolean; error?: string; season?: number; round?: number | null; players?: number;
	top?: BtmRow[]; me?: BtmRow | null; model?: [number, number, number, number] | null;
};

export const FINISHED = new Set(['FT', 'AET', 'PEN']);
const OFF = new Set(['PST', 'CANC', 'ABD', 'AWD', 'WO']);

// open: can be picked; picked: picked, not kicked off; missed: kicked off unpicked;
// live: under way; done: finished; off: postponed or called off
export type BtmState = 'open' | 'picked' | 'missed' | 'live' | 'done' | 'off';
export function matchState(m: BtmMatch, now: number): BtmState {
	if (m.status && OFF.has(m.status)) return 'off';
	if (m.status && FINISHED.has(m.status)) return 'done';
	if (Date.parse(m.kickoff) > now) return m.pick ? 'picked' : 'open';
	return m.pick ? 'live' : 'missed';
}

// A score box's text as goals, or null: a whole number from 0 to 20
export function goals(text: string): number | null {
	const t = text.trim();
	if (!/^\d{1,2}$/.test(t)) return null;
	const n = Number(t);
	return n <= 20 ? n : null;
}

// What the database would give a pick against a full-time score (btm_points): 3, 1 or 0
export function pointsFor(pick: [number, number], hg: number, ag: number): number {
	if (pick[0] === hg && pick[1] === ag) return 3;
	return Math.sign(pick[0] - pick[1]) === Math.sign(hg - ag) ? 1 : 0;
}

// The round's points so far: yours and the model's, over the matches marked
export function roundScore(ms: BtmMatch[]): { you: number; model: number; marked: number } {
	let you = 0, model = 0, marked = 0;
	for (const m of ms) {
		if (m.model_points == null && m.points == null) continue;
		marked++;
		you += m.points ?? 0;
		model += m.model_points ?? 0;
	}
	return { you, model, marked };
}

// A display name the database will take: 3 to 20 letters, digits, spaces, . _ -, not starting
// or ending with a space
export const NAME_RULE = /^[A-Za-z0-9][A-Za-z0-9 ._-]{1,18}[A-Za-z0-9._-]$/;
export const nameOk = (name: string) => NAME_RULE.test(name.trim());

// The round's one-line verdict over its finished matches, the first thing a player reads
export function scoreHeadline(s: { you: number; model: number }): string {
	const d = s.you - s.model, pts = (n: number) => `${n} ${n === 1 ? 'point' : 'points'}`;
	if (d > 0) return `You're beating the model by ${pts(d)}`;
	if (d < 0) return `The model leads you by ${pts(-d)}`;
	return 'Level with the model';
}

// A match's points as its chip shows them: "+3", "+1", "0"
export const pointsText = (n: number) => (n > 0 ? `+${n}` : '0');
