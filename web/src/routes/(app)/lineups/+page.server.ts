import { filterMenu } from '#lib/clubTable.ts';
import { clubExtremes, historySummary, liveRows, liveSummary, LR_CLUB_MIN, LR_LINES, LR_PAGE, of11, shareText, type Group, type HistoryDoc, type LiveDoc, type Summary } from '#lib/lineupRecord.ts';
import { compCountries, filterComps, knownMatchFilter } from '#lib/matchday.ts';
import { pageHref } from '#lib/menu.ts';
import { keptAsk, keptDoc } from '#lib/server/database.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';
import { compLabel, type Site } from '#lib/site.ts';

const TITLES = {
	all: 'All competitions', country: (c: string) => `All ${c} line-ups`, region: (r: string) => `All line-ups in ${r}`,
	euro: 'Champions League, Europa League and Conference League line-ups', cup: (name: string) => `${name} line-ups`, intl: 'National team line-ups'
};
const RANGES = [['7', '7 days'], ['30', '30 days'], ['90', '90 days'], ['365', '12 months'], ['all', 'All time']];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export async function load({ fetch, url, locals, parent, setHeaders }) {
	const { tz } = await parent();
	const site = await keptDoc<Site>(fetch, 'site');
	const q = url.searchParams;
	const live = q.get('src') !== 'history';
	const range = RANGES.some(([k]) => k === q.get('r')) ? q.get('r')! : 'all';
	const days = range === 'all' ? null : Number(range);
	const shown = Math.min(1000, Math.max(LR_PAGE, Number(q.get('n')) || LR_PAGE));
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	const base = { live, range, ranges: RANGES, shown, tabHead: { title: 'Line-up record', ...TAB_INFO.lineups } };

	// the menu over the competitions this record has, with the line-ups each has in the range
	let s: Summary, names: { teams: Record<string, string>; players: Record<string, string> }, menuIds: number[], counts: Map<number, number>, filter: string;
	let versions: { name?: string; registered?: string }[] = [], intlTeams = new Set<number>();
	if (live) {
		const d = await keptDoc<LiveDoc>(fetch, 'lineups', 300_000).catch(() => null);
		if (!d || d.available === false) return { ...base, filter: 'all', menu: null, state: 'waiting' as const };
		const rows = liveRows(d);
		menuIds = [...new Set(rows.map((r) => r.league))];
		const countries = compCountries(site, menuIds), intl = menuIds.filter((id) => site.competitions[id]?.type === 'International');
		filter = knownMatchFilter(q.get('c'), site, countries) ? q.get('c')! : 'all';
		const since = days ? Date.now() - days * 864e5 : -Infinity;
		counts = new Map();
		for (const r of rows) if (r.time >= since) counts.set(r.league, (counts.get(r.league) || 0) + 1);
		s = liveSummary(d, rows, days, filterComps(filter, countries, intl), tz, shown);
		names = { teams: d.teams || {}, players: d.players || {} };
		versions = d.versions;
		// a national team: one with a line-up in a national team competition
		intlTeams = new Set(rows.filter((r) => site.competitions[r.league]?.type === 'International').map((r) => r.team));
	} else {
		// the history is added up in the database, for the range and competitions chosen
		const all = compCountries(site, Object.keys(site.competitions).map(Number));
		const asked = knownMatchFilter(q.get('c'), site, all) ? q.get('c')! : 'all';
		const ids = filterComps(asked, all, []);
		const d = await keptAsk<HistoryDoc>(fetch, 'site_lineup_history', { p_limit: shown, ...(days ? { p_days: days } : {}), ...(ids ? { p_leagues: ids } : {}) }, 300_000).catch(() => null);
		if (!d || d.available === false) return { ...base, filter: 'all', menu: null, state: 'waiting' as const };
		menuIds = d.leagues; filter = asked;
		counts = new Map(Object.entries(d.scope).map(([id, n]) => [Number(id), n]));
		s = historySummary(d);
		names = { teams: d.teams || {}, players: d.players || {} };
	}
	const countries = compCountries(site, menuIds), intl = live ? menuIds.filter((id) => site.competitions[id]?.type === 'International') : [];
	const total = [...counts.values()].reduce((a, n) => a + n, 0);
	const menu = filterMenu(site, countries, filter, (value) => { const ids = filterComps(value, countries, intl); return ids ? ids.reduce((a, id) => a + (counts.get(id) || 0), 0) : total; }, TITLES, intl);
	if (!s.n) return { ...base, filter, menu, state: !live && !s.any ? 'waiting' as const : s.any ? 'none' as const : 'empty' as const };

	const team = (id: number) => site.teams[id] || names.teams[id] || `Team ${id}`;
	const player = (id: number) => names.players[id] || `Player ${id}`;
	const teamHref = (id: number) => (intlTeams.has(id) ? pageHref('nation', site.nation_pages?.[id] || team(id)) : `/club/${id}`);
	const years = s.first!.slice(0, 4) !== s.last!.slice(0, 4);
	const dateOf = (day: string) => `${Number(day.slice(8))} ${MONTHS[Number(day.slice(5, 7)) - 1]}${years ? ` ${day.slice(0, 4)}` : ''}`;
	const top = Math.max(...s.counts!), lo = Math.min(6, s.counts!.findIndex((c) => c > 0));
	const clubRow = ([id, n, correct, perfect]: Group) => ({ id, name: team(id), href: teamHref(id), n, named: of11(correct / n), perfect: shareText(perfect, n) });
	const extremes = clubExtremes(s.clubs!);
	const tally = (list: [number, number, number][]) => [...list].sort((a, b) => b[2] - a[2] || player(a[0]).localeCompare(player(b[0]))).slice(0, 15).map(([p, t, n]) => ({ id: p, name: player(p), team: team(t), n }));
	return {
		...base, filter, menu, state: 'ok' as const, clubMin: LR_CLUB_MIN, step: s.step!,
		cards: [
			['Line-ups', s.n.toLocaleString('en-GB'), `From ${s.matches.toLocaleString('en-GB')} matches, ${dateOf(s.first!)} to ${dateOf(s.last!)}`],
			['Named correctly', of11(s.correct / s.n), `${s.correct.toLocaleString('en-GB')} of ${(11 * s.n).toLocaleString('en-GB')} starters (${shareText(s.correct, 11 * s.n)})`],
			['Perfect XIs', s.perfect.toLocaleString('en-GB'), `All 11 right in ${shareText(s.perfect, s.n)} of line-ups`],
			['Right position', shareText(s.rolesRight, s.rolesKnown), 'Correct starters also put where they played']
		],
		sample: s.n < 200 ? `Very early: ${s.n.toLocaleString('en-GB')} line-ups is too few to judge the model, so these figures will move a lot.`
			: s.n < 1000 ? `Still a small sample (${s.n.toLocaleString('en-GB')} line-ups): small differences are likely to be luck.` : '',
		// how many of the 11 each line-up got
		spread: Array.from({ length: 11 - lo + 1 }, (_, i) => 11 - i).map((k) => ({ label: `${k} of 11`, share: top ? Math.round((100 * s.counts![k]) / top) : 0, text: `${s.counts![k]} · ${shareText(s.counts![k], s.n)}`, tip: `${k} of 11 right: ${s.counts![k]} line-ups` })),
		trend: s.trend!.map(([day, n, correct, perfect]) => {
			const d = new Date(`${day}T00:00:00Z`);
			const label = s.step === 'month' ? `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
				: `${s.step === 'week' ? 'w/c ' : ''}${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}${years ? ` ${String(d.getUTCFullYear()).slice(2)}` : ''}`;
			return { label, share: Math.round((100 * (correct / n)) / 11), value: (correct / n).toFixed(1), n, tip: `${label}: ${of11(correct / n)} from ${n} line-ups, ${perfect} perfect` };
		}),
		lines: LR_LINES.map((name, i) => { const starters = s.lines![2 * i], hit = s.lines![2 * i + 1]; return { name, starters, hit, rate: shareText(hit, starters), bar: Math.round((starters ? hit / starters : 0) * 60) }; }),
		timing: (s.timing || []).map(([label, n, correct, perfect]) => ({ label, n, named: n ? of11(correct / n) : '–', perfect: shareText(perfect, n) })),
		comps: [...s.comps!].sort((a, b) => b[1] - a[1] || b[2] / b[1] - a[2] / a[1]).map(([id, n, correct, perfect, right, known]) =>
			({ id, name: compLabel(site, id), on: String(id) === filter, n, named: of11(correct / n), perfect: shareText(perfect, n), position: shareText(right ?? 0, known) })),
		clubs: { easiest: extremes?.easiest.map(clubRow) ?? null, hardest: extremes?.hardest.map(clubRow) ?? null, all: [...s.clubs!].sort((a, b) => team(a[0]).localeCompare(team(b[0]))).map(clubRow) },
		missed: tally(s.missed!), wrong: tally(s.wrong!), missedTotal: s.missedTotal!,
		versions: (s.versions || []).map(([i, n, correct, perfect]) => {
			const v = versions[i] || {};
			const reg = v.registered ? new Date(v.registered) : null;
			return { label: `v${i + 1}`, name: v.name || 'unknown', from: reg ? `${reg.getUTCDate()} ${MONTHS[reg.getUTCMonth()]} ${reg.getUTCFullYear()}` : '', n, named: of11(correct / n), perfect: shareText(perfect, n) };
		}),
		rows: s.rows!.map((r) => ({ date: dateOf(r.day), team: team(r.team), href: teamHref(r.team), home: r.home, opponent: team(r.opponent), comp: compLabel(site, r.league), correct: r.correct, missed: r.missed.map(player).join(', ') })),
		// more to list, unless the database has already sent all it will (1,000 at most)
		more: s.n > s.rows!.length && s.rows!.length >= shown && shown < 1000 ? { left: s.n - s.rows!.length, n: shown + LR_PAGE } : null,
		excluded: s.excluded || 0
	};
}
