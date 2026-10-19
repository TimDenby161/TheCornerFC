using System.Text.Json;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/clubTable.test.ts, rankings.test.ts, cups.test.ts and the sorting in league.test.ts,
// for the C# site: the same cases and the same answers
public class ListTests
{
    static T Read<T>(string json) => JsonSerializer.Deserialize<T>(json, Database.Json)!;

    static readonly SiteDoc Site = Read<SiteDoc>("""
        {"generated_at":"","competitions":{
          "2":{"name":"UEFA Champions League","country":"World","type":"Cup"},
          "39":{"name":"Premier League","country":"England","type":"League"},
          "40":{"name":"Championship","country":"England","type":"League"},
          "78":{"name":"Bundesliga","country":"Germany","type":"League"},
          "113":{"name":"Allsvenskan","country":"Sweden","type":"League"},
          "307":{"name":"Pro League","country":"Saudi-Arabia","type":"League"}},
         "teams":{"33":"Manchester United","42":"Arsenal","63":"Leeds","157":"Bayern München","364":"Djurgården","2932":"Al-Hilal","900":"Old Club"}}
        """);
    const string Fields = """["team","league","current","st","lt","played","form","in_league","attack","defence","home","away"]""";
    static string Row(int team, int league, double lt, int inLeague = 1) => $"[{team},{league},{lt + 5},{lt},{lt},100,1,{inLeague},{lt},{lt},{lt},{lt}]";
    static readonly List<Club> All = Clubs.From(Read<Rankings>($$"""{"fields":{{Fields}},"rankings":[{{string.Join(',', Row(157, 78, 1118), Row(42, 39, 1096), Row(33, 39, 1049), Row(63, 40, 1017), Row(364, 113, 900), Row(2932, 307, 950), Row(900, 39, 990, 0))}}]}"""));
    static readonly List<Country> Countries = ClubTable.Countries(Site, All);
    static readonly Dictionary<int, HashSet<int>> CupClubs = new() { [2] = [157, 42, 900] };

    static (List<Club> Rows, bool Wide) Pick(string filter = "all", string[]? excluded = null, string search = "", string sort = "lt") =>
        ClubTable.Rows(Site, All, Countries, CupClubs, new(filter, (excluded ?? []).ToHashSet(), search, sort));
    static int[] Teams(string filter = "all", string[]? excluded = null, string search = "") => Pick(filter, excluded, search).Rows.Select(r => r.Team).ToArray();

    [Fact]
    public void Countries_put_the_big_five_first_then_the_rest_by_name_each_under_its_region()
    {
        Assert.Equal([("England", null), ("Germany", null), ("Saudi Arabia", "Asia"), ("Sweden", "Scandinavia")], Countries.Select(c => (c.Name, c.Region)));
        Assert.Equal([39, 40], Countries[0].Leagues);
    }

    [Fact]
    public void A_filter_is_a_league_country_region_or_cup_this_site_has_and_nothing_else()
    {
        foreach (var f in new[] { "all", "39", "c:England", "r:Scandinavia", "e:all", "e:2", "k:45" }) Assert.True(ClubTable.KnownFilter(f, Countries), f);
        foreach (var f in new[] { null, "", "2", "9999", "c:Narnia", "r:Atlantis", "e:45", "x:1", "39'" }) Assert.False(ClubTable.KnownFilter(f, Countries), f);
    }

    [Fact]
    public void Lists_the_clubs_in_a_tracked_league_this_season_highest_first()
    {
        Assert.Equal([157, 42, 33, 63, 2932, 364], Teams());
        Assert.True(Pick().Wide);
    }

    [Fact]
    public void Keeps_one_league_a_country_or_a_region()
    {
        Assert.Equal([42, 33], Teams("39"));
        Assert.False(Pick("39").Wide);
        Assert.Equal([42, 33, 63], Teams("c:England"));
        Assert.Equal([364], Teams("r:Scandinavia"));
    }

    [Fact]
    public void Shows_a_cups_clubs_whether_or_not_they_are_in_a_tracked_league() => Assert.Equal([157, 42, 900], Teams("e:2"));

    [Fact]
    public void Hides_excluded_countries_and_continents()
    {
        Assert.Equal([157, 2932, 364], Teams(excluded: ["England"]));
        Assert.Equal([2932], Teams(excluded: ["r:Europe"]));
        Assert.Equal([157], Teams("e:2", ["England"]));
        Assert.False(ClubTable.IsExcluded(Site, new HashSet<string> { "r:Europe" }, 2));
    }

    [Fact]
    public void Searches_every_ranked_club_whatever_the_menu_and_the_exclusions_say()
    {
        Assert.Equal([33], Teams("78", ["England"], "man utd"));
        Assert.Equal([900], Teams(search: "old"));
        Assert.Equal([157], Teams(search: "bayern munich"));
        Assert.Equal([42, 33], Teams(search: "epl"));
        Assert.Contains(" bayern munchen ", ClubTable.SearchText(Site, All[0]));
        Assert.Contains(" utd ", ClubTable.SearchText(Site, All[2]));
    }

    [Fact]
    public void The_menu_names_the_choice_in_full_opens_its_country_and_counts_clubs()
    {
        var menu = ClubTable.Menu(Site, Countries, "40", ClubTable.Counts(Site, All, Countries, CupClubs, new HashSet<string>()), ClubTable.ClubTitles);
        var chips = menu.Nodes.Where(n => !n.Sep).SelectMany(n => new[] { n }.Concat((n.Children ?? []).SelectMany(c => new[] { c }.Concat(c.Children ?? [])))).ToList();
        MenuNode Find(string v) => chips.First(n => n.Chip!.Value == v);
        Assert.Equal("England · Championship", menu.Name);
        Assert.Equal(1, menu.Count);
        Assert.True(Find("c:England").Open);
        Assert.True(Find("c:England").Chip!.HasActive);
        Assert.True(Find("40").Chip!.Pressed);
        Assert.Equal("Germany", Find("78").Chip!.Label);
        Assert.Null(Find("78").Children);
        Assert.Equal(6, Find("all").Chip!.Count);
        Assert.Equal(3, Find("c:England").Chip!.Count);
        Assert.Equal(3, Find("e:2").Chip!.Count);
        Assert.Equal(1, Find("r:Scandinavia").Chip!.Count);
    }

    // ---- rankings.test.ts
    static readonly List<Club> Ranked = Clubs.From(Read<Rankings>($$"""
        {"fields":{{Fields}},"rankings":[
          [157,78,1118.4,1117.5,1118.2,287,33.1,1,1189.4,1047.4,1124,1112.7],
          [42,39,1093.9,1094.1,1095.7,333,15.1,1,1071.9,1115.9,1089.8,1097.9],
          [50,39,1109.6,1107.7,1091.8,368,null,1,1128.3,1090.9,1105.1,1114.1],
          [900,39,1093.9,900,1095.7,10,-4,0,900,900,900,900]]}
        """));

    [Fact]
    public void Works_the_gap_out_from_the_rounded_figures_as_the_table_shows_them() => Assert.Equal(1110 - 1092, Ranked[2].Trend);

    [Fact]
    public void Ranks_every_club_in_the_world_and_in_its_league_equal_ratings_sharing_a_place()
    {
        var places = Clubs.Places(Ranked);
        Assert.Equal([1, 2, 3, 3], new[] { 157, 50, 42, 900 }.Select(t => places[t].World));
        Assert.Equal(new Place(2, 1, 2), places[50]);
        Assert.Equal(new Place(3, 2, 2), places[42]);
        Assert.Equal(new Place(3, null, null), places[900]);
    }

    [Fact]
    public void Colours_by_place_among_every_ranked_club()
    {
        var tier = Clubs.Tiers(Ranked, "lt");
        Assert.Equal(2, tier(1118.2));       // 1st of 4 is the top 25%: past the top 20%, inside the top half
        Assert.Equal(1, tier(1091.8));
    }

    [Theory]
    [InlineData(2.5, 3)]
    [InlineData(-2.5, -2)]
    [InlineData(1110.5, 1111)]
    public void Rounds_halves_up_as_the_browser_does(double x, int expected) => Assert.Equal(expected, Js.RoundInt(x));

    // ---- league.test.ts: sorting a table
    sealed record T(int Team, int Rank, int Gd, double? Xg);
    static readonly IReadOnlyDictionary<string, Leagues.Col<T>> Cols = new Dictionary<string, Leagues.Col<T>>
    {
        ["rank"] = new(1, r => r.Rank), ["gd"] = new(-1, r => r.Gd), ["xg90"] = new(-1, r => r.Xg),
    };

    [Fact]
    public void Sorts_best_first_reverses_on_a_second_press_and_puts_blanks_last()
    {
        var table = new List<T> { new(42, 1, 5, null), new(50, 2, 9, 2.1), new(51, 3, 12, 1.2) };
        Assert.Equal([51, 50, 42], Leagues.SortRows(table, Leagues.PickSort(Cols, "rank", "gd", false), Cols).Select(r => r.Team));
        Assert.Equal([42, 50, 51], Leagues.SortRows(table, Leagues.PickSort(Cols, "rank", "gd", true), Cols).Select(r => r.Team));
        Assert.Equal([50, 51, 42], Leagues.SortRows(table, Leagues.PickSort(Cols, "rank", "xg90", false), Cols).Select(r => r.Team));
        Assert.Equal(new Leagues.Sort("rank", 1), Leagues.PickSort(Cols, "rank", "nonsense", false));
    }

    [Fact]
    public void Names_crests_by_initials_and_ordinals_as_the_svelte_site_does()
    {
        Assert.Equal("MU", Markup.CrestInitials("Manchester United", true));
        Assert.Equal("BAY", Markup.CrestInitials("FC Bayern", true));
        Assert.Equal("ARS", Markup.CrestInitials("Arsenal", true));
        Assert.Equal(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st", "111th"],
            new[] { 1, 2, 3, 4, 11, 12, 13, 21, 22, 101, 111 }.Select(Markup.Ordinal));
        Assert.Equal("/nation/C%C3%B4te%20d'Ivoire", Menu.PageHref("nation", "Côte d'Ivoire"));
    }
}

// web/src/lib/cups.test.ts, for the C# site
public class CupTests
{
    static LeagueDoc Cup(string fixtures, string table = "[]") => JsonSerializer.Deserialize<LeagueDoc>($$"""
        {"fixture_fields":["id","kickoff","round","home","away","status","hg","ag","pen_h","pen_a"],"fixtures":{{fixtures}},
         "table_fields":["group","rank","team"],"table":{{table}}}
        """, Database.Json)!;

    [Fact]
    public void Puts_out_the_loser_of_a_finished_tie_and_keeps_a_tie_still_to_play() =>
        Assert.Equal([10, 12, 13], Cups.TeamsLeft(Cup("""[[1,"2026-09-01T19:00","Round 1",10,11,"FT",2,0,null,null],[2,"2026-09-01T19:00","Round 1",12,13,"NS",null,null,null,null]]""")).Order());

    [Fact]
    public void Settles_a_two_legged_tie_on_aggregate_then_on_penalties() =>
        Assert.Equal([11, 13], Cups.TeamsLeft(Cup("""[[1,"2026-09-01T19:00","Semi",10,11,"FT",1,0,null,null],[2,"2026-09-08T19:00","Semi",11,10,"FT",3,1,null,null],[3,"2026-09-01T19:00","Semi",12,13,"PEN",1,1,4,5]]""")).Order());

    [Fact]
    public void On_a_level_tie_with_no_shoot_out_recorded_keeps_the_club_that_plays_on()
    {
        var left = Cups.TeamsLeft(Cup("""[[1,"2026-09-01T19:00","Round 1",10,11,"FT",1,1,null,null],[2,"2026-09-20T19:00","Round 2",11,14,"NS",null,null,null,null]]"""));
        Assert.DoesNotContain(10, left);
        Assert.Contains(11, left);
    }

    [Fact]
    public void Ignores_a_match_that_was_called_off() =>
        Assert.Empty(Cups.TeamsLeft(Cup("""[[1,"2026-09-01T19:00","Round 1",10,11,"PST",null,null,null,null]]""")));

    [Fact]
    public void Puts_out_the_group_clubs_that_are_not_in_the_knockout_ties_that_follow() =>
        Assert.Equal([10, 12], Cups.TeamsLeft(Cup("""[[1,"2026-09-01T19:00","Group A",10,11,"FT",2,0,null,null],[2,"2026-10-01T19:00","Quarter-finals",10,12,"NS",null,null,null,null]]""")).Order());

    [Fact]
    public void A_european_cups_clubs_are_its_league_phase_once_there_is_a_table_everyone_drawn_before()
    {
        const string fx = """[[1,"2026-07-07T16:00","Qualifying",1,2,"FT",2,0,null,null]]""";
        Assert.Equal([85, 50], Cups.Entrants(Cup(fx, """[["UCL",1,85],["UCL",2,50]]""")));
        Assert.Equal([1, 2], Cups.Entrants(Cup(fx)));
    }
}

public class JsNumberTests
{
    // the browser's x.toFixed(n), which the pages' decimals follow
    [Theory]
    [InlineData(2.05, 1, "2.0")]
    [InlineData(1.25, 1, "1.3")]
    [InlineData(1.35, 1, "1.4")]
    [InlineData(0.45, 1, "0.5")]
    [InlineData(2.675, 2, "2.67")]
    [InlineData(0.15, 1, "0.1")]
    [InlineData(-1.25, 1, "-1.3")]
    [InlineData(-0.04, 1, "-0.0")]
    [InlineData(0, 2, "0.00")]
    [InlineData(1093.94, 1, "1093.9")]
    [InlineData(0.98141, 3, "0.981")]
    [InlineData(12, 0, "12")]
    public void Writes_decimals_as_the_browsers_toFixed_does(double x, int digits, string expected) => Assert.Equal(expected, Js.ToFixed(x, digits));
}
