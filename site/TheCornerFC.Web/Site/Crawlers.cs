using System.Text;

namespace TheCornerFC.Web.Site;

// What search engines are told (web/src/routes/robots.txt and sitemap.xml, web/src/lib/sitemap.ts).
public static class Crawlers
{
    // Search engines are let in at the live site's own address only. Anywhere else (staging, the
    // host's own address) is kept out. The account, the owner's fantasy pages and the server's own
    // addresses are never for them (a match card's panels, /match/<id>/..., among them: a crawler reads
    // the match's page without them), and SEO tools' crawlers are asked to stay away altogether.
    public static string Robots(SiteEnvironment env, string host)
    {
        string[] lines = env.IsProduction && host == env.Host
            ? [.. Names.SeoBots.SelectMany(bot => new[] { $"User-agent: {bot}", "Disallow: /", "" }), "User-agent: *", "Disallow: /account", "Disallow: /admin", "Disallow: /fantasy/", "Disallow: /fpl",
               "Disallow: /my-fpl-team", "Disallow: /efl-fantasy", "Disallow: /stripe/", "Disallow: /players/rows",
               "Disallow: /players/options", "Disallow: /players/seasons", "Disallow: /match/*/", "", $"Sitemap: https://{env.Host}/sitemap.xml", ""]
            : ["User-agent: *", "Disallow: /", ""];
        return string.Join('\n', lines);
    }

    // The main pages, every league (at its table, where /league/<id> leads), every club, and the
    // main competitions' matches of the last 7 days and the next 7 (SitemapMatches). Players and nations are reached
    // through the links on those pages.
    public static readonly IReadOnlyList<string> MainPages =
        ["/", "/clubs", "/players", "/matches", "/leagues", "/nations", "/stats", "/lineups", "/model", "/methodology", "/assumptions", "/privacy", "/terms"];

    public static string Sitemap(string origin, IEnumerable<(int Team, int? League)> clubs, IEnumerable<int>? matches = null)
    {
        var list = clubs.ToList();
        var leagues = list.Where(c => c.League is not null).Select(c => c.League!.Value).Distinct().Order();
        var teams = list.Select(c => c.Team).Distinct().Order();
        var paths = MainPages.Concat(leagues.Select(l => $"/league/{l}/table")).Concat(teams.Select(t => $"/club/{t}"))
            .Concat((matches ?? []).Distinct().Order().Select(m => $"/match/{m}"));
        var xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n");
        xml.AppendJoin('\n', paths.Select(p => $"<url><loc>{origin}{p}</loc></url>"));
        return xml.Append("\n</urlset>\n").ToString();
    }

    // Which days' matches the sitemap lists: from the start of the day 7 days back to the end of
    // the day 7 days ahead (UTC), whole days so the database's answer is kept for the day
    public static (string From, string To) SitemapDays(DateTimeOffset now)
    {
        var day = new DateTimeOffset(now.UtcDateTime.Date, TimeSpan.Zero);
        static string Iso(DateTimeOffset t) => t.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", System.Globalization.CultureInfo.InvariantCulture);
        return (Iso(day.AddDays(-7)), Iso(day.AddDays(8)));
    }

    // Those matches' ids: only in the competitions the site lists first (names.json's GROUP_ORDER:
    // the English leagues and cups, the European cups and the main European leagues; the owner's
    // choice, 2026-10-20), less any called off. About 540 in a fortnight
    public static IEnumerable<int> SitemapMatches(IEnumerable<Data.Match> matches) =>
        matches.Where(m => Names.GroupOrder.Contains(m.League) && !Data.ClubData.CalledOff.Contains(m.Status)).Select(m => m.Id);
}
