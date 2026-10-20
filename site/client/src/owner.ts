// The owner-only fantasy data (owner.svelte.ts), asked for once by the fantasy page that opens and
// kept in this browser only: the server never holds it, so one visitor's can't reach another.
import { useEffect, useSyncExternalStore } from 'react';
import type { Lock, OwnerAnswer, PredDoc, TeamDoc } from '../../../web/src/lib/fantasy.ts';

export type Owner = {
	// idle: not asked yet; busy: asking; ok: the owner; no: anyone else (error: why, where there is one)
	status: 'idle' | 'busy' | 'ok' | 'no';
	error: string;
	fpl: PredDoc | null;
	team: TeamDoc | null;
	efl: PredDoc | null;
	locks: Lock[];
	// the owner's own ticks on the FPL page: player -> [in my team, a target]
	marks: Map<number, [boolean, boolean]>;
	// players with a page of their own on this site (their names link to it), and those asked about
	known: Map<number, boolean>;
};
let owner: Owner = { status: 'idle', error: '', fpl: null, team: null, efl: null, locks: [], marks: new Map(), known: new Map() };
const watchers = new Set<() => void>();
const set = (change: Partial<Owner>) => { owner = { ...owner, ...change }; for (const w of watchers) w(); };
const watch = (w: () => void) => { watchers.add(w); return () => watchers.delete(w); };

// The owner's data as it stands, asked for on first use. email: the signed-in visitor's, or null.
export function useOwner(email: string | null): Owner {
	useEffect(() => { void loadOwner(email); }, [email]);
	return useSyncExternalStore(watch, () => owner);
}
export const setLocks = (locks: Lock[]) => set({ locks });

// Remembered in this browser so the menu has the Fantasy links from the start of the next visit.
// It decides nothing else: every page asks the database again.
const remember = (yes: boolean) => {
	document.cookie = `owner=${yes ? 1 : ''}; path=/; max-age=${yes ? 31536000 : 0}; samesite=lax${location.protocol === 'https:' ? '; secure' : ''}`;
};

let asked = false;
async function loadOwner(email: string | null) {
	if (asked) return;
	asked = true;
	if (!email) { set({ status: 'no' }); remember(false); return; }
	set({ status: 'busy' });
	let d: OwnerAnswer;
	try {
		const r = await fetch('/fantasy/data');
		if (!r.ok) throw new Error(String(r.status));
		d = await r.json();
	} catch {
		d = { ok: false, error: "Couldn't reach the database just now." };
	}
	if (!d.ok) { set({ error: d.error || '', status: 'no' }); if (!d.error) remember(false); return; }
	set({
		fpl: d.docs?.fpl_predictions || null, team: d.docs?.fpl_team || null, efl: d.docs?.efl_predictions || null, locks: d.locks || [],
		marks: new Map((d.marks || []).map(([id, mine, target]) => [id, [mine, target]])), status: 'ok'
	});
	remember(true);
}

// Which of these players have a page here: asked a screenful at a time, each player once
export async function askKnown(ids: number[]) {
	const need = [...new Set(ids)].filter((id) => id > 0 && !owner.known.has(id)).slice(0, 1000);
	if (!need.length) return;
	set({ known: new Map([...owner.known, ...need.map((id) => [id, false] as const)]) });
	try {
		const r = await fetch('/fantasy/known', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ids: need }) });
		if (!r.ok) return;
		const yes = (await r.json()).ids as number[];
		set({ known: new Map([...owner.known, ...yes.map((id) => [id, true] as const)]) });
	} catch { /* names stay plain */ }
}

async function post<T>(path: string, body: unknown): Promise<T | null> {
	try {
		const r = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
		return r.ok ? ((await r.json()) as T) : null;
	} catch { return null; }
}
// A tick is shown at once and saved to the owner's account; one that can't be saved is undone.
// Answers what went wrong, or "" when it is saved.
export async function markPlayer(id: number, which: 0 | 1, on: boolean): Promise<string> {
	const was = owner.marks.get(id) || [false, false];
	const now: [boolean, boolean] = which === 0 ? [on, was[1]] : [was[0], on];
	const put = (v: [boolean, boolean]) => {
		const marks = new Map(owner.marks);
		if (v[0] || v[1]) marks.set(id, v); else marks.delete(id);
		set({ marks });
	};
	put(now);
	const res = await post<{ ok: boolean; error?: string }>('/fantasy/mark', { player: id, mine: now[0], target: now[1] });
	if (res?.ok) return '';
	// unless it has been changed again since
	if ((owner.marks.get(id) || [false, false]).join() === now.join()) put(was);
	return `${res?.error || "Couldn't save that just now."} The box has been put back.`;
}
export const lockTransfers = (body: { undo: boolean; season: number | string; event: number; transfers?: unknown[] }) =>
	post<{ ok: boolean; error?: string; locked_at?: string }>('/fantasy/lock', body);
