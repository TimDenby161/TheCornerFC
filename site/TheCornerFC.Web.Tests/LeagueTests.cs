using System.Text.Json;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/league.test.ts, for the C# site: the same file, the same cases, the same answers
public class LeagueTests
{
    static readonly LeagueFile Lg = JsonSerializer.Deserialize<LeagueFile>("""
        {"id":39,"season":2026,"start":"2026-08-21",
         "table_fields":["group","rank","team","played","win","draw","lose","gf","ga","gd","points","form","description"],
         "table":[["PL",1,50,5,5,0,0,13,5,8,15,"WWWWW","Champions League"],["PL",2,42,5,4,0,1,9,5,4,12,"LWWWW","Champions League"],["PL",3,51,5,3,1,1,14,3,11,10,"WWDLW",null]],
         "fixture_fields":["id","kickoff","round","home","away","status","hg","ag","pen_h","pen_a","home_xg","away_xg","p_home","p_draw","p_away"],
         "fixtures":[[1,"2026-09-19T14:00:00+00:00","Regular Season - 5",51,42,"FT",3,0,null,null,null,null,null,null,null],
                     [2,"2026-10-10T11:30:00+00:00","Regular Season - 6",42,50,"NS",null,null,null,null,1.6,1.4,0.4,0.26,0.34],
                     [3,"2026-10-17T14:00:00+00:00","Regular Season - 7",50,51,"NS",null,null,null,null,2.1,0.9,0.62,0.21,0.17],
                     [4,"2026-10-24T14:00:00+00:00","Regular Season - 8",51,42,"NS",null,null,null,null,null,null,0.3,0.3,0.4]],
         "recent_xg_fields":["xg90","xga90","games"],"recent_xg":{"50":[2.1,0.8,5]},"teams":{"50":"Manchester City"},
         "cut":true,"projected_fields":["group","place","team","left","points"],"projected":[["PL",1,50,33,81]]}
        """, Database.Json)!;
    static readonly List<TableRow> Table = LeagueFiles.TableRows(Lg);
    static readonly List<Fixture> Fixtures = LeagueFiles.FixtureRows(Lg);

    [Fact]
    public void Reads_the_table_with_each_clubs_recent_expected_goals_the_fixtures_and_the_headline()
    {
        Assert.Equal((2.1, 0.8, 5), (Table[0].Xg90, Table[0].Xga90, Table[0].XgGames));
        Assert.Null(Table[1].Xg90);
        Assert.Equal(new Fixture(2, "2026-10-10T11:30:00+00:00", "Regular Season - 6", 42, 50, "NS", null, null, null, null, 1.6, 1.4, 0.4, 0.26, 0.34), Fixtures[1]);
        Assert.Equal([new Headline("PL", 1, 50, 33, 81)], LeagueFiles.Headline(Lg));
    }

    [Fact]
    public void Colours_the_zones_in_the_order_the_notes_first_appear_relegation_red()
    {
        Assert.Equal([("Champions League", "zone-0")], Leagues.Zones(Table.Select(r => r.Description)));
        Assert.Equal([("Promotion", "zone-0"), ("Relegation", "zone-down"), ("Relegation play-off", "zone-down2")],
            Leagues.Zones(["Promotion", null, "Relegation", "Promotion", "Relegation play-off"]));
    }

    [Fact]
    public void Opens_on_the_round_with_the_next_fixture_else_the_last()
    {
        var (rounds, open) = Leagues.Rounds(Fixtures);
        Assert.Equal(["Regular Season - 5", "Regular Season - 6", "Regular Season - 7", "Regular Season - 8"], rounds);
        Assert.Equal("Regular Season - 6", open);
        Assert.Equal("Regular Season - 5", Leagues.Rounds(Fixtures.Take(1).ToList()).Open);
        Assert.Null(Leagues.Rounds([]).Open);
        Assert.Equal("Round 6", Leagues.RoundLabel("Regular Season - 6"));
    }

    [Fact]
    public void Writes_a_chance_in_words_at_the_extremes()
    {
        Assert.Equal(["–", "<1%", ">99%", "100%", "43%"], new[] { 0, 0.004, 0.997, 1, 0.426 }.Select(Leagues.ChanceText));
        Assert.Equal(4, Leagues.FormPoints("WDL"));
    }

    // a fixed source of chance, the same as the Svelte site's test uses
    static Func<double> Seeded(uint seed) => () => { seed = (uint)((ulong)seed * 1664525 + 1013904223); return seed / 4294967296.0; };

    [Fact]
    public void Plays_the_season_out_exactly_as_the_svelte_site_does_given_the_same_chances()
    {
        var sims = Projection.Projectable(Fixtures);
        Assert.Equal([2, 3], sims.Select(f => f.Id));
        var proj = Projection.Group(Table, sims, 2000, Seeded(7));
        // what web/src/lib/league.ts gives for this table, these fixtures and seed 7
        Assert.Equal([50, 42, 51], proj.Select(p => p.Team));
        Assert.Equal([2, 1, 1], proj.Select(p => p.Left));
        Assert.Equal([18.384, 13.429, 10.749], proj.Select(p => Math.Round(p.Pts, 9)));
        Assert.Equal([9.0415, 4.1195, 9.839], proj.Select(p => Math.Round(p.Gd, 9)));
        Assert.Equal([0.9525, 0.0475, 0], proj[0].Pos.Select(p => Math.Round(p, 9)));
        Assert.Equal([0.0475, 0.8495, 0.103], proj[1].Pos.Select(p => Math.Round(p, 9)));
        Assert.Equal([0, 0.103, 0.897], proj[2].Pos.Select(p => Math.Round(p, 9)));
        Assert.Equal(5.96, proj[0].W, 9);
        Assert.Equal(0.47, proj[0].D, 9);
        foreach (var p in proj) Assert.Equal(1, p.Pos.Sum(), 9);
    }
}
