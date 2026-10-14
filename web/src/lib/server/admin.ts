import { error } from '@sveltejs/kit';
import { siteAsk } from '#lib/server/database.ts';
import { asModelCompare, isMatchModel, type MatchModelName, type ModelCompare } from '#lib/matchModels.ts';

// The Admin area is the site administrator's only. Who that is, the database decides: its
// am_admin() and admin_doc() answer for the visitor whose own token the request carries, from a
// list of administrators set by hand (db/migrations/20261013_admin_area.sql). Being signed in is
// not enough, and nothing in the browser is asked. No key that could read the documents without
// that token is held by this site.
type Fetch = typeof fetch;

// Every address the gate covers: /admin and everything under it, pages, their data and endpoints
export const isAdminPath = (pathname: string) => pathname === '/admin' || pathname.startsWith('/admin/');

// Whether this token is an administrator's. Any failure is a "no".
export async function isAdmin(fetch: Fetch, token: string | undefined): Promise<boolean> {
	if (!token) return false;
	return (await siteAsk<unknown>(fetch, 'am_admin', {}, token).catch(() => false)) === true;
}

// What to do with a request, decided before any of its code runs: "open" for an address outside
// the Admin area, "signin" for a visitor with no session, "refuse" for one who is signed in and is
// not an administrator (or when the database can't be asked), "admin" for an administrator.
export type Gate = 'open' | 'signin' | 'refuse' | 'admin';
export async function adminGate(fetch: Fetch, pathname: string, token: string | undefined): Promise<Gate> {
	if (!isAdminPath(pathname)) return 'open';
	if (!token) return 'signin';
	return (await isAdmin(fetch, token)) ? 'admin' : 'refuse';
}

// One of the administrator's documents ("bets", "model_changes"), or null where the export has
// not stored it yet. Anyone else is told the page isn't there: the database answers them
// {ok: false} whatever the page did or didn't check.
export async function adminDoc<T>(fetch: Fetch, token: string | undefined, name: string): Promise<T | null> {
	if (!token) error(404, 'Not found');
	const answer = await siteAsk<{ ok?: boolean; doc?: T | null }>(fetch, 'admin_doc', { p_name: name }, token);
	if (answer?.ok !== true) error(404, 'Not found');
	return answer.doc ?? null;
}

// Which match model is live and the last switches (db/migrations/20261014_challenger_model.sql), for
// an administrator; null for anyone else, or before that migration is applied.
export type MatchModel = { live: MatchModelName; switches: { at: string; live: MatchModelName }[] };
type MatchModelAnswer = { ok?: boolean; live?: unknown; switches?: { at: string; live: MatchModelName }[] };
const asMatchModel = (answer: MatchModelAnswer | null): MatchModel | null =>
	answer?.ok === true && isMatchModel(answer.live) ? { live: answer.live, switches: answer.switches ?? [] } : null;
export async function matchModel(fetch: Fetch, token: string | undefined): Promise<MatchModel | null> {
	if (!token) return null;
	return asMatchModel(await siteAsk<MatchModelAnswer>(fetch, 'admin_match_model', {}, token).catch(() => null));
}
// Switch the live model; the database checks the caller is an administrator. From the next run.
export async function switchMatchModel(fetch: Fetch, token: string | undefined, live: MatchModelName): Promise<MatchModel | null> {
	if (!token) return null;
	return asMatchModel(await siteAsk<MatchModelAnswer>(fetch, 'admin_set_match_model', { p_live: live }, token).catch(() => null));
}
// Both match models compared on the same finished and upcoming matches, for an administrator; null
// for anyone else, or before db/migrations/20261014_match_model_compare.sql is applied.
export async function matchModelCompare(fetch: Fetch, token: string | undefined): Promise<ModelCompare | null> {
	if (!token) return null;
	return asModelCompare(await siteAsk<Partial<ModelCompare> & { ok?: boolean }>(fetch, 'admin_match_model_compare', {}, token).catch(() => null));
}
