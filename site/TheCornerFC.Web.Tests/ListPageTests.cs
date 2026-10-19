using System.Net;

namespace TheCornerFC.Web.Tests;

// The list pages served whole, against a stand-in database
public class ListPageTests
{
    const string Site = """
        {"generated_at":"2026-10-18T01:40:00+00:00","competitions":{
          "39":{"name":"Premier League","country":"England","type":"League"},
          "45":{"name":"FA Cup","country":"England","type":"Cup"},
          "78":{"name":"Bundesliga","country":"Germany","type":"League"}},
         "teams":{"42":"Arsenal","33":"Manchester United","157":"Bayern München"}}
        """;
    const string Rankings = """
        {"fields":["team","league","current","st","lt","played","form","in_league","attack","defence","home","away"],
         "rankings":[[157,78,1118.4,1117.5,1118.2,287,33.1,1,1189.4,1047.4,1124,1112.7],
                     [42,39,1093.9,1094.1,1095.7,333,15.1,1,1071.9,1115.9,1089.8,1097.9],
                     [33,39,1050.2,1050,1049.6,300,-12.4,1,1050,1050,1050,1050]]}
        """;
    const string Nations = """
        {"latest_match":"2026-10-14","matches":49000,"from_api":12,"aliases":{},"nations":[
          {"name":"Spain","flag":"es","confed":"UEFA","current":2100.4,"year_ago":2080,"played":700,"w":8,"d":2,"l":1,"last":{"date":"2026-10-14","opp":"Italy","gf":2,"ga":1,"comp":"Friendly"}},
          {"name":"Brazil","flag":"br","confed":"CONMEBOL","current":2050,"year_ago":null,"played":900,"w":6,"d":3,"l":2,"last":{"date":"2026-10-10","opp":"Chile","gf":1,"ga":1,"comp":"WCQ"}}]}
        """;

    static HttpResponseMessage Answer(HttpRequestMessage r)
    {
        var q = r.RequestUri!.Query;
        if (r.RequestUri.AbsolutePath.EndsWith("site_player_facets")) return StubHandler.Json("""{"nats":["Spain"]}""");
        return StubHandler.Json(q.Contains("p_key=site&") ? Site : q.Contains("p_key=rankings") ? Rankings : q.Contains("p_key=nations") ? Nations : "null");
    }

    static async Task<(HttpStatusCode, string)> Get(string path)
    {
        using var site = new SiteFactory("production", Answer);
        var r = await site.CreateClient(new() { BaseAddress = new Uri("https://thecornerfc.com") }).GetAsync(path);
        return (r.StatusCode, await r.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Clubs_lists_every_club_with_its_ratings_and_the_menu()
    {
        var (status, html) = await Get("/clubs");
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Contains("<title>Clubs · The Corner FC</title>", html);
        Assert.Contains("href=\"/club/157\" data-short=\"Bayern\">Bayern München</a>", html);
        Assert.Contains("<span class=\"form-down\">-12</span>", html);
        Assert.Contains("<span class=\"flabel\">England</span>", html);
        Assert.Contains("Every club ranked by strength", html);
    }

    [Fact]
    public async Task Clubs_keeps_one_league_and_says_so_in_its_title()
    {
        var (_, html) = await Get("/clubs?c=39");
        // (a country with one league has one chip, named for the country)
        Assert.Contains("<title>England clubs · The Corner FC</title>", html);
        Assert.DoesNotContain("Bayern München</a>", html);
    }

    [Fact]
    public async Task Leagues_ranks_each_league_by_its_clubs_average()
    {
        var (status, html) = await Get("/leagues");
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.True(html.IndexOf(">Bundesliga</a>", StringComparison.Ordinal) < html.IndexOf(">Premier League</a>", StringComparison.Ordinal));
    }

    [Fact]
    public async Task A_country_lists_its_leagues_cups_and_clubs_and_an_unknown_one_is_not_found()
    {
        var (status, html) = await Get("/country/England");
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Contains("<span class=\"pl-meta\">1 league · 1 cup · 2 clubs</span>", html);
        Assert.Contains("2 clubs · top rated Arsenal", html);
        Assert.Equal(HttpStatusCode.NotFound, (await Get("/country/Narnia")).Item1);
    }

    [Fact]
    public async Task Nations_ranks_national_teams_and_links_the_ones_with_players_on_the_site()
    {
        var (status, html) = await Get("/nations");
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Contains("<a class=\"team-link\" href=\"/nation/Spain\">Spain</a>", html);
        Assert.Contains("<span class=\"team-link\">Brazil</span>", html);
        Assert.Contains("World #1 · Last 12 months: 8W 2D 1L · Last match: 2–1 v Italy (Friendly, 14 Oct 2026)", html);
        Assert.Contains("49,000 matches, the latest on 14 Oct 2026", html);
        Assert.Contains(" and API-Football (12 recent matches)", html);
    }
}
