using System.Text.Json;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Tests;

// web/src/lib/matchday.test.ts, lineups.test.ts and matchDetail.test.ts, for the C# site: the same
// cases and the same answers
public class MatchTests
{
    static T Read<T>(string json) => JsonSerializer.Deserialize<T>(json, Database.Json)!;
    static string Iso(DateTimeOffset t) => t.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'");

    static Match Mk(int id, string kickoff = "2026-10-10T14:00:00+00:00", string? round = null, string status = "NS", int? hg = null, int intl = 0,
        double? pHome = null, double? pDraw = null, double? mHome = null, double? mDraw = null, double? homeXg = null, double? awayXg = null,
        double? homeXi = null, double? awayXi = null, double? homeMissing = null, double? awayMissing = null,
        double? homeRecentXi = null, double? awayRecentXi = null, double? pOver25 = null, double? pBtts = null) =>
        new(id, kickoff, 39, round, 1, 2, status, hg, null, null, null, pHome, pDraw, null, homeXg, awayXg, null, null, null, null,
            homeXi, awayXi, homeMissing, awayMissing, null, null, null, null, null, null, mHome, mDraw, intl, [],
            homeRecentXi, awayRecentXi, pOver25, pBtts);

    // ---- days in a time zone
    [Fact]
    public void A_late_kick_off_falls_on_the_visitors_own_day_and_a_day_starts_at_their_midnight()
    {
        Assert.Equal("2026-10-11", Matchday.LocalDay(DateTimeOffset.Parse("2026-10-10T23:30:00+00:00"), "Europe/London")); // summer time
        Assert.Equal("2026-10-10", Matchday.LocalDay(DateTimeOffset.Parse("2026-10-10T23:30:00+00:00"), "America/New_York"));
        Assert.Equal("2026-10-09", Matchday.LocalDay(DateTimeOffset.Parse("2026-10-10T02:00:00+00:00"), "America/Los_Angeles"));
        Assert.Equal("2026-10-09T23:00:00.000Z", Iso(Matchday.DayStart("2026-10-10", "Europe/London")));
        Assert.Equal("2026-12-10T00:00:00.000Z", Iso(Matchday.DayStart("2026-12-10", "Europe/London")));
        Assert.Equal("2026-10-24T23:00:00.000Z", Iso(Matchday.DayStart("2026-10-25", "Europe/London"))); // clocks go back that night
        Assert.Equal("2026-10-26T00:00:00.000Z", Iso(Matchday.DayStart("2026-10-26", "Europe/London")));
        Assert.Equal("2026-10-09T15:00:00.000Z", Iso(Matchday.DayStart("2026-10-10", "Asia/Tokyo")));
        Assert.Equal("2026-10-10T04:00:00.000Z", Iso(Matchday.DayStart("2026-10-10", "America/New_York")));
    }

    [Fact]
    public void Days_step_and_are_named_and_an_address_day_is_read_as_JavaScript_reads_it()
    {
        Assert.Equal("2026-11-01", Matchday.AddDays("2026-10-31", 1));
        Assert.Equal("2026-02-28", Matchday.AddDays("2026-03-01", -1));
        Assert.Equal("Sat 10 Oct", Matchday.DayName("2026-10-10"));
        Assert.True(Matchday.IsDay("2026-10-10"));
        foreach (var d in new[] { null, "", "2026-13-45", "10/10/2026", "2026-10-10'", "2026-00-10" }) Assert.False(Matchday.IsDay(d), d);
        // (30 February runs on into March, as in the browser)
        Assert.True(Matchday.IsDay("2026-02-30"));
        Assert.Equal("Mon 2 Mar", Matchday.DayName("2026-02-30"));
    }

    static readonly MatchDays Md = Read<MatchDays>("""{"days":[["2026-10-08",39,2],["2026-10-10",39,5],["2026-10-10",78,3],["2026-10-12",5,4]],"leagues":[39,78,5],"intl":[[5,4]]}""");

    [Fact]
    public void The_page_opens_on_today_when_something_is_on_else_the_next_day_with_matches_else_the_last()
    {
        Assert.Equal("2026-10-10", Matchday.DefaultDay(Md, "2026-10-10"));
        Assert.Equal("2026-10-10", Matchday.DefaultDay(Md, "2026-10-09"));
        Assert.Equal("2026-10-12", Matchday.DefaultDay(Md, "2026-11-01"));
        Assert.Equal(["2026-10-10"], Matchday.DaysWith(Md, [78]));
        Assert.Equal(["2026-10-08", "2026-10-10", "2026-10-12"], Matchday.DaysWith(Md, null));
    }

    static readonly SiteDoc Site = Read<SiteDoc>("""
        {"generated_at":"","teams":{},"competitions":{
          "2":{"name":"UEFA Champions League","country":"World","type":"Cup"},"5":{"name":"UEFA Nations League","country":"World","type":"International"},
          "39":{"name":"Premier League","country":"England","type":"League"},"45":{"name":"FA Cup","country":"England","type":"Cup"},
          "40":{"name":"Championship","country":"England","type":"League"},"113":{"name":"Allsvenskan","country":"Sweden","type":"League"}}}
        """);

    [Fact]
    public void The_menu_puts_leagues_before_cups_under_each_country_and_knows_its_own_choices()
    {
        var countries = Matchday.CompCountries(Site, [45, 40, 39, 113, 2, 5, 9999]);
        Assert.Equal([("England", "39,40,45", (string?)null), ("Sweden", "113", "Scandinavia")], countries.Select(c => (c.Name, string.Join(',', c.Leagues), c.Region)));
        foreach (var f in new[] { "all", "39", "c:England", "r:Scandinavia", "e:all", "e:2", "i:all", "i:5" }) Assert.True(Matchday.KnownFilter(f, Site, countries), f);
        foreach (var f in new[] { null, "777", "c:Narnia", "k:45", "e:777", "x" }) Assert.False(Matchday.KnownFilter(f, Site, countries), f);
        Assert.Null(Matchday.FilterComps("all", countries, [5]));
        Assert.Equal([39, 40, 45], Matchday.FilterComps("c:England", countries, [5]));
        Assert.Equal([5], Matchday.FilterComps("i:all", countries, [5]));
        Assert.Equal([2], Matchday.FilterComps("e:2", countries, [5]));
        Assert.Equal(39, Matchday.SingleComp("39"));
        Assert.Equal(2, Matchday.SingleComp("e:2"));
        Assert.Equal(5, Matchday.SingleComp("i:5"));
        foreach (var f in new[] { "all", "c:England", "e:all", "r:Scandinavia" }) Assert.Null(Matchday.SingleComp(f));
    }

    static readonly List<Matchday.Round> Rounds = Matchday.MatchRounds([
        Mk(1, "2026-10-03T14:00:00+00:00", "Regular Season - 7", "FT"), Mk(2, "2026-10-04T14:00:00+00:00", "Regular Season - 7", "FT"),
        Mk(3, "2026-11-20T19:00:00+00:00", "Regular Season - 7"), // rearranged: outside its round's window
        Mk(4, "2026-10-17T14:00:00+00:00", "Regular Season - 8"), Mk(5, "2026-10-18T14:00:00+00:00", "Regular Season - 8", "PST"),
        Mk(6, "2026-10-24T14:00:00+00:00", "Regular Season - 9"),
    ], "Europe/London");

    [Fact]
    public void Rounds_are_in_date_order_leave_a_postponed_match_out_and_dont_wait_for_a_rearranged_one()
    {
        Assert.Equal(["Round 7", "Round 8", "Round 9"], Rounds.Select(r => r.Label));
        Assert.Equal("3 Oct – 4 Oct", Matchday.RoundDates(Rounds[0], "Europe/London"));
        Assert.Equal("24 Oct", Matchday.RoundDates(Rounds[2], "Europe/London"));
        Assert.Equal([4], Rounds[1].Matches.Select(m => m.Id));
        Assert.False(Rounds[0].Pending);
        Assert.True(Rounds[1].Pending);
    }

    [Fact]
    public void A_round_opens_on_the_one_on_now_or_next_up_or_the_one_on_a_day_asked_for_and_a_group_stage_goes_by_week()
    {
        Assert.Equal("Round 8", Matchday.PickRound(Rounds, null, "Europe/London")!.Label);
        Assert.Equal("Round 7", Matchday.PickRound(Rounds, "2026-10-04", "Europe/London")!.Label);
        Assert.Equal("Round 9", Matchday.PickRound(Rounds, "2026-10-20", "Europe/London")!.Label);
        Assert.Equal("Round 8", Matchday.PickRound(Rounds, "2027-01-01", "Europe/London")!.Label);
        Assert.Null(Matchday.PickRound([], null, "Europe/London"));
        var g = Matchday.MatchRounds([Mk(1, "2026-09-15T19:00:00+00:00", "Group A - 1"), Mk(2, "2026-09-17T19:00:00+00:00", "Group B - 1"), Mk(3, "2026-09-29T19:00:00+00:00", "Group A - 2")], "Europe/London");
        Assert.Equal([("w:2026-09-14", "Group stage", 2), ("w:2026-09-28", "Group stage", 1)], g.Select(r => (r.Key, r.Label, r.Matches.Count)));
    }

    // ---- line-ups
    static Lineups.Starter Starter(int id, string label) => new(id, $"A. Player{id}", label, 70);
    static Lineups.XiRow Row(int pid, string name, string? role, double? rank) => new(pid, name, role, rank);

    [Fact]
    public void A_finished_XI_is_marked_against_the_prediction_each_miss_paired_with_the_nearest_pick_who_didnt_start()
    {
        var (xi, hits) = Lineups.MarkPredicted([Starter(1, "GK"), Starter(2, "CB"), Starter(3, "ST")], [Row(1, "A", "GK", 80), Row(2, "B", "CB", 75), Row(9, "C", "ST", 70)]);
        Assert.Equal(2, hits);
        Assert.Equal([true, true, false], xi.Select(c => c.Predicted == true));
        var (paired, none) = Lineups.MarkPredicted([Starter(1, "LB"), Starter(2, "CM"), Starter(3, "ST"), Starter(4, "GK")],
            [Row(11, "Same", "ST", 60), Row(12, "Group", "RB", 61), Row(13, "Line", "AM", 62), Row(14, "Anyone", "CB", 63)]);
        Assert.Equal(0, none);
        Assert.Equal(["Group", "Line", "Same", "Anyone"], paired.Select(c => c.Instead?.Name));
        var (alone, _) = Lineups.MarkPredicted([Starter(1, "GK"), Starter(2, "CB")], [Row(1, "A", "GK", 80)]);
        Assert.False(alone[1].Predicted);
        Assert.Null(alone[1].Instead);
    }

    [Fact]
    public void Each_spot_says_what_happened_to_its_starter_in_words()
    {
        var (xi, _) = Lineups.MarkPredicted([Starter(1, "GK"), Starter(3, "ST")], [Row(1, "A", "GK", 80), Row(9, "J. Other", "ST", 71.26)]);
        var s = Lineups.Spots(xi).OrderBy(x => x.Y).ToList();
        Assert.Equal("A. Player1 · GK · rank 70.0 · predicted to start", s[0].Tip);
        Assert.Equal("A. Player3 · ST · rank 70.0 · not predicted; the model picked J. Other (rank 71.3)", s[1].Tip);
        Assert.Equal(("Other", (double?)71.26), s[1].Instead);
        Assert.Equal("Player1", s[0].Name);
        Assert.Equal("A. Keeper · GK", Lineups.Spots([new(1, "A. Keeper", "GK", null)], false)[0].Tip);
        var p = Lineups.Spots([new(1, "A. Keeper", "GK", 80.5, 97.6, 88)])[0];
        Assert.Equal((98, (double?)88, (bool?)null, "A. Keeper · GK · rank 80.5 · 98% to start · 88′ expected"), (p.Chance, p.Mins, p.Predicted, p.Tip));
    }

    static Player P(int id, double? rank, Dictionary<string, double>? ranks) => new(id, "X", null, rank, null, null, ranks, null, null, false);

    [Fact]
    public void A_predicted_starter_shows_his_rank_in_the_position_he_is_picked_in_else_his_Ability_else_none()
    {
        var players = new Dictionary<int, Player> { [1] = P(1, 95, new() { ["ST"] = 95, ["W"] = 81.4 }), [2] = P(2, 77, new() { ["FB"] = 77 }) };
        // a full-back with no wing-back rank is shown there on his full-back one, as on the club's page
        Assert.Equal([81.4, 77], Lineups.WithSlotRank([Row(1, "Striker", "LW", 94.2), Row(2, "Full-back", "RWB", 70)], players).Select(r => r.Rank));
        var more = new Dictionary<int, Player> { [1] = P(1, 84.3, new() { ["W"] = 86 }), [2] = P(2, null, null), [4] = P(4, 82, null) };
        Assert.Equal([84.3, null, null, 82], Lineups.WithSlotRank([Row(1, "A", "AM", 94.2), Row(2, "B", "ST", 64), Row(3, "C", "GK", 87), Row(4, "D", "GK", 80)], more).Select(r => r.Rank));
        Assert.Equal(77, Lineups.AverageRank([84.3, 70, null, 77.2]));
        Assert.Null(Lineups.AverageRank([null]));
        Assert.Null(Lineups.AverageRank([]));
    }

    // ---- a match's model detail
    static readonly Match M = Mk(1, pHome: 0.62, pDraw: 0.213, mHome: 0.684, mDraw: 0.196, homeXg: 1.9, awayXg: 0.8, pOver25: 0.55, pBtts: 0.46,
        homeXi: 88.4, awayXi: 79.6, homeRecentXi: 87, awayRecentXi: 80, homeMissing: 0.4, awayMissing: 1.2);
    const string WhyJson = """
        {"fallback":[false,true],"current":[1094,1025],"baseline":[1096,1017],"match":[1095,1021],
         "margin":{"strength":0.74,"home_advantage":0.3,"absences":-0.02},"exp_diff":1.02,"league_goals":2.9,"tendencies":-0.12,
         "missing":[0.4,1.2],"lines":[[90,88,89,87],[80,79,81,78]],"captured_at":"2026-10-07T10:24:16+00:00","source":"prospective",
         "injuries_at":"2026-10-07T09:54:25+00:00","odds_at":null,"model":"abcdef0123456789"
        """;
    static readonly Why TheWhy = Read<Why>(WhyJson + "}");
    static readonly DetailAnswer.Version Version = new("match-prediction", "c355108");

    static MatchDetail.Section Sec(MatchDetail.Detail d, string title) => d.Sections.First(s => s.Title == title);
    static object? Val(MatchDetail.Detail d, string title, string label) => d.Sections.FirstOrDefault(s => s.Title == title)?.Rows.FirstOrDefault(r => r.Label == label)?.Value;

    [Fact]
    public void The_detail_sets_out_strengths_the_margin_goals_absences_line_ups_and_the_market()
    {
        var d = MatchDetail.Of(M, TheWhy, Version, "Arsenal", "Leeds");
        Assert.Equal("1,094 · 1,025", Val(d, "Strength", "Current Strength"));
        Assert.Equal("No rating history yet for Leeds: the competition's starting strength was used.", Sec(d, "Strength").Note);
        Assert.Equal([("Strength gap", "+0.7"), ("Home advantage", "+0.3"), ("Known absences", "≈0"), ("Total", "+1.0")], Sec(d, "Expected margin").Rows.Select(r => (r.Label, (string)r.Value)));
        Assert.Equal("goals, + favours home", Sec(d, "Expected margin").Unit);
        Assert.Equal("2.7", Val(d, "Goals", "Projected total"));
        Assert.Equal("55% · 46%", Val(d, "Goals", "Over 2.5 · both score"));
        Assert.Equal("0.4 · 1.2", Val(d, "Known absences", "Missing players"));
        Assert.Equal("88 · 80", Val(d, "Predicted line-ups", "Predicted XI rating"));
        Assert.Equal("89 · 81", Val(d, "Predicted line-ups", "Model input, MID"));
        Assert.Equal("62 · 21 · 17%", Val(d, "Model vs market", "Model"));
        Assert.Equal("−6 · +1 · +5 pts", Val(d, "Model vs market", "Difference"));
        Assert.Equal(new MatchDetail.When("2026-10-07T10:24:16+00:00"), Val(d, "Data", "Model inputs"));
        Assert.Equal(["Model inputs", "Injury list seen", "Model version"], Sec(d, "Data").Rows.Select(r => r.Label));
        Assert.Equal("match-prediction · c355108", Val(d, "Data", "Model version"));
        Assert.Single(d.Notes);
    }

    [Fact]
    public void Without_a_stored_explanation_the_detail_says_so_and_a_finished_or_national_match_is_named_as_such()
    {
        var bare = MatchDetail.Of(M, null, null, "Arsenal", "Leeds");
        Assert.StartsWith("No breakdown", bare.Notes[0]);
        Assert.Equal(["Goals", "Known absences", "Predicted line-ups", "Model vs market"], bare.Sections.Select(s => s.Title));
        Assert.Contains(MatchDetail.Of(M with { Status = "FT", Hg = 2 }, null, null, "A", "B").Sections, s => s.Title == "Line-ups");
        var intl = MatchDetail.Of(M with { Intl = 1 }, TheWhy, Version, "England", "Wales");
        Assert.Contains("national team", Sec(intl, "Expected margin").Rows[1].Tip);
        Assert.Equal("Two level sides", Sec(intl, "Goals").Rows[0].Label);
    }

    [Fact]
    public void The_detail_works_through_the_steps_from_goals_records_to_chances_with_the_weights_used()
    {
        const string steps = """
            ,"steps":{"now_share":0.6,"record":[[1.67,1.03,17],[1.1,1.5,16]],"league":[1.5,1.2],"shrunk":[1.62,1.39,1.13,1.12],"plain":[1.51,1.13],
             "open_total":2.81,"base":[1.6,1.2],"scale":1.123,"xg":[1.8,1.07],"poisson":[0.52,0.24,0.24],"boost":1.051,"chances":[0.508,0.252,0.24],"likely":"1-1",
             "weights":{"now":[0.6,0.2],"shrink":6,"open":0.75,"draw":[1.1,1.5],"absence":0.1,"line":0.005}}}
            """;
        var d = MatchDetail.Of(M, Read<Why>(WhyJson + steps), Version, "Arsenal", "Leeds");
        Assert.Equal(["Strength", "Expected margin", "Each side's usual goals", "How open the game is", "Projected goals", "Chances"], d.Sections.Take(6).Select(s => s.Title));
        Assert.Equal("60% Current · 40% Baseline", Val(d, "Strength", "Blend"));
        Assert.Equal("(1.62 + 1.39) ÷ 2 = 1.51", Val(d, "Each side's usual goals", "Home goals, Arsenal"));
        Assert.Contains("counts 6 games", Sec(d, "Each side's usual goals").Note);
        Assert.Equal("25% × 2.64 + 75% × 2.81 = 2.80", Val(d, "How open the game is", "Blended"));
        Assert.Equal("1.60 × 1.123 · 1.20 ÷ 1.123", Val(d, "Projected goals", "Scaled"));
        Assert.Equal("52 · 24 · 24%", Val(d, "Chances", "From the projected goals"));
        Assert.Equal("51 · 25 · 24%", Val(d, "Chances", "Final chances"));
        Assert.Equal("× 1.051", Val(d, "Chances", "Draw boost"));
        Assert.Contains("Up to × 1.1 in a close game, none once the projected margin reaches 1.5 goals", Sec(d, "Chances").Rows[1].Tip);
        var plain = MatchDetail.Of(M, Read<Why>(WhyJson + steps.Replace("\"open_total\":2.81", "\"open_total\":null").Replace("\"now_share\":0.6", "\"now_share\":null")), Version, "Arsenal", "Leeds");
        Assert.DoesNotContain(plain.Sections, s => s.Title == "How open the game is");
        Assert.DoesNotContain(Sec(plain, "Strength").Rows, r => r.Label == "Blend");
    }
}
