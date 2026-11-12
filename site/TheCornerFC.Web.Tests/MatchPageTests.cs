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
        Assert.Contains("<a class=\"link-btn\" href=\"/match/example\" rel=\"nofollow\">See an example</a>", body);
        Assert.DoesNotContain("lineup-toggle", body);
        Assert.DoesNotContain("why-toggle", body);
    }

    // "See an example": the newest finished match that had a prediction, on its own page, which
    // says what it is an example of and is kept out of search engines
    [Fact]
    public async Task See_an_example_goes_on_to_the_newest_finished_match_that_had_a_prediction()
    {
        const string season = """
            {"matches":[[1002,"2026-10-18T14:00:00+00:00",39,"Regular Season - 8",49,42,"FT",0,2,0.4,0.3,0.3,1.3,1.2,"1-1"],
             [1004,"2026-10-25T14:00:00+00:00",39,"Regular Season - 9",42,49,"FT",1,1,0.5,0.27,0.23,1.7,1.1,"2-1"],
             [1005,"2026-10-26T14:00:00+00:00",39,"Regular Season - 9",49,42,"FT",3,0,null,null,null,null,null,null],
             [1001,"2030-10-26T16:30:00+00:00",39,"Regular Season - 10",42,49,"NS",null,null,0.5,0.27,0.23,1.7,1.1,"2-1"]],"paywall":true}
            """;
        async Task<HttpResponseMessage> Go(string matches)
        {
            using var site = new SiteFactory("production", r => r.RequestUri!.AbsolutePath.EndsWith("site_matches") ? StubHandler.Json(matches)
                : r.RequestUri.Query.Contains("p_key=site&") ? StubHandler.Json(Site) : StubHandler.Json("null"));
            var r = await site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com") }).GetAsync("/match/example");
            Assert.Contains("\"p_leagues\":[39]", site.Handler.Bodies[site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath.EndsWith("site_matches"))]);
            return r;
        }
        var to = await Go(season);
        Assert.Equal(HttpStatusCode.Redirect, to.StatusCode);
        Assert.Equal("/match/1004?example=1", to.Headers.Location!.ToString());
        Assert.Equal("noindex", to.Headers.GetValues("X-Robots-Tag").Single());
        // nothing played yet: the matches
        Assert.Equal("/matches", (await Go(Upcoming)).Headers.Location!.ToString());

        var (_, body, _, f) = await Get("/match/1002?example=1", Finished);
        using var _f = f;
        Assert.Contains("An example of what subscribers get.", body);
        Assert.Contains("<meta name=\"robots\" content=\"noindex\" />", body);
        // the same match at its own address, and a match to come, say nothing of it
        var (_, plain, _, f2) = await Get("/match/1002", Finished);
        using var _f2 = f2;
        Assert.DoesNotContain("An example of what subscribers get.", plain);
        Assert.DoesNotContain("content=\"noindex\"", plain);
        var (_, later, _, f3) = await Get("/match/1001?example=1", Upcoming);
        using var _f3 = f3;
        Assert.DoesNotContain("An example of what subscribers get.", later);
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
