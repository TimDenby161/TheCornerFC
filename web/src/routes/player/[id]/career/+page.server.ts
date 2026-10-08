import { playerBase } from '#lib/server/player.ts';
import { seasonShort } from '#lib/club.ts';
import { GROUP_SINGLE } from '#lib/playerFilters.ts';
import { positionShares, seasonGroup, spells, type ChartPoint, type Spell } from '#lib/player.ts';

// Rank by season with his clubs, and the clubs his current rank is built on
export async function load({ fetch, params }) {
	const { site, p, doc, club } = await playerBase(fetch, params.id);
	const seasons = site.player_seasons;
	const spellView = (sp: Spell[]) => sp.map((x) => ({ team: x.team, name: club(x.team), clubRank: x.club_rank, minutes: x.minutes || 0, goals: x.goals ?? 0, assists: x.assists ?? 0 }));
	const rows = seasons.flatMap((y, k) => {
		const v = p.seasons?.[k];
		if (v == null) return [];
		const pos = doc?.positions?.[String(y)];
		const group = seasonGroup(pos);
		return [{
			y, label: seasonShort(y), age: p.age != null ? p.age - (seasons[0] - y) : null, rank: v, est: !!p.estimated?.includes(k),
			spells: spellView(spells(doc, String(y))), shares: pos ? positionShares(pos) : [], ratedAs: pos && group ? GROUP_SINGLE[group] : null
		}];
	});
	// the chart's points, oldest first
	const points: ChartPoint[] = rows.slice().reverse().map((r) => ({ label: r.label, season: `${r.y}/${String(r.y + 1).slice(2)}`, v: r.rank, est: r.est }));
	return { rows, points: points.length >= 2 ? points : [], now: spellView(spells(doc, 'now')) };
}
