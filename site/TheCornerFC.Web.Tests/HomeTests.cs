using System.Text.Json;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// Home's Stats slide (web/src/lib/server/home.ts homeStats): its figures from the last year's stats,
// worked out as JavaScript works them, a missing figure counting as nothing
public class HomeTests
{
    static StatsDoc Read(string json) => JsonSerializer.Deserialize<StatsDoc>(json, Database.Json)!;

    [Fact]
    public void The_stats_slide_gives_the_last_years_strongest_figures()
    {
        var s = Home.StatsOf(Read("""
            {"ranges":{"365d":{
              "all":{"n":1234,"live":1000,"rated":1200,"correct":0.524,"exact":0.105,"home_rate":0.441,"goal_error":0.873,
                "calibration":[[0,null,null],[50,0.15,0.12],[40,0.72,0.75],[10,0.85,null]]},
              "39":{"n":300,"live":300,"rated":300},"140":{"n":200,"live":200,"rated":200}}}}
            """))!;
        Assert.Equal("1,234", s.Matches);
        Assert.Equal([
            ("60%", "", "of the results the model gave 70% or more came in"),   // (40 × 0.75 + 10 × 0) ÷ 50
            ("52%", "", "right result, against 44% by picking the home team every time"),
            ("1 in 10", "", "exact scores right"),
            ("0.87", "", "goals off per team, on average"),
            ("11.2", " pts", "between the chance it gave and how often it happened"), // (50 × 0.03 + 40 × 0.03 + 10 × 0.85) ÷ 100 points
            ("2", "", "competitions marked"),
        ], s.Nums);
        Assert.Equal("1,000 recorded before kickoff, the rest reconstructed from pre-match data.", s.Note);
    }

    [Fact]
    public void A_year_with_no_matches_has_no_stats_slide_and_missing_figures_are_left_out()
    {
        Assert.Null(Home.StatsOf(null));
        Assert.Null(Home.StatsOf(Read("""{"ranges":{"365d":{"all":{"n":0,"live":0,"rated":0}}}}""")));
        var s = Home.StatsOf(Read("""{"ranges":{"365d":{"all":{"n":5,"live":5,"rated":5,"correct":0.6}}}}"""))!;
        Assert.Equal([("60%", "", "right result, against 0% by picking the home team every time")], s.Nums);
        Assert.Equal("", s.Note);
    }

    // Home's sample for subscribers: what was shown before kick-off for a match now played
    static readonly SiteDoc Site = JsonSerializer.Deserialize<SiteDoc>("""
        {"match_fields":["id","kickoff","league","home","away","status","hg","ag","p_home","p_draw","p_away","home_xg","away_xg","likely"],
         "generated_at":"2026-11-14T06:00:00+00:00","competitions":{},"teams":{"1":"Alpha","2":"Beta","3":"Gamma"}}
        """, Database.Json)!;
    static List<Data.Match> Rows(string matches, string reasons = "{}") =>
        ClubData.MatchRows(Site, JsonSerializer.Deserialize<MatchesAnswer>($$"""{"matches":{{matches}},"reasons":{{reasons}},"paywall":true}""", Database.Json)!);

    [Fact]
    public void The_subscribers_sample_is_the_latest_played_match_with_a_projected_score_and_reasons_whatever_the_result()
    {
        // Alpha's list: an older win the model called, then a newer defeat it didn't; Gamma's has the
        // same newer match and one still to come
        var alpha = Rows("""
            [[10,"2026-11-01T15:00:00+00:00",39,1,2,"FT",3,0,0.7,0.2,0.1,2.44,0.61,"2-0"],
             [11,"2026-11-08T15:00:00+00:00",39,1,3,"FT",0,2,0.62,0.22,0.16,2.06,0.94,"2-1"]]
            """, """{"10":[["strength",1.2],["home_advantage",0.3]],"11":[["strength",0.8],["home_advantage",0.3],["absences",-0.2],["tendencies",0.1]]}""");
        var gamma = Rows("""
            [[11,"2026-11-08T15:00:00+00:00",39,1,3,"FT",0,2,0.62,0.22,0.16,2.06,0.94,"2-1"],
             [12,"2026-11-22T15:00:00+00:00",39,3,2,"NS",null,null,0.5,0.25,0.25,null,null,null]]
            """, """{"11":[["strength",0.8],["home_advantage",0.3],["absences",-0.2],["tendencies",0.1]]}""");
        var s = Home.SampleOf(Site, new([alpha, gamma], true))!;
        Assert.Equal((11, "Alpha", "Gamma", "0–2"), (s.Id, s.HomeName, s.AwayName, s.Score));
        Assert.Equal((62, 22, 16), (s.H, s.D, s.A));
        Assert.Equal(("2.1–0.9", "2–1"), (s.Goals, s.Likely));      // (each score with the same dash)
        // the first three reasons, as a match card words them
        Assert.Equal([new Cards.Reason("Alpha rated the stronger side", "0.8 goals"), new Cards.Reason("Home advantage for Alpha", "0.3 goals"),
            new Cards.Reason("More of Alpha's regulars listed as missing", "0.2 goals")], s.Reasons);
    }

    [Fact]
    public void A_match_without_reasons_or_a_projected_score_isnt_the_sample_and_none_leaves_it_out()
    {
        // the newest has one reason only, the one before it no projected goals: the third is the sample
        var list = Rows("""
            [[20,"2026-10-18T15:00:00+00:00",39,1,2,"FT",1,1,0.5,0.3,0.2,1.5,1.1,"1-1"],
             [21,"2026-10-25T15:00:00+00:00",39,2,1,"FT",2,1,0.4,0.3,0.3,null,null,null],
             [22,"2026-11-01T15:00:00+00:00",39,1,3,"FT",4,0,0.6,0.2,0.2,2.0,1.0,"2-1"],
             [23,"2026-11-08T15:00:00+00:00",39,3,1,"PST",null,null,0.3,0.3,0.4,1.0,1.4,"1-1"]]
            """, """{"20":[["strength",0.4],["home_advantage",0.3]],"21":[["strength",0.4],["home_advantage",0.3]],"22":[["strength",1.0]]}""");
        Assert.Equal(20, Home.SampleOf(Site, new([list], true))!.Id);
        Assert.Null(Home.SampleOf(Site, new([list.Where(m => m.Id != 20).ToList()], true)));
        Assert.Null(Home.SampleOf(Site, new([], false)));
    }
}
