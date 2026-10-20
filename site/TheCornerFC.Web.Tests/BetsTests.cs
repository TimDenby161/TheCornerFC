using System.Net;
using System.Text.Json;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// The two paper-bet pages in the Admin area: the simulation's record and the open selections,
// drawn from the administrator's "bets" document (against a stand-in database: nothing sent anywhere)
public class BetsTests
{
    static string Cookie() =>
        $"{Sessions.Cookie}={Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(new Session("access-1", "refresh-1", DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), "user-1", "admin@example.com")))}";
    static HttpRequestMessage Get(string path)
    {
        var m = new HttpRequestMessage(HttpMethod.Get, path);
        m.Headers.Add("Cookie", Cookie());
        return m;
    }
    static HttpClient Client(SiteFactory site) =>
        site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com"), HandleCookies = false });
    static string Fn(HttpRequestMessage r) => r.RequestUri!.AbsolutePath.Replace("/rest/v1/rpc/", "");

    const string Site = """{"generated_at":"","competitions":{"39":{"name":"Premier League","country":"England","type":"League"},"140":{"name":"La Liga","country":"Spain","type":"League"}},"teams":{"42":"Arsenal","63":"Leeds"}}""";
    static string Bet(int id, string strategy, int fixture, string kickoff, int league, string market, string sel, double odds, string? result, double? profit, double? clv = null, bool cautious = false) =>
        $$"""{"id":{{id}},"strategy":"{{strategy}}","fixture":{{fixture}},"kickoff":"{{kickoff}}","league":{{league}},"market":"{{market}}","selection":"{{sel}}","model_prob":0.55,"fair_prob":0.48,"odds":{{odds}},"closing_odds":{{(clv is null ? "null" : "1.9")}},"clv":{{(clv is null ? "null" : clv.ToString())}},"result":{{(result is null ? "null" : $"\"{result}\"")}},"profit":{{(profit is null ? "null" : profit.ToString())}},"home":"Arsenal","away":"Leeds","home_id":42,"away_id":63,"score":{{(result is null ? "null" : "\"2-0\"")}},"cautious":{{(cautious ? "true" : "false")}}}""";
    static readonly string Soon = DateTimeOffset.UtcNow.AddDays(2).ToString("yyyy-MM-dd'T'14:00:00+00:00");
    static string Doc() => $$"""
        {"rules":{"min_edge":0.05,"max_odds":4.5,"stake_gbp":10,"bank":1000},"bets":[
          {{Bet(1, "early", 100, "2026-10-04T14:00:00+00:00", 39, "1X2", "Home", 2.1, "win", 1.1, clv: 0.02)}},
          {{Bet(2, "late", 100, "2026-10-04T14:00:00+00:00", 39, "1X2", "Away", 3.5, "loss", -1)}},
          {{Bet(3, "late", 101, "2026-10-05T19:00:00+00:00", 140, "OU25", "Over 2.5", 1.95, "loss", -1, clv: -0.01, cautious: true)}},
          {{Bet(4, "early", 102, Soon, 39, "BTTS", "Yes", 1.8, null, null)}},
          {{Bet(5, "early", 102, Soon, 39, "1X2", "Draw", 3.4, null, null)}}]}
        """;

    static SiteFactory Make(bool admin = true) => new("production", r => Fn(r) switch
    {
        "am_admin" => StubHandler.Json(admin ? "true" : "false"),
        "admin_doc" => StubHandler.Json($$"""{"ok":true,"doc":{{Doc()}}}"""),
        "site_doc" when r.RequestUri!.Query.Contains("p_key=site&") => StubHandler.Json(Site),
        "site_doc" when r.RequestUri!.Query.Contains("p_key=rankings") => StubHandler.Json("""{"fields":["team"],"rankings":[]}"""),
        _ => StubHandler.Json("null"),
    });

    [Fact]
    public async Task The_simulation_counts_one_bet_per_pick_and_lists_the_settled_ones_newest_first()
    {
        using var site = Make();
        var r = await Client(site).SendAsync(Get("/admin/simulation"));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.True(r.Headers.CacheControl is { Private: true, NoStore: true });
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains("BeGambleAware.org", html);
        // All: the night-before result bet stands for match 100, so the pre-kickoff one is left out
        Assert.Contains("<div class=\"stats-value\">£1,001.00</div>", html);
        Assert.Contains("Started with £1,000.00 · £20.00 on 2 pending", html);
        Assert.Contains("<span class=\"pos\">&#x2B;£1.00</span>", html);
        Assert.Contains("Settled (2)", html);
        Assert.True(html.IndexOf("Over 2.5", StringComparison.Ordinal) < html.IndexOf("Home win", StringComparison.Ordinal), "newest first");
        Assert.Contains("Won &#x2B;£11.00", html);
        Assert.Contains("When taken: model 55% · market fair 48% · difference &#x2B;7 pts · closed 1.90 · simulated bank £1,011.00", html);
        Assert.Contains("at least 5% better than even, at odds up to 4.5", html);
        Assert.Contains("2 paper bets still to be played", html);
        Assert.Contains("href=\"/club/42\"", html);
        Assert.Equal("Bearer access-1", site.Handler.Sent.First(x => Fn(x) == "admin_doc").Headers.Authorization!.ToString());
    }

    [Fact]
    public async Task The_simulations_choices_narrow_the_bets_and_stay_in_each_link()
    {
        using var site = Make();
        var html = await (await Client(site).SendAsync(Get("/admin/simulation?s=late&c=39"))).Content.ReadAsStringAsync();
        // pre-kickoff bets in the Premier League: only the away bet that lost
        Assert.Contains("Settled (1)", html);
        Assert.Contains("Lost −£10.00", html);
        Assert.DoesNotContain("Over 2.5", html);
        Assert.Contains("href=\"?c=39&amp;s=late&amp;m=BTTS\"", html);
        Assert.Contains("<tr class=\"u-bold\"><td><a class=\"team-link\" href=\"?s=late\">Premier League</a>", html);
        var cautious = await (await Client(site).SendAsync(Get("/admin/simulation?v=cautious"))).Content.ReadAsStringAsync();
        Assert.Contains("Settled (1)", cautious);
        Assert.Contains("Over 2.5", cautious);
    }

    [Fact]
    public async Task Model_vs_market_shows_the_open_selections_by_day_and_competition()
    {
        using var site = Make();
        var r = await Client(site).SendAsync(Get("/admin/model-vs-market"));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains("<span class=\"comp-group-name\">Premier League</span><span class=\"comp-group-count\">2</span>", html);
        Assert.Contains("<span class=\"match-meta\">2 selections</span>", html);
        Assert.Contains("<span class=\"sel\">Both teams to score: Yes</span>", html);
        Assert.Contains("<span class=\"sel\">Draw</span>", html);
        Assert.Contains("<div class=\"bet-match\">Arsenal v Leeds</div>", html);
        // the settled record: one of two beat the closing price (the pre-kickoff bet on match 100 is not counted)
        Assert.Contains("<span class=\"kpi-pill good\">&#x2B;5.0% return</span>", html);
        Assert.Contains("<div><span>Won</span><b>1 of 2</b></div>", html);
        Assert.Contains("<span class=\"kpi-pill good\">Above 50%</span>", html);
        // the match tops asked as the administrator
        var asked = site.Handler.Sent.Single(x => Fn(x) == "site_matches");
        Assert.Contains("\"p_ids\":[102]", site.Handler.Bodies[asked]);
        Assert.Equal("Bearer access-1", asked.Headers.Authorization!.ToString());
    }

    [Fact]
    public async Task Neither_page_is_shown_to_anyone_else()
    {
        using var site = Make(admin: false);
        foreach (var path in new[] { "/admin/simulation", "/admin/model-vs-market" })
            Assert.Equal(HttpStatusCode.NotFound, (await Client(site).SendAsync(Get(path))).StatusCode);
        Assert.DoesNotContain(site.Handler.Sent, x => Fn(x) == "admin_doc");
    }
}
