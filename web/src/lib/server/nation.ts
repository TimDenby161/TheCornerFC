import { error } from '@sveltejs/kit';
import { nationFor, nationSpell, nationTier, readTeam, type NationDoc, type NationsDoc } from '#lib/nation.ts';
import { playerRows, type Player, type PlayersAnswer } from '#lib/players.ts';
import type { Site } from '#lib/site.ts';
import type { Injuries } from './club.ts';
import { askAs, keptDoc, keptDocOrNull } from './database.ts';

// every player that fits, 2,000 a request (the most site_players sends)
async function everyPlayer(fetch: typeof globalThis.fetch, site: Site, token: string | undefined, params: Record<string, unknown>) {
	const out: Player[] = [];
	let paywall = false;
	for (let at = 0, total = 1; at < total; ) {
		const d = await askAs<PlayersAnswer>(fetch, token, 'site_players', { ...params, p_limit: 2000, p_offset: at });
		paywall ||= !!d.paywall;
		if (!d.rows.length) break;
		out.push(...playerRows(site, d.rows));
		at += d.rows.length; total = d.total;
	}
	return { players: out, paywall };
}

// What every part of a nation's page starts from: the nationality's ranked club players (as this
// visitor may see them), the nation's place in the ranking, and, where the feed has its
// internationals, the national team's own file. A name with neither players nor a ranking has no page.
export async function nationBase(fetch: typeof globalThis.fetch, name: string, token?: string) {
	if (!name || name.length > 60) error(404, 'Not found');
	const [site, ranking] = await Promise.all([keptDoc<Site>(fetch, 'site'), keptDoc<NationsDoc>(fetch, 'nations', 300_000).catch(() => null)]);
	const { players, paywall } = await everyPlayer(fetch, site, token, { p_nats: [name] });
	const byOrd = (a: Player, b: Player) => (a.ord ?? 1e9) - (b.ord ?? 1e9) || a.name.localeCompare(b.name);
	const list = players.filter((p) => p.nationality === name).sort(byOrd);
	const n = ranking ? nationFor(ranking, name) ?? null : null;
	if (!list.length && !n) error(404, 'Not found');
	const doc = n?.team_id ? await keptDocOrNull<NationDoc>(fetch, `nations/${n.team_id}`, 300_000).catch(() => null) : null;
	const team = doc?.matches?.length ? readTeam(doc) : null;
	// the squad's own rows in the Players list, for their ranks, clubs and links to their pages
	const squadIds = team ? Object.keys(team.players).map(Number).filter((id) => !list.some((p) => p.id === id)) : [];
	const squad = squadIds.length ? (await everyPlayer(fetch, site, token, { p_ids: squadIds })).players : [];
	const known = new Map([...list, ...squad].map((p) => [p.id, p]));
	return {
		site, name, list, team, known, paywall: paywall || list.some((p) => p.locked), spell: team ? nationSpell(team) : null,
		rating: n && ranking ? {
			current: Math.round(n.current), tier: nationTier(ranking, n.current), rank: ranking.nations.filter((x) => x.current > n.current).length + 1, of: ranking.nations.length,
			change: n.year_ago == null ? null : Math.round(n.current - n.year_ago)
		} : null
	};
}
// players their club's latest injury list has missing through injury (the list's "injured" flag)
export async function injuredPlayers(fetch: typeof globalThis.fetch): Promise<Set<number>> {
	const d = await keptDoc<Injuries & { fields?: string[] }>(fetch, 'injuries', 300_000).catch(() => null);
	const out = new Set<number>(), fields = d?.fields || [];
	const pi = fields.indexOf('player'), ii = fields.indexOf('injured');
	for (const t of Object.values(d?.teams || {})) for (const r of (t.players || []) as unknown as (number | string | null)[][]) if (r[ii]) out.add(r[pi] as number);
	return out;
}
