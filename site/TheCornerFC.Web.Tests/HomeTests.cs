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
}
