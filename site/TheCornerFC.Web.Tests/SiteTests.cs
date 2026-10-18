using System.Net;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// The whole site in memory: what every response carries, and the pages step 1 brings
public class SiteTests
{
    static HttpClient Client(SiteFactory site, string host) =>
        site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri($"https://{host}") });

    [Fact]
    public async Task Every_page_carries_the_security_headers_and_its_policy()
    {
        using var site = new SiteFactory("production");
        var r = await Client(site, "thecornerfc.com").GetAsync("/");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        foreach (var (k, v) in Gate.SecurityHeaders) Assert.Equal(v, r.Headers.GetValues(k).Single());
        var policy = r.Headers.GetValues("Content-Security-Policy").Single();
        Assert.Contains("style-src 'self';", policy);
        Assert.Contains("frame-ancestors 'none'", policy);
        Assert.Contains("Cookie", r.Headers.Vary);
        Assert.False(r.Headers.Contains("X-Robots-Tag"));
        // the page's own script carries the nonce the policy names
        var nonce = System.Text.RegularExpressions.Regex.Match(policy, "'nonce-([^']+)'").Groups[1].Value;
        Assert.Contains($"<script src=\"/site.js\" nonce=\"{nonce}\">", await r.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Staging_is_never_for_search_engines_and_says_what_it_is()
    {
        using var site = new SiteFactory("staging");
        var r = await Client(site, "staging.thecornerfc.com").GetAsync("/");
        Assert.Equal("noindex, nofollow", r.Headers.GetValues("X-Robots-Tag").Single());
        Assert.Contains("id=\"staging-strip\"", await r.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task A_server_reached_at_the_other_copys_address_serves_nothing()
    {
        using var site = new SiteFactory("staging");
        Assert.Equal(HttpStatusCode.InternalServerError, (await Client(site, "thecornerfc.com").GetAsync("/")).StatusCode);
    }

    [Theory]
    [InlineData("http://thecornerfc.com/clubs?c=39", "https://thecornerfc.com/clubs?c=39")]
    [InlineData("https://www.thecornerfc.com/terms", "https://thecornerfc.com/terms")]
    [InlineData("https://thecornerfc.com/terms.html?x=1", "/terms?x=1")]
    public async Task Sends_old_and_other_addresses_to_the_one_address(string from, string to)
    {
        using var site = new SiteFactory("production");
        var r = await site.CreateClient(new() { AllowAutoRedirect = false }).GetAsync(from);
        Assert.Equal(HttpStatusCode.MovedPermanently, r.StatusCode);
        Assert.Equal(to, r.Headers.Location!.ToString());
        Assert.True(r.Headers.Contains("Strict-Transport-Security"));
    }

    [Fact]
    public async Task An_address_with_no_page_gets_the_plain_page_not_found()
    {
        using var site = new SiteFactory("production");
        var r = await Client(site, "thecornerfc.com").GetAsync("/no-such-page");
        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains("<h2>Page not found</h2>", html);
        Assert.Contains("class=\"menu-link\"", html);
    }

    [Fact]
    public async Task Says_which_copy_answered_and_what_it_reads()
    {
        using var site = new SiteFactory("staging");
        var r = await Client(site, "staging.thecornerfc.com").GetAsync("/version");
        Assert.Equal("no-store", r.Headers.CacheControl!.ToString());
        Assert.Equal("""{"environment":"staging","commit":"local","project":"sjvzmlbdowebylnzvisa","site":"csharp"}""", await r.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task The_live_sitemap_lists_the_clubs_from_the_rankings_and_nowhere_else_has_one()
    {
        using var site = new SiteFactory("production", r => StubHandler.Json(r.RequestUri!.Query.Contains("p_key=rankings")
            ? """{"fields":["team","league","current"],"rankings":[[42,39,1500.0],[7,null,1400.0]]}""" : "null"));
        var xml = await Client(site, "thecornerfc.com").GetStringAsync("/sitemap.xml");
        Assert.Contains("<loc>https://thecornerfc.com/league/39/table</loc>", xml);
        Assert.Contains("<loc>https://thecornerfc.com/club/7</loc>", xml);
        using var staging = new SiteFactory("staging");
        Assert.Equal(HttpStatusCode.NotFound, (await Client(staging, "staging.thecornerfc.com").GetAsync("/sitemap.xml")).StatusCode);
    }

    [Fact]
    public async Task The_foot_of_every_page_says_when_its_data_was_fetched_in_the_visitors_time()
    {
        using var site = new SiteFactory("production", r => StubHandler.Json(r.RequestUri!.Query.Contains("p_key=site")
            ? """{"generated_at":"2026-10-18T01:40:00+00:00","freshness":{"odds":"2026-10-18T13:05:00+00:00","model":{"name":"match-prediction","code":"9afa9ed"}}}""" : "null"));
        var html = await Client(site, "thecornerfc.com").GetStringAsync("/");
        Assert.Contains("Data updated <time datetime=\"2026-10-18T01:40:00.000Z\" data-show=\"short\">18 Oct</time> <time datetime=\"2026-10-18T01:40:00.000Z\" data-show=\"time\">02:40</time>", html);
        Assert.Contains("Odds last seen", html);
        Assert.DoesNotContain("Injuries updated", html);
        Assert.Contains("Model match-prediction · 9afa9ed", html);
    }
}
