import { shortName } from '#lib/club.ts';
import { overviewPitch } from '#lib/nation.ts';
import { nationBase } from '#lib/server/nation.ts';
import { teamName } from '#lib/site.ts';

const LIMIT = 100;

// The best in each position, where they play, and every ranked player of the nationality
export async function load({ fetch, params, url, locals }) {
	const { site, list, team, known, paywall } = await nationBase(fetch, params.name, locals.token);
	const pitch = list.length ? overviewPitch(list, team) : null;
	const showAll = url.searchParams.get('all') === '1';
	return {
		paywall, total: list.length, showAll,
		pitch: !pitch ? null : {
			formation: pitch.formation, coach: pitch.coach, hasShape: pitch.hasShape,
			boxes: pitch.boxes.map((b) => ({
				label: b.label, row: String(b.row), col: b.col,
				players: b.players.map(({ p, unpicked }) => ({
					id: p.id, name: shortName(p.name), rank: p.rank == null ? null : Math.round(p.rank), unpicked, link: known.has(p.id),
					tip: `${p.name}${p.team ? ` · ${teamName(site, p.team)}` : ''}${unpicked ? ` · not picked by ${pitch.coach || 'the current coach'}` : ''}`
				}))
			}))
		},
		players: (showAll ? list : list.slice(0, LIMIT)).map((p) => ({
			id: p.id, name: p.name, position: p.position || '', team: p.team, teamName: p.team ? teamName(site, p.team) : null, age: p.age, rank: p.rank
		}))
	};
}
