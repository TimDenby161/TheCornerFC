using System.Net;

namespace TheCornerFC.Web.Tests;

// A club's Overview against a stand-in database: its injured and suspended list links a player
// only when he has a page (he is among the club's listed players). The site sweep of 2026-10-22
// found six such links to long-term absentees who had dropped out of the ranks, each a 404.
public class ClubOverviewTests
{
    const string Site = """
        {"generated_at":"2026-10-22T01:40:00+00:00","competitions":{"39":{"name":"Premier League","country":"England","type":"League"}},
         "teams":{"42":"Arsenal"},"match_fields":["id","kickoff","league","home","away","status"],
         "player_fields":["id","name","position","rank","team","league","nationality","age","seasons","estimated","lg_rank","lg_n","position_ranks","season"],
         "player_season_fields":["minutes","goals","assists"],"player_seasons":[2026,2025,2024],"player_future_seasons":[2027]}
        """;
    const string Rankings = """
        {"fields":["team","league","current","st","lt","played","form","in_league","attack","defence","home","away"],
         "rankings":[[42,39,1093.9,1094.1,1095.7,333,15.1,1,1071.9,1115.9,1089.8,1097.9]]}
        """;
    const string Players = """{"total":1,"rows":[[1460,"B. Saka","RW",88.1,42,39,"England",25,[88.1,86,84],[],2,600,{"W":88.1},[500,3,2]]]}""";
    const string Injuries = """
        {"teams":{"42":{"kickoff":"2026-10-25T14:00:00+00:00","upcoming":true,
          "players":[[1460,"B. Saka","Missing Fixture",null,1],[26095,"M. Sverko","Missing Fixture",null,30]]}}}
        """;

    [Fact]
    public async Task The_injury_list_links_only_the_players_who_have_a_page()
    {
        using var site = new SiteFactory("production", r =>
        {
            var path = r.RequestUri!.AbsolutePath;
            var q = r.RequestUri.Query;
            if (path.EndsWith("site_players")) return StubHandler.Json(Players);
            if (path.EndsWith("site_matches")) return StubHandler.Json("""{"matches":[]}""");
            return StubHandler.Json(q.Contains("p_key=site&") ? Site : q.Contains("p_key=rankings") ? Rankings : q.Contains("p_key=injuries") ? Injuries : "null");
        });
        var r = await site.CreateClient(new() { BaseAddress = new Uri("https://thecornerfc.com") }).GetAsync("/club/42");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains("<span class=\"inj-surname\"><a class=\"player-link\" href=\"/player/1460\">", html);
        Assert.DoesNotContain("href=\"/player/26095\"", html);              // no page: his name, not a link
        Assert.Contains("Sverko", html);
    }
}
