import { TAB_INFO } from '#lib/tabInfo.ts';
import { filterMenu } from '#lib/clubTable.ts';
import { matchRows, type MatchesAnswer } from '#lib/matches.ts';
import { addDays, compCountries, dayName, dayStart, daysWith, defaultDay, filterComps, GROUP_ORDER, isDay, knownMatchFilter, localDay, matchRounds, pickRound, roundDates, singleComp, type MatchDays } from '#lib/matchday.ts';
import { clubs, type RankingsDoc } from '#lib/rankings.ts';
import { askAs, keptAsk, keptDoc } from '#lib/server/database.ts';
import { cardView } from '#lib/server/matches.ts';
import { compLabel, type Site } from '#lib/site.ts';

const TITLES = {
	all: 'All competitions', country: (c: string) => `All ${c} matches`, region: (r: string) => `All matches in ${r}`,
	euro: 'Champions League, Europa League and Conference League matches', cup: (name: string) => `${name} matches`,
	intl: 'National team matches: World Cup, qualifiers, Nations League, friendlies and others'
};

export async function load({ fetch, url, locals, parent, setHeaders }) {
	const { tz } = await parent();
	const [site, rankings, md] = await Promise.all([
		keptDoc<Site>(fetch, 'site'), keptDoc<RankingsDoc>(fetch, 'rankings'),
		// which days and competitions have matches, on this visitor's calendar
		keptAsk<MatchDays>(fetch, 'site_match_days', { p_tz: tz }, 300_000)
	]);
	const ranks = new Map(clubs(rankings).map((c) => [c.team, c]));
	const countries = compCountries(site, md.leagues), intl = md.intl.map(([lid]) => lid);
	const q = url.searchParams;
	const filter = knownMatchFilter(q.get('c'), site, countries) ? q.get('c')! : 'all';
	const asked = isDay(q.get('d')) ? q.get('d')! : null;
	const today = localDay(Date.now(), tz);
	const menu = filterMenu(site, countries, filter, null, TITLES, intl);
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	const tabHead = { title: 'Matches', ...TAB_INFO.matches };
	const cards = (list: ReturnType<typeof matchRows>, paywall: boolean) => list.map((m) => cardView(site, ranks, m, paywall));

	// One competition: a round at a time, that round's matches by day
	const lid = singleComp(filter);
	if (lid != null) {
		const answer = await askAs<MatchesAnswer>(fetch, locals.token, 'site_matches', { p_leagues: [lid] });
		const rounds = matchRounds(matchRows(site.match_fields, answer), tz);
		const round = pickRound(rounds, asked, tz);
		if (round) {
			const i = rounds.indexOf(round);
			const days = new Map<string, typeof round.matches>();
			for (const m of round.matches) { const d = localDay(m.kickoff, tz); days.set(d, [...(days.get(d) || []), m]); }
			const dayOf = (k: number) => (rounds[k] ? localDay(rounds[k].first, tz) : null);
			return {
				mode: 'rounds' as const, filter, menu, tabHead, title: menu.name,
				day: localDay(round.first, tz),
				rounds: rounds.map((r) => ({ day: localDay(r.first, tz), label: `${r.label} · ${roundDates(r, tz)}` })),
				prev: i > 0 ? dayOf(i - 1) : null, next: i < rounds.length - 1 ? dayOf(i + 1) : null,
				// "Next": the round on now or next up
				now: localDay(pickRound(rounds, null, tz)!.first, tz),
				groups: [...days].map(([d, list]) => ({ key: `d:${d}`, name: dayName(d), cards: cards(list, !!answer.paywall) }))
			};
		}
	}

	// Otherwise: the day's matches, by competition
	const ids = filterComps(filter, countries, intl);
	const day = asked ?? defaultDay(md, today);
	const from = dayStart(day, tz), to = dayStart(addDays(day, 1), tz);
	const answer = await askAs<MatchesAnswer>(fetch, locals.token, 'site_matches', { p_from: from.toISOString(), p_to: to.toISOString() });
	const shown = matchRows(site.match_fields, answer).filter((m) => m.status !== 'PST' && (!ids || ids.includes(m.league)) && localDay(m.kickoff, tz) === day);
	const groups = new Map<number, typeof shown>();
	for (const m of shown) groups.set(m.league, [...(groups.get(m.league) || []), m]);
	const orderOf = (id: number) => { const i = GROUP_ORDER.indexOf(id); return i === -1 ? 999 : i; };
	return {
		mode: 'days' as const, filter, menu, tabHead, title: filter === 'all' ? null : menu.name,
		day, dayName: `${dayName(day)}${day.slice(0, 4) === today.slice(0, 4) ? '' : ` ${day.slice(0, 4)}`}`,
		prev: addDays(day, -1), next: addDays(day, 1), isDefault: asked == null,
		// nothing on that day: the next day that has matches in these competitions
		upcoming: shown.length ? null : (() => { const d = daysWith(md, ids).find((x) => x > day); return d ? { day: d, name: dayName(d) } : null; })(),
		groups: [...groups.keys()].sort((a, b) => orderOf(a) - orderOf(b) || compLabel(site, a).localeCompare(compLabel(site, b)))
			.map((id) => ({ key: String(id), name: compLabel(site, id), cards: cards(groups.get(id)!, !!answer.paywall) }))
	};
}
