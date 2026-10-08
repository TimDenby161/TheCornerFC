import { shortDate } from '#lib/club.ts';
import { CONFEDS, nationTier, type NationsDoc } from '#lib/nation.ts';
import type { PlayerFacets } from '#lib/playerFilters.ts';
import { keptAsk, keptDoc } from '#lib/server/database.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';

const SORTS = ['current', 'change'] as const;

// The national team ranking: the club Elo run over every men's international since 1872
export async function load({ fetch, url, locals, setHeaders }) {
	const [d, facets] = await Promise.all([keptDoc<NationsDoc>(fetch, 'nations', 300_000), keptAsk<PlayerFacets>(fetch, 'site_player_facets', {}, 300_000)]);
	const asked = url.searchParams.get('sort') as (typeof SORTS)[number];
	const sort = SORTS.includes(asked) ? asked : 'current';
	const confed = CONFEDS.includes(url.searchParams.get('c') || '') ? url.searchParams.get('c')! : 'all';
	const nations = d.nations.map((n) => ({ ...n, change: n.year_ago == null ? null : n.current - n.year_ago }));
	const worldRank = new Map([...nations].sort((a, b) => b.current - a.current).map((n, i) => [n.name, i + 1]));
	// the nationality page's name for a nation (the feed's), if the site has players from it
	const nats = new Set(facets.nats);
	const pageName = (n: { name: string }) => [n.name, ...(d.aliases?.[n.name] || [])].find((x) => nats.has(x)) ?? null;
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	return {
		sort, confed, confeds: CONFEDS, tabHead: { title: 'Nations', ...TAB_INFO.nations },
		matches: d.matches, latest: `${shortDate(d.latest_match)} ${d.latest_match.slice(0, 4)}`, fromApi: d.from_api ?? 0,
		rows: nations.filter((n) => confed === 'all' || n.confed === confed)
			.sort((a, b) => (b[sort] ?? -Infinity) - (a[sort] ?? -Infinity) || b.current - a.current)
			.map((n) => ({
				name: n.name, page: pageName(n), flag: /^[a-z]{2}(-[a-z]{3})?$/.test(n.flag) ? n.flag : null, confed: n.confed,
				current: Math.round(n.current), tier: nationTier(d, n.current), change: n.change == null ? null : Math.round(n.change),
				tip: `World #${worldRank.get(n.name)} · Last 12 months: ${n.w}W ${n.d}D ${n.l}L · Last match: ${n.last.gf}–${n.last.ga} v ${n.last.opp} (${n.last.comp}, ${shortDate(n.last.date)} ${n.last.date.slice(0, 4)}) · ${n.played} internationals rated`
			}))
	};
}
