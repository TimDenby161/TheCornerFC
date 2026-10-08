import { clubBase, clubPlayers } from '#lib/server/club.ts';
import { keptDocOrNull } from '#lib/server/database.ts';
import { leagueZones, result, shortDate, shortName } from '#lib/club.ts';
import { countryDisplay } from '#lib/clubTable.ts';
import { tiers } from '#lib/rankings.ts';
import { compLabel, leagueShort, teamName } from '#lib/site.ts';

type LeagueFile = { table_fields: string[]; table: (string | number | null)[][]; teams: Record<string, string> };
type TableRow = { group: string | null; rank: number; team: number; played: number | null; gd: number | null; points: number | null; form: string | null; description: string | null };

export async function load({ fetch, params, setHeaders, locals }) {
	const { id, site, all, rank: r, doc, rows, opponent, name } = await clubBase(fetch, params.id);
	const comp = r ? site.competitions[r.league] : null;
	// its league's file, for the table position
	// the club's five best players by Ability: the export's order is by current rank, and a player
	// whose rank is hidden (the paywall) keeps his place in it
	const best = (await clubPlayers(fetch, site, id, locals.token).catch(() => ({ list: [] }))).list
		.filter((p) => p.rank != null || p.locked).sort((a, b) => (a.ord ?? 1e9) - (b.ord ?? 1e9) || a.name.localeCompare(b.name)).slice(0, 5)
		.map((p) => ({ id: p.id, name: p.name, short: shortName(p.name), position: p.position, rank: p.rank, goals: p.season?.goals ?? null, assists: p.season?.assists ?? null }));
	const lg = r?.in_league ? await keptDocOrNull<LeagueFile>(fetch, `leagues/${r.league}`, 300_000).catch(() => null) : null;
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });

	const place = (key: 'current' | 'lt', v: number) => all.filter((x) => x[key] > v).length + 1;

	// The club's slice of its league table: it and the two clubs either side (five rows, shifted
	// at the top and bottom), in the club's own group
	let table = null;
	if (lg && r) {
		const tableRows = lg.table.map((row) => Object.fromEntries(lg.table_fields.map((f, i) => [f, row[i]])) as unknown as TableRow);
		const me = tableRows.find((t) => t.team === id);
		if (me) {
			const zones = leagueZones(tableRows);
			const group = tableRows.filter((t) => t.group === me.group);
			const i = group.indexOf(me), start = Math.max(0, Math.min(i - 2, group.length - 5));
			const league = leagueShort(site, r.league) || compLabel(site, r.league);
			table = {
				league: r.league,
				title: me.group && me.group !== site.competitions[r.league]?.name ? `${league} · ${me.group}` : league,
				rows: group.slice(start, start + 5).map((t) => ({
					team: t.team, me: t === me, name: lg.teams[t.team] || teamName(site, t.team), rank: t.rank,
					played: t.played, gd: t.gd, points: t.points, form: t.form, zone: (t.description && zones.get(t.description)) || ''
				}))
			};
		}
	}

	// Style: the lean between attack and defence. The ends of the meter are the most one-sided
	// clubs in the world
	let style = null;
	if (r && r.attack != null && r.defence != null) {
		const max = Math.max(1, ...all.filter((x) => x.attack != null && x.defence != null).map((x) => Math.abs(x.attack - x.defence) / 2));
		const lean = (r.attack - r.defence) / 2, k = Math.round(lean);
		style = { x: 50 + 50 * Math.max(-1, Math.min(1, lean / max)), text: k === 0 ? 'Balanced' : `${k > 0 ? 'Attacking' : 'Defensive'} +${Math.abs(k)}` };
	}

	return {
		id, name,
		league: comp && r ? { id: r.league, name: leagueShort(site, r.league) || compLabel(site, r.league), countryKey: comp.country, country: countryDisplay(comp.country) } : null,
		coach: doc?.coach?.name ?? null,
		rating: r ? {
			place: place('current', r.current),
			form: r.form == null ? null : Math.round(r.form),
			lt: Math.round(r.lt), ltTier: tiers(all, 'lt')(r.lt),
			current: Math.round(r.current), currentTier: tiers(all, 'current')(r.current)
		} : null,
		// recent form: results in all competitions, newest first
		form: rows.slice(-40).reverse().map((m) => ({
			c: result(m),
			title: `${shortDate(m.date)} · ${m.gf}–${m.ga} ${m.home ? 'v' : '@'} ${opponent(m.opponent)} · ${compLabel(site, m.league)}`
		})),
		table, style, best
	};
}
