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
		{ tab: 'tips', label: 'Model vs Market', path: '/model-vs-market' },
		{ tab: 'bets', label: 'Paper Simulation', path: '/simulation' }
	] }
];
// The fantasy pages are the site owner's: in the menu for the owner only (the pages themselves
// show anyone else a line saying so).
export const OWNER_MENU = { label: 'Fantasy', sections: [
	{ tab: 'fpl', label: 'FPL', path: '/fpl' },
	{ tab: 'myteam', label: 'My FPL team', path: '/my-fpl-team' },
	{ tab: 'efl', label: 'EFL Fantasy', path: '/efl-fantasy' }
] as Section[] };
export const sectionHref = (s: Section) => s.path ?? OLD_SITE + (s.old ?? '');
export function tabFor(pathname: string): string {
	for (const g of [...MENU, OWNER_MENU]) for (const s of g.sections) if (s.path && (pathname === s.path || pathname.startsWith(s.path + '/'))) return s.tab;
	// a club's, player's, competition's or country's page (the stylesheet knows every such page as "club")
	if (/^\/(club|player|league|country|nation)\//.test(pathname)) return 'club';
	return 'home';
}

// A link to a club's, competition's or country's page. Until that kind of page is rebuilt here,
// the link goes to the old site's.
const BUILT = new Set<string>(['club', 'player', 'league', 'country', 'nation']);
export const pageHref = (kind: 'club' | 'league' | 'country' | 'player' | 'nation', id: string | number) =>
	BUILT.has(kind) ? `/${kind}/${encodeURIComponent(id)}` : `${OLD_SITE}#/${kind}/${encodeURIComponent(id)}`;
export const methodologyHref = (section: string) => `/methodology#${section}`;

// The address on this site for one of the old site's (its part after the #), or null where the
// part after the # isn't one. The pages kept their names and their choices' names; the one
// difference is that a club's, player's or nation's first tab could be named in the address
// there ("/overview") and has none here.
const OLD_PAGES = /^#\/(clubs|players|leagues|nations|matches|stats|lineups|model-vs-market|simulation|fpl|my-fpl-team|efl-fantasy|(?:club|player|league|country|nation)\/[^?#]+)(\?[^#]*)?$/;
export function oldAddress(hash: string): string | null {
	const m = OLD_PAGES.exec(hash);
	if (!m) return null;
	const path = m[1].replace(/^((?:club|player|nation)\/[^/]+)\/overview$/, '$1');
	return `/${path}${m[2] ?? ''}`;
}

// The old site's files by their own names (thecornerfc.com/terms.html, /index.html): where each is
// here, or null for any other path.
export function oldFile(pathname: string): string | null {
	const m = /^\/(index|methodology|terms|privacy)\.html$/.exec(pathname);
	return m ? (m[1] === 'index' ? '/' : `/${m[1]}`) : null;
}
