// The menu, in the old site's groups. A section with a `path` is built here; one without still
// lives on the old site and its link goes there until it is rebuilt. `tab` is the name the
// stylesheet knows the section by (body[data-tab]).
export const OLD_SITE = 'https://thecornerfc.com/';
export type Section = { tab: string; label: string; path?: string; old?: string };
export const MENU: { label: string; sections: Section[] }[] = [
	{ label: 'Ratings', sections: [
		{ tab: 'table', label: 'Clubs', path: '/clubs' },
		{ tab: 'table', label: 'Players', path: '/players' },
		{ tab: 'leagues', label: 'Leagues', path: '/leagues' },
		{ tab: 'nations', label: 'Nations', path: '/nations' }
	] },
	{ label: 'Predictions', sections: [
		{ tab: 'matches', label: 'Matches', path: '/matches' },
		{ tab: 'stats', label: 'Stats', path: '/stats' },
		{ tab: 'lineups', label: 'Line-up record', path: '/lineups' }
	] },
	{ label: 'Against the market', sections: [
		{ tab: 'tips', label: 'Model vs Market', old: '#/model-vs-market' },
		{ tab: 'bets', label: 'Paper Simulation', old: '#/simulation' }
	] }
];
export const sectionHref = (s: Section) => s.path ?? OLD_SITE + (s.old ?? '');
export function tabFor(pathname: string): string {
	for (const g of MENU) for (const s of g.sections) if (s.path && (pathname === s.path || pathname.startsWith(s.path + '/'))) return s.tab;
	// a club's, player's, competition's or country's page (the stylesheet knows every such page as "club")
	if (/^\/(club|player|league|country|nation)\//.test(pathname)) return 'club';
	return 'home';
}

// A link to a club's, competition's or country's page. Until that kind of page is rebuilt here,
// the link goes to the old site's.
const BUILT = new Set<string>(['club', 'player', 'league', 'country', 'nation']);
export const pageHref = (kind: 'club' | 'league' | 'country' | 'player' | 'nation', id: string | number) =>
	BUILT.has(kind) ? `/${kind}/${encodeURIComponent(id)}` : `${OLD_SITE}#/${kind}/${encodeURIComponent(id)}`;
export const methodologyHref = (section: string) => `${OLD_SITE}methodology.html#${section}`;
