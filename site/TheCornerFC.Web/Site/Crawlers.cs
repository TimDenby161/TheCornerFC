using System.Text;

namespace TheCornerFC.Web.Site;

// What search engines are told (web/src/routes/robots.txt and sitemap.xml, web/src/lib/sitemap.ts).
public static class Crawlers
{
    // Search engines are let in at the live site's own address only. Anywhere else (staging, the
    // host's own address) is kept out. The account, the owner's fantasy pages and the server's own
    // addresses are never for them.
    public static string Robots(SiteEnvironment env, string host)
    {
        string[] lines = env.IsProduction && host == env.Host
            ? ["User-agent: *", "Disallow: /account", "Disallow: /admin", "Disallow: /fantasy/", "Disallow: /fpl",
               "Disallow: /my-fpl-team", "Disallow: /efl-fantasy", "Disallow: /stripe/", "Disallow: /players/rows",
               "Disallow: /players/options", "Disallow: /players/seasons", "", $"Sitemap: https://{env.Host}/sitemap.xml", ""]
            : ["User-agent: *", "Disallow: /", ""];
        return string.Join('\n', lines);
    }

    // The main pages, every league (at its table, where /league/<id> leads) and every club.
    // Players and nations are reached through the links on those pages.
    public static readonly IReadOnlyList<string> MainPages =
        ["/", "/clubs", "/players", "/matches", "/leagues", "/nations", "/stats", "/lineups", "/model", "/methodology", "/privacy", "/terms"];

    public static string Sitemap(string origin, IEnumerable<(int Team, int? League)> clubs)
    {
        var list = clubs.ToList();
        var leagues = list.Where(c => c.League is not null).Select(c => c.League!.Value).Distinct().Order();
        var teams = list.Select(c => c.Team).Distinct().Order();
        var paths = MainPages.Concat(leagues.Select(l => $"/league/{l}/table")).Concat(teams.Select(t => $"/club/{t}"));
        var xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n");
        xml.AppendJoin('\n', paths.Select(p => $"<url><loc>{origin}{p}</loc></url>"));
        return xml.Append("\n</urlset>\n").ToString();
    }
}
