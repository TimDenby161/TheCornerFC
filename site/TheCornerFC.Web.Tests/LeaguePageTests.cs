using System.Net;

namespace TheCornerFC.Web.Tests;

// A competition's page served whole, against a stand-in database
public class LeaguePageTests
{
    const string Site = """{"generated_at":"2026-10-18T01:40:00+00:00","competitions":{"39":{"name":"Premier League","country":"England","type":"League"},"45":{"name":"FA Cup","country":"England","type":"Cup"}},"teams":{"42":"Arsenal","50":"Manchester City","51":"Crystal Palace"}}""";
    const string Rankings = """{"fields":["team","league","current","st","lt","played","form","in_league","attack","defence","home","away"],"rankings":[[50,39,1109.6,1107.7,1091.8,368,null,1,1128.3,1090.9,1105.1,1114.1],[42,39,1093.9,1094.1,1095.7,333,15.1,1,1071.9,1115.9,1089.8,1097.9]]}""";
    const string League = """
        {"id":39,"season":2026,"start":"2026-08-21",
         "table_fields":["group","rank","team","played","win","draw","lose","gf","ga","gd","points","form","description"],
         "table":[["PL",1,50,5,5,0,0,13,5,8,15,"WWWWW","Champions League"],["PL",2,42,5,4,0,1,9,5,4,12,"LWWWW","Champions League"]],
         "fixture_fields":["id","kickoff","round","home","away","status","hg","ag","pen_h","pen_a","home_xg","away_xg","p_home","p_draw","p_away"],
         "fixtures":[[2,"2026-10-10T11:30:00+00:00","Regular Season - 6",42,50,"NS",null,null,null,null,1.6,1.4,0.4,0.26,0.34]],
         "teams":{},"cut":true,"projected_fields":["group","place","team","left","points"],"projected":[["PL",1,50,33,81]]}
        """;

    static HttpResponseMessage Answer(HttpRequestMessage r)
    {
        if (r.RequestUri!.AbsolutePath.EndsWith("site_league"))
            return StubHandler.Json(r.Content!.ReadAsStringAsync().Result.Contains("39") ? League : "null");
        var q = r.RequestUri.Query;
        return StubHandler.Json(q.Contains("p_key=site&") ? Site : q.Contains("p_key=rankings") ? Rankings : "null");
    }

    static async Task<HttpResponseMessage> Get(string path)
    {
        var site = new SiteFactory("production", Answer);
        return await site.CreateClient(new() { BaseAddress = new Uri("https://thecornerfc.com"), AllowAutoRedirect = false }).GetAsync(path);
    }

    [Fact]
    public async Task A_competitions_own_address_opens_its_standings()
    {
        var r = await Get("/league/39");
        Assert.Equal(HttpStatusCode.TemporaryRedirect, r.StatusCode);
        Assert.Equal("/league/39/table", r.Headers.Location!.ToString());
    }

    [Fact]
    public async Task The_standings_show_the_table_its_zones_and_the_tabs()
    {
        var html = await (await Get("/league/39/table")).Content.ReadAsStringAsync();
        Assert.Contains("<title>Premier League table · The Corner FC</title>", html);
        Assert.Contains("<td class=\"lt-pos zone-0\">1</td>", html);
        Assert.Contains("<a href=\"/league/39/table\" aria-current=\"page\">Standings</a>", html);
        Assert.Contains("<i class=\"res-l\">L</i>", html);
        Assert.Contains("<span><i class=\"zone-0\"></i>Champions League</span>", html);
    }

    [Fact]
    public async Task A_visitor_without_a_subscription_gets_the_projected_headline_only()
    {
        var html = await (await Get("/league/39/projected")).Content.ReadAsStringAsync();
        Assert.Contains("<td class=\"lt-wide\">33</td><td><b>81</b></td>", html);
        Assert.Contains("are for subscribers.", html);
    }

    [Fact]
    public async Task The_matches_tab_gives_the_models_chances_for_matches_to_come()
    {
        var html = await (await Get("/league/39/matches")).Content.ReadAsStringAsync();
        Assert.Contains("<div class=\"lf-sub\">40% · 26% · 34%</div>", html);
        Assert.Contains("<div class=\"modal-section\">Sat 10 Oct</div>", html);
    }

    [Fact]
    public async Task A_competition_nobody_knows_has_no_page() =>
        Assert.Equal(HttpStatusCode.NotFound, (await Get("/league/99999/table")).StatusCode);
}
