// The owner-only fantasy data, asked for once by whichever of the three pages opens first and
// kept while the visitor moves between them. Only ever touched in the browser: the server never
// holds it, so one visitor's can't reach another.
import { SvelteMap } from 'svelte/reactivity';
import type { Lock, OwnerAnswer, PredDoc, TeamDoc } from './fantasy.ts';

class Owner {
	// idle: not asked yet; busy: asking; ok: the owner; no: anyone else (error: why, where there is one)
	status = $state<'idle' | 'busy' | 'ok' | 'no'>('idle');
	error = $state('');
	// (raw: thousands of rows, read but never changed)
	fpl = $state.raw<PredDoc | null>(null);
	team = $state.raw<TeamDoc | null>(null);
	efl = $state.raw<PredDoc | null>(null);
	locks = $state.raw<Lock[]>([]);
	// the owner's own ticks on the FPL page: player -> [in my team, a target]
	marks = new SvelteMap<number, [boolean, boolean]>();
	// players with a page of their own on this site (their names link to it), and those asked about
	known = new SvelteMap<number, boolean>();
	who: string | null | undefined = undefined;
}
export const owner = new Owner();

// Remembered in this browser so the menu has the Fantasy links from the start of the next visit.
// It decides nothing else: every page asks the database again.
const remember = (yes: boolean) => {
	document.cookie = `owner=${yes ? 1 : ''}; path=/; max-age=${yes ? 31536000 : 0}; samesite=lax${location.protocol === 'https:' ? '; secure' : ''}`;
};

// email: the signed-in visitor's, or null. A different visitor is asked about afresh.
export async function loadOwner(email: string | null) {
	if (owner.who === email && owner.status !== 'idle') return;
	owner.who = email;
	owner.fpl = owner.efl = owner.team = null; owner.locks = []; owner.marks.clear(); owner.error = '';
	if (!email) { owner.status = 'no'; remember(false); return; }
	owner.status = 'busy';
	let d: OwnerAnswer;
	try {
		const r = await fetch('/fantasy/data');
		if (!r.ok) throw new Error(String(r.status));
		d = await r.json();
	} catch {
		d = { ok: false, error: "Couldn't reach the database just now." };
	}
	if (owner.who !== email) return;
	if (!d.ok) { owner.error = d.error || ''; owner.status = 'no'; if (!d.error) remember(false); return; }
	owner.fpl = d.docs?.fpl_predictions || null;
	owner.team = d.docs?.fpl_team || null;
	owner.efl = d.docs?.efl_predictions || null;
	owner.locks = d.locks || [];
	for (const [id, mine, target] of d.marks || []) owner.marks.set(id, [mine, target]);
	owner.status = 'ok';
	remember(true);
}

// Which of these players have a page here: asked a screenful at a time, each player once
export async function askKnown(ids: number[]) {
	const need = [...new Set(ids)].filter((id) => id > 0 && !owner.known.has(id)).slice(0, 1000);
	if (!need.length) return;
	for (const id of need) owner.known.set(id, false);
	try {
		const r = await fetch('/fantasy/known', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ids: need }) });
		if (!r.ok) return;
		for (const id of (await r.json()).ids as number[]) owner.known.set(id, true);
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
	const put = (v: [boolean, boolean]) => { if (v[0] || v[1]) owner.marks.set(id, v); else owner.marks.delete(id); };
	put(now);
	const res = await post<{ ok: boolean; error?: string }>('/fantasy/mark', { player: id, mine: now[0], target: now[1] });
	if (res?.ok) return '';
	// unless it has been changed again since
	if ((owner.marks.get(id) || [false, false]).join() === now.join()) put(was);
	return `${res?.error || "Couldn't save that just now."} The box has been put back.`;
}
export const lockTransfers = (body: { undo: boolean; season: number | string; event: number; transfers?: unknown[] }) =>
	post<{ ok: boolean; error?: string; locked_at?: string }>('/fantasy/lock', body);
