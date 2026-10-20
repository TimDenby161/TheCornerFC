using System.Net;

namespace TheCornerFC.Web.Tests;

// A match's own page served whole, against a stand-in database
public class MatchPageTests
{
    const string Site = """
        {"generated_at":"2026-10-20T01:40:00+00:00","competitions":{"39":{"name":"Premier League","country":"England","type":"League"}},
         "teams":{"42":"Arsenal","49":"Chelsea"},
         "match_fields":["id","kickoff","league","round","home","away","status","hg","ag","p_home","p_draw","p_away","home_xg","away_xg","likely"]}
        """;
    const string Upcoming = """{"matches":[[1001,"2030-10-26T16:30:00+00:00",39,"Regular Season - 9",42,49,"NS",null,null,0.5,0.27,0.23,1.7,1.1,"2-1"]],"reasons":{"1001":[["strength",0.31]]},"paywall":false}""";
    const string Finished = """{"matches":[[1002,"2026-10-18T14:00:00+00:00",39,"Regular Season - 8",49,42,"FT",0,2,0.4,0.3,0.3,1.3,1.2,"1-1"]],"paywall":false}""";
    const string Locked = """{"matches":[[1003,"2030-10-26T16:30:00+00:00",39,"Regular Season - 9",42,49,"NS",null,null,null,null,null,null,null,null]],"paywall":true}""";

    static async Task<(HttpStatusCode Status, string Body, HttpResponseMessage R, SiteFactory F)> Get(string path, string matches = """{"matches":[]}""")
    {
        var site = new SiteFactory("production", r =>
        {
            var p = r.RequestUri!.AbsolutePath;
            if (p.EndsWith("site_matches")) return StubHandler.Json(matches);
            if (r.RequestUri.Query.Contains("p_key=site&")) return StubHandler.Json(Site);
            if (r.RequestUri.Query.Contains("p_key=rankings")) return StubHandler.Json("""{"fields":["team"],"rankings":[]}""");
            return StubHandler.Json("null");
        });
        var r = await site.CreateClient(new() { BaseAddress = new Uri("https://thecornerfc.com") }).GetAsync(path);
        return (r.StatusCode, await r.Content.ReadAsStringAsync(), r, site);
    }

    [Fact]
    public async Task A_match_to_come_has_its_card_with_the_panels_open_and_names_both_sides_in_its_title()
    {
        var (status, body, r, f) = await Get("/match/1001", Upcoming);
        using var _ = f;
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Contains("<title>Arsenal v Chelsea · Premier League, Sat 26 Oct · The Corner FC</title>", body);
        Assert.Contains("<h1 class=\"app-title\">Arsenal v Chelsea</h1>", body);
        Assert.Contains("the model&#x27;s win, draw and loss chances", body);
        Assert.Contains("data-fixture=\"1001\"", body);
        Assert.Contains("data-open=\"1\"", body);
        Assert.Contains("<a href=\"/league/39\">Premier League</a>", body);
        Assert.Contains("Predicted line-ups", body);
        Assert.Contains("Model detail", body);
        Assert.Contains("Arsenal rated the stronger side", body);
        Assert.DoesNotContain("match-page-link", body);   // no link to itself
        Assert.Contains("public", r.Headers.CacheControl?.ToString());
    }

    [Fact]
    public async Task A_finished_match_says_so_in_its_description_and_shows_the_score()
    {
        var (status, body, _, f) = await Get("/match/1002", Finished);
        using var _f = f;
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Contains("Chelsea v Arsenal · Premier League, Sun 18 Oct", body);
        Assert.Contains("the result, the model&#x27;s chances before kick-off", body);
        Assert.Contains("<span class=\"final-box\">0</span>", body);
        Assert.Contains(">Line-ups<", body);
    }

    [Fact]
    public async Task What_the_database_holds_back_stays_held_back()
    {
        var (status, body, _, f) = await Get("/match/1003", Locked);
        using var _f = f;
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Contains("are for subscribers", body);
        Assert.DoesNotContain("lineup-toggle", body);
        Assert.DoesNotContain("why-toggle", body);
    }

    [Theory]
    [InlineData("/match/999")]          // no such match
    [InlineData("/match/abc")]
    [InlineData("/match/12345678901")]
    public async Task An_unknown_match_is_not_found(string path)
    {
        var (status, _, _, f) = await Get(path);
        using var _f = f;
        Assert.Equal(HttpStatusCode.NotFound, status);
    }
}
