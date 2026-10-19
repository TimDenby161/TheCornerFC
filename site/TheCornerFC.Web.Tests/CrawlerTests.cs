using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/sitemap.test.ts and the robots.txt route, for the C# site
public class CrawlerTests
{
    static readonly SiteEnvironment Live = SiteEnvironment.Named("production"), Staging = SiteEnvironment.Named("staging");

    [Fact]
    public void The_sitemap_lists_the_main_pages_each_league_once_and_each_club()
    {
        var xml = Crawlers.Sitemap("https://thecornerfc.com", [(42, 39), (7, 39), (9, 140), (5, null)]);
        var locs = System.Text.RegularExpressions.Regex.Matches(xml, "<loc>([^<]+)</loc>").Select(m => m.Groups[1].Value).ToList();
        Assert.Equal(Crawlers.MainPages.Select(p => "https://thecornerfc.com" + p), locs.Take(Crawlers.MainPages.Count));
        Assert.Equal(["https://thecornerfc.com/league/39/table", "https://thecornerfc.com/league/140/table",
            "https://thecornerfc.com/club/5", "https://thecornerfc.com/club/7", "https://thecornerfc.com/club/9", "https://thecornerfc.com/club/42"],
            locs.Skip(Crawlers.MainPages.Count));
        Assert.StartsWith("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">", xml);
        Assert.EndsWith("</urlset>\n", xml);
        foreach (var p in new[] { "/account", "/admin", "/fpl", "/my-fpl-team", "/efl-fantasy" })
            Assert.DoesNotContain(locs, l => l.EndsWith(p));
    }

    [Fact]
    public void Search_engines_are_let_in_at_the_live_address_only()
    {
        var live = Crawlers.Robots(Live, "thecornerfc.com");
        Assert.Contains("Disallow: /account", live);
        Assert.Contains("Sitemap: https://thecornerfc.com/sitemap.xml", live);
        Assert.StartsWith("User-agent: SemrushBot\nDisallow: /\n\nUser-agent: AhrefsBot\nDisallow: /\n", live);
        Assert.Contains("\nUser-agent: *\nDisallow: /account\n", live);
        Assert.Equal("User-agent: *\nDisallow: /\n", Crawlers.Robots(Live, "thecornerfc.azurewebsites.net"));
        Assert.Equal("User-agent: *\nDisallow: /\n", Crawlers.Robots(Staging, "staging.thecornerfc.com"));
    }
}
