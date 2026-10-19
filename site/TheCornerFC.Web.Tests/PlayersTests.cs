using System.Text.Json;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/playerFilters.test.ts and players.test.ts, for the C# site: the same cases and the
// same answers
public class PlayersTests
{
    static T Read<T>(string json) => JsonSerializer.Deserialize<T>(json, Database.Json)!;
    static string Json(object o) => JsonSerializer.Serialize(o, Database.Json);
    static string N(PickRange r) => $"{r.Lo?.ToString() ?? "null"},{r.Hi?.ToString() ?? "null"}";

    static readonly PlayerFacets Facets = Read<PlayerFacets>("""
        {"players":5,"age":[16,42],"ability":[42,97],"minutes":1838,"positions":{"ST":3},
         "clubs":[[42,39],[33,39],[157,78],[900,40],[901,141]],"nats":["Spain","England","Côte d'Ivoire"]}
        """);

    [Fact]
    public void A_range_in_the_address_reads_both_ends_either_end_open_and_ignores_anything_else()
    {
        Assert.Equal("20,25", N(Players.ParseRange("20-25")));
        Assert.Equal("null,25", N(Players.ParseRange("-25")));
        Assert.Equal("20,null", N(Players.ParseRange("20-")));
        Assert.Equal("null,null", N(Players.ParseRange(null)));
        Assert.Equal("null,null", N(Players.ParseRange("abc")));
        Assert.Equal("null,null", N(Players.ParseRange("1;drop")));
        Assert.Equal("null,null", N(Players.ParseRange("٢٠-25"))); // (digits are 0 to 9 only, as JavaScript's \d)
    }

    [Fact]
    public void A_range_is_written_back_the_same_way_and_sent_as_whole_numbers()
    {
        Assert.Equal("20-", Players.RangeText(new(20, null)));
        Assert.Equal("19.5-24.2", Players.RangeText(new(19.5, 24.2)));
        Assert.Null(Players.RangeText(new(null, null)));
        Assert.Equal([20, 25], Players.RangeParam(new(19.2, 25.8)));
        Assert.Equal([null, 30], Players.RangeParam(new(null, 30)));
    }

    [Fact]
    public void Slider_stops_have_every_age_every_whole_Ability_and_minutes_a_match_at_a_time()
    {
        Assert.Equal(27, Players.RangeStops("age", Facets, 0).Count);
        Assert.Equal(42, Players.RangeStops("ab", Facets, 0)[0]);
        Assert.Equal(97, Players.RangeStops("ab", Facets, 0)[^1]);
        var mins = Players.RangeStops("mins", Facets, 0);
        Assert.Equal([0, 90, 180], mins.Take(3));
        Assert.Equal(1890, mins[^1]);
    }

    [Fact]
    public void Club_ranks_are_finer_at_the_top_and_end_on_the_number_of_ranked_clubs()
    {
        Assert.Equal([1, 5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 400, 500, 750, 1000, 1500, 2000, 2346], Players.RangeStops("crank", Facets, 2346));
        Assert.Equal([1, 5, 10, 20, 30, 50, 60], Players.RangeStops("crank", Facets, 60));
    }

    static readonly List<double> Stops = [1, 5, 10, 20, 50];

    [Fact]
    public void Handles_stand_on_the_nearest_stop_inside_a_range_from_a_link()
    {
        Assert.Equal(0, Players.StopIndex(Stops, null, 0));
        Assert.Equal(4, Players.StopIndex(Stops, null, 1));
        Assert.Equal(2, Players.StopIndex(Stops, 7, 0));
        Assert.Equal(1, Players.StopIndex(Stops, 7, 1));
        Assert.Equal(4, Players.StopIndex(Stops, 99, 0));
    }

    [Fact]
    public void Handles_at_either_end_leave_that_end_open_and_are_described_in_words()
    {
        Assert.Equal("null,null", N(Players.HandlesRange(Stops, 0, 4)));
        Assert.Equal("5,20", N(Players.HandlesRange(Stops, 1, 3)));
        Assert.Equal("null,10", N(Players.HandlesRange(Stops, 0, 2)));
        Assert.Equal("All", Players.RangeLabel("crank", Stops, 0, 4));
        Assert.Equal("Top 10", Players.RangeLabel("crank", Stops, 0, 2));
        Assert.Equal("10 down", Players.RangeLabel("crank", Stops, 2, 4));
        Assert.Equal("Up to 10", Players.RangeLabel("ab", Stops, 0, 2));
        Assert.Equal("10+", Players.RangeLabel("ab", Stops, 2, 4));
        Assert.Equal("5–20", Players.RangeLabel("mins", Stops, 1, 3));
        Assert.Equal("All ages", Players.RangeLabel("age", Stops, 0, 4));
        Assert.Equal("10", Players.RangeLabel("age", Stops, 2, 2));
        Assert.Equal("Top 1,500", Players.RangeLabel("crank", [1, 1500, 2000], 0, 1));
        // where each handle stands along its track
        Assert.Equal((25, 50), (Players.At(1, 4), Players.At(2, 4)));
        Assert.Equal(0, Players.At(0, 0));
    }

    [Fact]
    public void Picked_positions_become_the_groups_they_are_rated_in_and_a_player_his_best_of_them()
    {
        Assert.Equal(["FB", "ST"], Players.SelectedGroups(["LB", "RB", "ST"]));
        Assert.Empty(Players.SelectedGroups([]));
        Assert.Equal(95.5, Players.PosRank(new() { ["W"] = 95.5, ["AM"] = 87.5 }, ["AM", "W"]));
        Assert.Null(Players.PosRank(new() { ["W"] = 95.5 }, ["CB"]));
        Assert.Null(Players.PosRank(null, ["CB"]));
    }

    static readonly SiteDoc WhoSite = Read<SiteDoc>("""
        {"generated_at":"","competitions":{
          "39":{"name":"Premier League","country":"England","type":"League"},
          "40":{"name":"Championship","country":"England","type":"League"},
          "78":{"name":"Bundesliga","country":"Germany","type":"League"},
          "141":{"name":"Segunda División","country":"Spain","type":"League"}},
         "teams":{"42":"Arsenal","33":"Manchester United","157":"Bayern München","900":"Racing","901":"Racing"}}
        """);

    [Fact]
    public void The_club_box_adds_the_league_to_a_name_two_clubs_share_and_lists_leagues_in_the_menus_order()
    {
        var who = Players.Who(WhoSite, Facets, [new("England", [39, 40], null), new("Germany", [78], null)]);
        Assert.Equal(["Arsenal", "Bayern München", "Manchester United", "Racing (Championship)", "Racing (Segunda División)"], who.Clubs.Select(c => c.Name));
        Assert.Equal([39, 40, 78, 141], who.Leagues.Select(l => l.Id));
        Assert.Equal([42, 33], who.Leagues[0].Clubs);
        Assert.Equal(["Côte d'Ivoire", "England", "Spain"], who.Nats.Select(n => n.Name));
        // the keys match without accents
        Assert.Equal("cote d'ivoire", who.Nats[0].Key);
        Assert.Equal("bayern munchen", who.Clubs[1].Key);
    }

    // ---- players.test.ts
    static readonly SiteDoc Site = Read<SiteDoc>("""
        {"generated_at":"","competitions":{
          "2":{"name":"UEFA Champions League","country":"World","type":"Cup"},
          "39":{"name":"Premier League","country":"England","type":"League"},
          "78":{"name":"Bundesliga","country":"Germany","type":"League"},
          "307":{"name":"Pro League","country":"Saudi-Arabia","type":"League"}},
         "teams":{"33":"Manchester United","42":"Arsenal","157":"Bayern München","2932":"Al-Hilal"},
         "player_fields":["id","name","position","rank","team","league","seasons","season","ord"],
         "player_season_fields":["minutes","goals","assists"],
         "player_seasons":[2026,2025,2024],"player_future_seasons":[2027,2028]}
        """);
    const string Fields = """["team","league","current","st","lt","played","form","in_league","attack","defence","home","away"]""";
    static readonly List<Club> All = Clubs.From(Read<Rankings>($$"""
        {"fields":{{Fields}},"rankings":[[157,78,1100,1,1100,1,1,1,1,1,1,1],[42,39,1090,1,1090,1,1,1,1,1,1,1],[33,39,1040,1,1040,1,1,1,1,1,1,1],[2932,307,950,1,950,1,1,1,1,1,1,1]]}
        """));
    static readonly List<Country> Countries = ClubTable.Countries(Site, All);
    static readonly Dictionary<int, HashSet<int>> Cups = new() { [2] = [157, 42] };
    static readonly PlayerFacets AskFacets = Read<PlayerFacets>("""{"players":4,"age":[16,40],"ability":[40,97],"minutes":1800,"positions":{},"nats":[],"clubs":[[157,78],[42,39],[33,39],[2932,307]]}""");

    static Players.Choices Choose(string filter = "all", string[]? excluded = null, string search = "", string sort = "s2026",
        Dictionary<string, PickRange>? ranges = null, List<string>? positions = null, List<int>? clubs = null, List<string>? nats = null)
    {
        var all = new Dictionary<string, PickRange> { ["age"] = default, ["ab"] = default, ["crank"] = default, ["mins"] = default };
        foreach (var (k, v) in ranges ?? []) all[k] = v;
        var ex = excluded ?? [];
        return new(filter, ex.ToHashSet(), ex, search, sort, all, positions ?? [], clubs ?? [], nats ?? []);
    }
    static Dictionary<string, object?> Ask(Players.Choices ch) =>
        Players.ListParams(new(Site, All, Cups, AskFacets, Countries, false, ch, Players.SelectedGroups(ch.Positions)));

    static string Key(string? asked, bool open = true, List<string>? groups = null) =>
        Players.SortKey(asked, Site.PlayerSeasons!, Site.PlayerFutureSeasons!, open, groups ?? []);

    [Fact]
    public void The_sort_is_the_current_season_unless_age_goals_a_past_or_a_projected_season_is_asked_for()
    {
        Assert.Equal("s2026", Key(null));
        Assert.Equal("s2026", Key("nonsense"));
        Assert.Equal("s2026", Key("s1999"));
        Assert.Equal("s2026", Key("s"));
        Assert.Equal("age", Key("age"));
        Assert.Equal("ga", Key("ga"));
        Assert.Equal("s2024", Key("s2024"));
        Assert.Equal("f2028", Key("f2028"));
        // the position rank takes Ability's place while positions are picked
        Assert.Equal("pos", Key(null, groups: ["ST"]));
        Assert.Equal("pos", Key("s2026", groups: ["ST"]));
        Assert.Equal("s2024", Key("s2024", groups: ["ST"]));
        Assert.Equal("age", Key("age", false, ["ST"]));
        Assert.Equal("s2026", Key("pos"));
        // a closed season column can't be sorted on
        Assert.Equal("s2026", Key("s2024", false));
        Assert.Equal("age", Key("age", false));
    }

    [Fact]
    public void The_list_asks_for_everyone_by_default_or_a_league_a_country_or_a_cups_clubs()
    {
        Assert.Equal("""{"p_sort":"s0"}""", Json(Ask(Choose())));
        Assert.Equal("[39]", Json(Ask(Choose("39"))["p_leagues"]!));
        Assert.Equal("[78]", Json(Ask(Choose("c:Germany"))["p_leagues"]!));
        Assert.Equal("[157,42]", Json(((List<int>)Ask(Choose("e:2"))["p_teams"]!).Order().Reverse()));
        Assert.Equal("[39]", Json(Ask(Choose(excluded: ["England"]))["p_not_leagues"]!));
        Assert.Equal("[307]", Json(Ask(Choose(excluded: ["r:Asia"]))["p_not_leagues"]!));
    }

    [Fact]
    public void Seasons_go_to_the_database_by_their_place_newest_first()
    {
        Assert.Equal("s2", Ask(Choose(sort: "s2024"))["p_sort"]);
        Assert.Equal("f1", Ask(Choose(sort: "f2028"))["p_sort"]);
        Assert.Equal("age", Ask(Choose(sort: "age"))["p_sort"]);
    }

    [Fact]
    public void The_side_filters_go_too_and_a_picked_club_shows_whatever_league_is_selected()
    {
        Assert.Equal("""{"p_age":[null,21],"p_crank":[null,50],"p_sort":"s0"}""",
            Json(Ask(Choose(ranges: new() { ["age"] = new(null, 21), ["crank"] = new(null, 50) }))));
        Assert.Equal("""{"p_positions":["LB","RB"],"p_nats":["Spain"],"p_sort":"s0"}""", Json(Ask(Choose(positions: ["LB", "RB"], nats: ["Spain"]))));
        var p = Ask(Choose("78", ["England"], clubs: [42]));
        Assert.Equal("[42]", Json(p["p_teams"]!));
        Assert.False(p.ContainsKey("p_leagues"));
        Assert.False(p.ContainsKey("p_not_leagues"));
        Assert.Equal("""{"p_positions":["LB","ST"],"p_sort":"pos","p_groups":["FB","ST"]}""", Json(Ask(Choose(positions: ["LB", "ST"], sort: "pos"))));
    }

    [Fact]
    public void A_search_looks_at_every_player_and_finds_the_clubs_each_word_fits()
    {
        var p = Ask(Choose("78", ["England"], " Man Utd "));
        Assert.False(p.ContainsKey("p_leagues"));
        Assert.False(p.ContainsKey("p_not_leagues"));
        Assert.Equal("man utd", p["p_q"]);
        Assert.Equal(["man|0|33", "utd|0|33"], (List<string>)p["p_words"]!);
        Assert.Equal(["epl|0|42,33"], Players.SearchParams(Site, All, AskFacets, "epl").Words);
        Assert.Equal(["munich|0|157"], Players.SearchParams(Site, All, AskFacets, "munich").Words);
        Assert.Equal(["yamal|0|"], Players.SearchParams(Site, All, AskFacets, "yamal").Words);
    }

    [Fact]
    public void The_menus_numbers_are_asked_for_with_the_exclusions_and_added_up_for_each_choice()
    {
        Assert.Equal("""{"p_count":true}""", Json(Players.CountParams(Site, Choose())));
        Assert.Equal("""{"p_not_leagues":[78],"p_count":true}""", Json(Players.CountParams(Site, Choose(excluded: ["Germany"]))));
        Assert.Equal("""{"p_positions":["ST"],"p_nats":["Spain"],"p_count":true}""", Json(Players.CountParams(Site, Choose(positions: ["ST"], nats: ["Spain"]))));
        var countOf = Players.Counts([[39, 42, 25], [39, 33, 24], [78, 157, 26], [307, 2932, 20], [null, null, 3]], Countries, Cups);
        Assert.Equal(98, countOf("all"));
        Assert.Equal(49, countOf("39"));
        Assert.Equal(26, countOf("c:Germany"));
        Assert.Equal(20, countOf("r:Asia"));
        Assert.Equal(51, countOf("e:2"));
    }

    [Fact]
    public void A_season_tip_names_his_clubs_from_his_file_or_the_sites_names()
    {
        var doc = Read<PlayerDoc>("""
            {"id":7,"season_fields":[],"seasons":[],"match_fields":[],"matches":[],
             "spell_fields":["team","minutes","club_rank","goals","assists"],
             "spells":{"2026":[[42,530,63.5,6,0],[999,null,null,null,null]]},"teams":{"999":"Somewhere FC"}}
            """);
        Assert.Equal("""{"2026":[["Arsenal",63.5,530,6,0],["Somewhere FC",null,0,0,0]]}""", Json(Players.SeasonSpells(Site, doc)));
        Assert.Equal("{}", Json(Players.SeasonSpells(Site, null)));
    }
}
