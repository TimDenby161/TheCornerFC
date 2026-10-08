import { formationUse, longDate, shortDate, shortName, wdl, type ClubMatch } from '#lib/club.ts';
import { FLAG_CODES } from '#lib/names.ts';
import { ROLE_ORDER, spellLabel } from '#lib/nation.ts';
import { nationBase } from '#lib/server/nation.ts';

// The current coach, the formations used under him, then match by match with each starting XI
export async function load({ fetch, params, locals }) {
	const { team, spell, known } = await nationBase(fetch, params.name, locals.token);
	if (!team || !spell) return { any: false as const };
	const list = spell.rows, first = longDate(list[0].date);
	const knownF = list.filter((m) => m.formation);
	const thisYear = String(new Date().getFullYear());
	const when = (d: string) => (d.slice(0, 4) === thisYear ? shortDate(d) : longDate(d));
	const order = (r: string | null) => ROLE_ORDER.indexOf(r || '') + 1 || 99;
	return {
		any: true as const, label: spellLabel(spell), thisYear,
		coach: spell.coach ? {
			name: spell.coach, when: spell.since ? `Since ${longDate(spell.since)}` : `First match ${first}${spell.full ? '' : ' (or before)'}`,
			record: `${list.length} matches${spell.since && !spell.full ? ` from ${first}` : ''} · ${wdl(list)}`
		} : null,
		used: formationUse(knownF as unknown as ClubMatch[]), missing: list.length - knownF.length,
		note: `International matches API-Football has line-ups for${spell.full ? '' : `, from ${first}${spell.since ? '' : ' (his spell may have started earlier)'}`}. Formations as on each team sheet.`,
		matches: list.slice().reverse().map((m) => ({
			key: m.i, date: when(m.date), opp: m.opp, flag: FLAG_CODES[m.opp] ?? null, venue: m.venue, venueName: ({ H: 'Home', A: 'Away', N: 'Neutral ground' } as Record<string, string>)[m.venue] || '',
			tournament: m.tournament || '', gf: m.gf, ga: m.ga, formation: m.formation,
			xi: m.xi.slice().sort((a, b) => order(a.role) - order(b.role)).map((a) => {
				const name = team.players[a.player] || 'Unknown';
				return { id: a.player, role: a.role || '–', name: shortName(name), link: known.has(a.player), goals: a.goals || 0 };
			})
		}))
	};
}
