using System.Text.Json;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/lineupRecord.test.ts, for the C# site: the same cases and the same answers
public class LineupRecordTests
{
    static T Read<T>(string json) => JsonSerializer.Deserialize<T>(json, Database.Json)!;
    const string Fields = """["fixture","kickoff","league","team","opponent","home","correct","roles_right","roles_known","lines","hours_before","version","missed","wrong"]""";
    const string Rows = """
        [1,"2026-10-03T14:00:00+00:00",39,42,50,1,11,10,11,[1,1,4,4,3,3,3,3],0.5,0,[],[]],
        [1,"2026-10-03T14:00:00+00:00",39,50,42,0,9,8,9,[1,1,4,3,3,3,3,2],0.5,0,[7,8],[70,80]],
        [2,"2026-10-05T19:00:00+00:00",40,63,64,1,8,6,8,[1,1,4,3,3,2,3,2],30,1,[7,9,10],[70,90,91]],
        [3,"2026-10-06T23:30:00+00:00",39,50,33,1,10,9,10,[1,1,4,4,3,3,3,2],3,1,[7],[70]]
        """;
    static readonly LiveDoc Doc = Read<LiveDoc>($$"""{"fields":{{Fields}},"versions":[{"name":"a"},{"name":"b"}],"excluded_no_official_xi":2,"rows":[{{Rows}}]}""");
    static readonly List<LineupRecord.LiveRow> All = LineupRecord.LiveRows(Doc);
    static LineupRecord.Summary Sum(int? days = null, List<int>? ids = null, double shown = 50) =>
        LineupRecord.LiveSummary(Doc, All, days, ids, "Europe/London", shown, DateTimeOffset.Parse("2026-10-08T00:00:00Z"));

    [Fact]
    public void The_live_record_totals_the_line_ups_the_starters_named_and_the_perfect_XIs()
    {
        var s = Sum();
        Assert.Equal((true, 4, 38, 1, 33, (int?)38, 3, 2), (s.Any, s.N, s.Correct, s.Perfect, s.RolesRight, s.RolesKnown, s.Matches, s.Excluded));
        Assert.Equal(1, s.Counts[11]);
        Assert.Equal(1, s.Counts[9]);
    }

    [Fact]
    public void A_late_kick_off_falls_on_the_visitors_day_and_a_short_record_counts_by_day()
    {
        var s = Sum();
        Assert.Equal("2026-10-03", s.First);
        Assert.Equal("2026-10-07", s.Last); // 23:30 UTC is past midnight in UK summer time
        Assert.Equal("day", s.Step);
        Assert.Equal([new("2026-10-07", 1, 10, 0), new("2026-10-05", 1, 8, 0), new LineupRecord.TrendPoint("2026-10-03", 2, 20, 1)], s.Trend);
    }

    [Fact]
    public void The_four_lines_add_up_and_each_line_up_is_timed_before_kick_off()
    {
        var s = Sum();
        Assert.Equal([4, 4, 16, 14, 12, 11, 12, 9], s.Lines);
        Assert.Equal([("Under 1 hour", 2, 20, 1), ("1–6 hours", 1, 10, 0), ("6–24 hours", 0, 0, 0), ("24 hours or more", 1, 8, 0)], s.Timing!);
    }

    [Fact]
    public void Line_ups_group_by_competition_club_and_model_version()
    {
        var s = Sum();
        Assert.Equal(new LineupRecord.Group(39, 3, 30, 1, 27, 30), s.Comps.First(c => c.Key == 39));
        Assert.Equal((50, 2, 19), s.Clubs.First(c => c.Key == 50) is var c ? (c.Key, c.N, c.Correct) : default);
        Assert.Equal([(0, 2), (1, 2)], s.Versions!.Select(v => (v.Key, v.N)));
    }

    [Fact]
    public void The_players_it_got_wrong_twice_or_more_are_listed_with_their_club()
    {
        var s = Sum();
        Assert.Equal([new LineupRecord.Tally(7, 50, 3)], s.Missed);
        Assert.Equal([new LineupRecord.Tally(70, 50, 3)], s.Wrong);
        Assert.Equal(6, s.MissedTotal);
    }

    [Fact]
    public void The_line_ups_are_listed_newest_first_and_narrow_to_a_range_and_competitions()
    {
        Assert.Equal([50, 63], Sum(shown: 2).Rows.Select(r => r.Team));
        Assert.Equal(2, Sum(3).N);
        Assert.Equal(1, Sum(ids: [40]).N);
        Assert.Equal((true, 0), Sum(ids: [999]) is var e ? (e.Any, e.N) : default);
    }

    [Fact]
    public void A_record_longer_than_four_weeks_counts_by_week()
    {
        var longDoc = Read<LiveDoc>($$"""{"fields":{{Fields}},"versions":[],"rows":[[9,"2026-08-01T14:00:00+00:00",39,42,50,1,7,5,7,[1,1,4,2,3,2,3,2],2,0,[],[]],{{Rows}}]}""");
        var l = LineupRecord.LiveSummary(longDoc, LineupRecord.LiveRows(longDoc), null, null, "Europe/London", 50, DateTimeOffset.Parse("2026-10-08T00:00:00Z"));
        Assert.Equal("week", l.Step);
        Assert.Equal("2026-10-05", l.Trend[0].Day); // the Monday of the latest week
    }

    [Fact]
    public void The_reconstructed_history_is_the_databases_answer_in_the_same_shape()
    {
        var s = LineupRecord.HistorySummary(Read<HistorySummaryDoc>("""
            {"any":true,"total":818,"correct":6285,"perfect":40,"roles_right":4821,"roles_known":6073,"matches":435,"first":"2026-09-08","last":"2026-10-07",
             "counts":{"9":184,"11":40},"step":"week","trend":[["2026-10-05",21,60,0]],"lines":[1,1,1,1,1,1,1,1],"comps":[],"clubs":[],"missed":[],"wrong":[],"missed_total":2713,
             "rows":[["2026-10-07",1607,1603,1,253,8,[22235]]]}
            """));
        Assert.Equal((818, 6285, (int?)6073, "2026-09-08", 2713), (s.N, s.Correct, s.RolesKnown, s.First, s.MissedTotal));
        Assert.Equal(12, s.Counts.Length);
        Assert.Equal(184, s.Counts[9]);
        Assert.Equal(("2026-10-07", 1607, 1603, true, 253, 8, 22235), s.Rows[0] is var r ? (r.Day, r.Team, r.Opponent, r.Home, r.League, r.Correct, r.Missed[0]) : default);
        // a range with nothing in it comes back with its sums empty
        Assert.Equal((false, 0), LineupRecord.HistorySummary(Read<HistorySummaryDoc>("""{"any":false,"total":null,"leagues":[2],"scope":{}}""")) is var e ? (e.Any, e.N) : default);
    }

    static LineupRecord.Group Club(int id, int n, int correct) => new(id, n, correct, 0, null, null);

    [Fact]
    public void The_easiest_and_hardest_clubs_need_enough_clubs_with_enough_line_ups()
    {
        Assert.Null(LineupRecord.ClubExtremes([Club(1, 3, 30), Club(2, 3, 20), Club(3, 2, 22)]));
        var x = LineupRecord.ClubExtremes([Club(1, 3, 33), Club(2, 3, 30), Club(3, 4, 36), Club(4, 3, 21), Club(5, 5, 30), Club(6, 3, 15), Club(7, 1, 11)])!.Value;
        Assert.Equal([1, 2, 3], x.Easiest.Select(c => c.Key));
        Assert.Equal([6, 5, 4], x.Hardest.Select(c => c.Key));
        Assert.Equal("9.5 of 11", LineupRecord.Of11(9.512));
        Assert.Equal("4.9%", LineupRecord.ShareText(40, 818));
        Assert.Equal("–", LineupRecord.ShareText(1, 0));
    }
}
