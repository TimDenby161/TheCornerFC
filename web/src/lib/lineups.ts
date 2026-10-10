// A match's line-ups as its card shows them: each side's eleven on a pitch. For a finished match
// the eleven that started, each marked as predicted or not against the model's pre-match XI.
import { shortName } from './club.ts';
import { xiSpots } from './depth.ts';
import { GROUP_OF } from './playerFilters.ts';

// a line-up row from the database: [player, name, role, rank (null where it is for subscribers)]
export type XiRow = [number, string, string | null, number | null];
export type Starter = { id: number; name: string; label: string; rank: number | null; chance?: number | null; mins?: number | null; predicted?: boolean; instead?: XiRow };

const LINE_OF_ROLE: Record<string, string> = { GK: 'GK', CB: 'D', LB: 'D', RB: 'D', LWB: 'D', RWB: 'D', DM: 'M', CM: 'M', LM: 'M', RM: 'M', AM: 'M', LW: 'F', RW: 'F', ST: 'F' };
// Marks each starter of an actual XI as predicted or not, against the model's pre-match XI. Each
// starter it missed is paired with a predicted player who didn't start: same position first, then
// the same position group, then the same line, then anyone. Returns how many it got right.
export function markPredicted(xi: Starter[], predicted: XiRow[]): number {
	const started = new Set(xi.map((c) => c.id));
	const picked = new Set(predicted.map(([pid]) => pid));
	const spare = predicted.filter(([pid]) => !started.has(pid));
	const missed = xi.filter((c) => !picked.has(c.id));
	for (const c of xi) c.predicted = picked.has(c.id);
	const tests: ((a: string, b: string | null) => boolean)[] = [
		(a, b) => a === b, (a, b) => !!b && GROUP_OF[a] === GROUP_OF[b], (a, b) => !!b && LINE_OF_ROLE[a] === LINE_OF_ROLE[b], () => true];
	for (const same of tests) for (const c of missed) {
		if (c.instead) continue;
		const i = spare.findIndex(([, , role]) => same(c.label, role));
		if (i !== -1) c.instead = spare.splice(i, 1)[0];
	}
	return xi.length - missed.length;
}

// A match to come: each predicted starter with his Ability, the number his own page shows (the
// stored line-up carries his rank over his recent matches, which it doesn't); none where he has
// no Ability or it is for subscribers
export const withAbility = (rows: XiRow[], ability: Map<number, number | null>): XiRow[] =>
	rows.map(([pid, name, role]) => [pid, name, role, ability.get(pid) ?? null]);
// The average of an eleven's ranks to a whole number, those without one left out
export function averageRank(ranks: (number | null)[]): number | null {
	const known = ranks.filter((r): r is number => r != null);
	return known.length ? Math.round(known.reduce((t, r) => t + r, 0) / known.length) : null;
}

// Where each starter stands and what his spot says. `ranks`: whether ranks are shown at all
// (national sides have none).
export type Spot = ReturnType<typeof spots>[number];
export function spots(xi: Starter[], ranks = true) {
	return xiSpots(xi.map((s) => ({ ...s, box: { label: s.label } }))).map(({ c, x, y }) => {
		const hasChance = c.chance != null, hasMins = c.mins != null, marked = c.predicted != null;
		const [, predName, , predRank] = c.instead || [];
		const verdict = !marked ? '' : c.predicted ? ' · predicted to start'
			: ` · not predicted${c.instead ? `; the model picked ${predName} (rank ${predRank != null ? Number(predRank).toFixed(1) : '–'})` : ''}`;
		return {
			id: c.id, name: shortName(c.name), label: c.label, x: Math.round(x), y, rank: c.rank,
			chance: hasChance ? Math.round(c.chance!) : null, mins: hasMins ? c.mins! : null,
			predicted: marked ? !!c.predicted : null,
			instead: c.instead ? { name: shortName(predName as string), rank: predRank ?? null } : null,
			tip: `${c.name} · ${c.label}${ranks ? ` · rank ${c.rank != null ? Number(c.rank).toFixed(1) : '–'}` : ''}${hasChance ? ` · ${Math.round(c.chance!)}% to start` : ''}${hasMins ? ` · ${c.mins}′ expected` : ''}${verdict}`
		};
	});
}
