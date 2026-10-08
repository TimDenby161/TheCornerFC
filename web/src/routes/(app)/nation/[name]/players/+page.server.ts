import { longDate, shortDate, shortName } from '#lib/club.ts';
import { NAT_PLAYER_SORTS, nationPlayers, spellLabel } from '#lib/nation.ts';
import { nationBase } from '#lib/server/nation.ts';
import { teamName } from '#lib/site.ts';

// Everyone who has played under the current coach, with appearances, minutes, goals, assists and cards
export async function load({ fetch, params, url, locals }) {
	const { site, team, spell, known } = await nationBase(fetch, params.name, locals.token);
	if (!team || !spell) return { any: false as const };
	const asked = url.searchParams.get('sort') as (typeof NAT_PLAYER_SORTS)[number];
	const sort = NAT_PLAYER_SORTS.includes(asked) ? asked : 'minutes';
	const thisYear = String(new Date().getFullYear());
	const list = spell.rows;
	const players = nationPlayers(team, spell, (id) => known.get(id)?.position ?? null, sort);
	return {
		any: true as const, sort, matches: list.length, anyNoMins: players.some((p) => p.noMins > 0),
		heading: `${spellLabel(spell)}${spell.since ? ` (since ${longDate(spell.since)})` : ''} · ${list.length} match${list.length === 1 ? '' : 'es'}${spell.full ? '' : ` from ${longDate(list[0].date)}`}`,
		players: players.map((p) => {
			const site_ = known.get(p.id);
			return { ...p, short: shortName(p.name), link: !!site_, team: site_?.team ?? null, teamName: site_?.team ? teamName(site, site_.team) : null,
				lastText: p.last.slice(0, 4) === thisYear ? shortDate(p.last) : longDate(p.last) };
		})
	};
}
