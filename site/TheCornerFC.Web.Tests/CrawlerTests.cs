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
    public void The_sitemap_adds_each_main_competition_match_once_after_the_clubs_and_leaves_out_those_called_off()
    {
        var xml = Crawlers.Sitemap("https://thecornerfc.com", [(42, 39)], [1002, 1001, 1002]);
        Assert.EndsWith("<url><loc>https://thecornerfc.com/club/42</loc></url>\n<url><loc>https://thecornerfc.com/match/1001</loc></url>\n" +
                        "<url><loc>https://thecornerfc.com/match/1002</loc></url>\n</urlset>\n", xml);
        Data.Match M(int id, string status, int league = 39) => new(id, "", league, null, 1, 2, status, null, null, null, null, null, null, null, null, null, null, null, null, null,
            null, null, null, null, null, null, null, null, null, null, null, null, 0, [], null, null, null, null);
        Assert.Equal([1, 2, 4], Crawlers.SitemapMatches([M(1, "NS"), M(2, "FT"), M(3, "PST"), M(4, "1H"), M(5, "CANC")]));
        // only the competitions the site lists first: the Premier League and the Champions League, not the Allsvenskan
        Assert.Equal([6, 7], Crawlers.SitemapMatches([M(6, "NS", 39), M(7, "NS", 2), M(8, "NS", 113)]));
    }

    [Fact]
    public void The_sitemaps_matches_run_from_7_days_back_to_7_days_ahead_in_whole_days()
    {
        Assert.Equal(("2026-10-13T00:00:00.000Z", "2026-10-28T00:00:00.000Z"), Crawlers.SitemapDays(DateTimeOffset.Parse("2026-10-20T15:42:00+00:00")));
        Assert.Equal(Crawlers.SitemapDays(DateTimeOffset.Parse("2026-10-20T00:00:01+00:00")), Crawlers.SitemapDays(DateTimeOffset.Parse("2026-10-20T23:59:59+00:00")));
    }

    [Fact]
    public void Search_engines_are_let_in_at_the_live_address_only()
    {
        var live = Crawlers.Robots(Live, "thecornerfc.com");
        Assert.Contains("Disallow: /account", live);
        Assert.Contains("Sitemap: https://thecornerfc.com/sitemap.xml", live);
        Assert.StartsWith("User-agent: SemrushBot\nDisallow: /\n\nUser-agent: AhrefsBot\nDisallow: /\n", live);
        Assert.Contains("\nUser-agent: *\nContent-Signal: search=yes,ai-train=no,use=reference\nDisallow: /account\n", live);
        // AI-training crawlers are kept out; search engines never are
        foreach (var bot in new[] { "GPTBot", "Google-Extended", "CCBot", "ClaudeBot", "Applebot-Extended" })
            Assert.Contains($"\nUser-agent: {bot}\nDisallow: /\n", live);
        foreach (var engine in new[] { "Googlebot", "Bingbot", "bingbot", "Applebot\n", "DuckDuckBot" })
            Assert.DoesNotContain($"User-agent: {engine}", live);
        Assert.Contains("\nDisallow: /match/*/\n", live);          // the card panels' data, not the match pages
        Assert.Equal("User-agent: *\nDisallow: /\n", Crawlers.Robots(Live, "thecornerfc.azurewebsites.net"));
        Assert.Equal("User-agent: *\nDisallow: /\n", Crawlers.Robots(Staging, "staging.thecornerfc.com"));
    }
}
