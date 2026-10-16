// The sitemap search engines read (/sitemap.xml, named in robots.txt): the main pages, every
// league (at its table, where /league/<id> leads) and every club. Players and nations are reached
// through the links on those pages, so building it needs only the club list the site already
// keeps (task T-031).
export const MAIN_PAGES = ['/', '/clubs', '/players', '/matches', '/leagues', '/nations', '/stats', '/lineups', '/methodology', '/privacy', '/terms'];

export function sitemap(origin: string, clubs: { team: number; league: number }[]): string {
	const leagues = [...new Set(clubs.map((c) => c.league).filter((l) => l != null))].sort((a, b) => a - b);
	const teams = [...new Set(clubs.map((c) => c.team))].sort((a, b) => a - b);
	const paths = [...MAIN_PAGES, ...leagues.map((l) => `/league/${l}/table`), ...teams.map((t) => `/club/${t}`)];
	return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
		+ paths.map((p) => `<url><loc>${origin}${p}</loc></url>`).join('\n') + '\n</urlset>\n';
}
