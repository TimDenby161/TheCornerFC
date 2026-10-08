import { clubBase } from '#lib/server/club.ts';
import { clubSeasons, formationUse, longDate, wdl } from '#lib/club.ts';

// The manager, then the formations used since he took over and this season (league line-ups only:
// cup matches outside the player-data leagues have no formation)
export async function load({ fetch, params }) {
	const { rows, doc } = await clubBase(fetch, params.id);
	if (!rows.some((m) => m.formation)) return { any: false as const };
	const coach = doc?.coach?.name ? doc.coach : null;
	const { seasonOf, label } = clubSeasons(rows);
	const season = seasonOf(rows[rows.length - 1]);
	const sinceRows = coach?.since ? rows.filter((m) => m.date >= coach.since!) : [];
	const seasonRows = rows.filter((m) => seasonOf(m) === season);
	const section = (title: string, list: typeof rows) => {
		const known = list.filter((m) => m.formation);
		return { title, used: formationUse(known), missing: list.length - known.length };
	};
	// the same matches either way (he took over before this season's first match): one list
	const same = sinceRows.length === seasonRows.length && sinceRows[0] === seasonRows[0];
	return {
		any: true as const,
		coach: coach ? { name: coach.name!, since: coach.since ? longDate(coach.since) : null, matches: sinceRows.length, record: wdl(sinceRows) } : null,
		sections: [
			section(`${same && coach ? `Since ${coach.name} took over · ` : ''}This season (${label(season)})`, seasonRows),
			...(coach?.since && !same ? [section(`Since ${coach.name} took over`, sinceRows)] : [])
		],
		thisYear: String(new Date().getFullYear())
	};
}
