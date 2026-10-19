using System.Net;

namespace TheCornerFC.Web.Tests;

// A player's page served whole, against a stand-in database
public class PlayerPageTests
{
    const string Site = """
        {"generated_at":"2026-10-18T01:40:00+00:00","competitions":{"39":{"name":"Premier League","country":"England","type":"League"}},
         "teams":{"50":"Manchester City"},"match_fields":["id","kickoff","league","home","away","status"],
         "player_fields":["id","name","position","rank","team","league","nationality","age","seasons","estimated","lg_rank","lg_n","position_ranks","season"],
         "player_season_fields":["minutes","goals","assists"],"player_seasons":[2026,2025,2024],"player_future_seasons":[2027]}
        """;
    const string Row = """{"total":1,"rows":[[129033,"J. Gvardiol","D",92.6,50,39,"Croatia",24,[92.6,91.1,96.0],[],3,600,{"FB":92.6,"CB":90.1},[459,1,3]]]}""";
    const string Doc = """
        {"id":129033,"born":"2002-01-23","season_fields":["season","team","league","apps","starts","minutes","goals","assists","yellow","red"],
         "seasons":[[2026,50,39,6,5,459,1,3,0,0],[2025,50,39,30,28,1374,2,2,3,0]],
         "match_fields":["fixture","date","league","team","opponent","home","gf","ga","started","minutes","role","rank","goals","assists","yellow","red"],
         "matches":[[1,"2026-10-04","39",50,42,1,2,1,1,90,"LB",92.1,1,0,0,0]],
         "spell_fields":["team","minutes","club_rank","goals","assists"],"spells":{"2026":[[50,459,1128,1,3]],"now":[[50,1493,1136,3,4]]},
         "positions":{"12m":[["LB",900],["CB",300]],"2026":[["LB",459]]},"injury":null,"teams":{}}
        """;

    static HttpResponseMessage Answer(HttpRequestMessage r)
    {
        var path = r.RequestUri!.AbsolutePath;
        var body = r.Content?.ReadAsStringAsync().Result ?? "";
        if (path.EndsWith("site_players")) return StubHandler.Json(body.Contains("129033") ? Row : """{"total":0,"rows":[]}""");
        if (path.EndsWith("site_player_page")) return StubHandler.Json(Doc);
        if (path.EndsWith("site_matches")) return StubHandler.Json("""{"matches":[]}""");
        return StubHandler.Json(r.RequestUri.Query.Contains("p_key=site&") ? Site : "null");
    }

    static async Task<(HttpStatusCode, string)> Get(string path)
    {
        using var site = new SiteFactory("production", Answer);
        var r = await site.CreateClient(new() { BaseAddress = new Uri("https://thecornerfc.com") }).GetAsync(path);
        return (r.StatusCode, await r.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task The_overview_gives_his_ability_league_place_season_and_positions()
    {
        var (status, html) = await Get("/player/129033");
        Assert.Equal(HttpStatusCode.OK, status);
        Assert.Contains("<title>J. Gvardiol · The Corner FC</title>", html);
        Assert.Contains("<span class=\"val\">93</span><span class=\"lbl\">Ability</span>", html);
        Assert.Contains("of 600 in Premier League", html);
        Assert.Contains("<span class=\"pos-chip-pos\">FB</span><span class=\"pos-chip-rank\">93</span>", html);
        Assert.Contains("Only 459 minutes so far", html);
    }

    [Fact]
    public async Task The_career_tab_draws_the_chart_for_the_react_chart_to_take_over()
    {
        var (_, html) = await Get("/player/129033/career");
        Assert.Contains("data-island=\"rank-chart\"><script type=\"application/json\">{\"points\":[{\"label\":\"24/25\"", html);
        Assert.Contains("<svg viewBox=\"0 0 640 180\"", html);
        Assert.Contains("<script type=\"module\" src=\"/client/islands.js\"", html);
        Assert.Contains("rated as full-back", html);
    }

    [Fact]
    public async Task A_player_not_in_the_ranks_has_no_page() =>
        Assert.Equal(HttpStatusCode.NotFound, (await Get("/player/1")).Item1);
}
