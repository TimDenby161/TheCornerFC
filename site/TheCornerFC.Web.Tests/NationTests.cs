using System.Text.Json;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/nation.test.ts, for the C# site: the same cases and the same answers
public class NationTests
{
    static T Read<T>(string json) => JsonSerializer.Deserialize<T>(json, Database.Json)!;

    static readonly NationsDoc Ranking = Read<NationsDoc>("""
        {"latest_match":"2026-10-06","matches":3,"aliases":{"South Korea":["Korea Republic"]},
         "nations":[{"name":"Spain","current":1400},{"name":"England","current":1361},{"name":"South Korea","current":1100},{"name":"Malta","current":700}]}
        """);

    [Fact]
    public void The_ranking_finds_a_nation_by_its_own_name_or_the_feeds_and_colours_its_rating()
    {
        Assert.Equal("South Korea", Nation.For(Ranking, "Korea Republic")?.Name);
        Assert.Equal("England", Nation.For(Ranking, "England")?.Name);
        Assert.Null(Nation.For(Ranking, "Atlantis"));
        Assert.Equal(2, Ranking.Tier(1400)); // 1st of 4: the top 25%
        Assert.Equal(1, Ranking.Tier(700));
    }

    // two friendlies under an old coach, then three matches in a 4-3-3 under the current one
    static readonly string[] XiRoles = ["GK", "RB", "CB", "CB", "LB", "DM", "CM", "CM", "RW", "LW", "ST"];
    static IEnumerable<string> Sheet(int match, int[] players) =>
        players.Select((p, i) => $"[{match},{p},90,1,\"{XiRoles[i]}\",{(i == 10 ? "1" : "null")},null,0,0]");
    static readonly int[] Eleven = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
    static readonly Nation.Team Team = Nation.ReadTeam(Read<NationDoc>($$$"""
        {"id":10,"name":"England","coach":{"id":40,"name":"T. Tuchel","since":"2025-01-01"},
         "match_fields":["date","opp","venue","gf","ga","tournament","formation","coach","coach_id"],
         "matches":[
           ["2024-10-10","Greece","H",1,2,"UEFA Nations League","4-2-3-1","L. Carsley",39],
           ["2025-03-21","Albania","H",2,0,"World Cup - Qualification","4-3-3","T. Tuchel",40],
           ["2025-06-07","Andorra","A",1,0,"World Cup - Qualification","4-3-3","T. Tuchel",40],
           ["2026-10-06","Czechia","H",3,0,"UEFA Nations League","4-3-3","T. Tuchel",40]],
         "app_fields":["match","player","minutes","started","role","goals","assists","yellow","red"],
         "apps":[{{{string.Join(',', Sheet(0, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20]).Concat(Sheet(1, Eleven)).Concat(Sheet(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12])).Concat(Sheet(3, Eleven))
             .Append("[3,12,20,0,null,1,null,1,0]").Append("[3,13,null,0,null,null,null,0,1]"))}}}],
         "players":{"1":"J. Pickford","11":"H. Kane","12":"O. Watkins","13":"N. O&apos;Reilly","20":"Old Striker"}}
        """));

    [Fact]
    public void A_nations_file_gives_each_match_the_eleven_that_started_and_reads_encoded_names()
    {
        Assert.Equal(11, Team.Matches[3].Xi.Count);
        Assert.Equal("N. O'Reilly", Team.PlayerName(13));
    }

    [Fact]
    public void The_current_coachs_matches_run_from_his_start_date_or_else_his_unbroken_spell()
    {
        var spell = Nation.SpellOf(Team);
        Assert.Equal(("T. Tuchel", "2025-01-01", true), (spell.Coach, spell.Since, spell.Full));
        Assert.Equal(["2025-03-21", "2025-06-07", "2026-10-06"], spell.Rows.Select(m => m.Date));
        Assert.Equal("Under T. Tuchel", Nation.SpellLabel(spell));
        var noDate = Nation.SpellOf(Team with { Coach = null });
        Assert.Equal("T. Tuchel", noDate.Coach);
        Assert.Equal(3, noDate.Rows.Count);
    }

    [Fact]
    public void The_predicted_XI_uses_the_coachs_usual_formation_and_whoever_started_in_each_position_most()
    {
        var shape = Nation.ShapeOf(Team)!;
        Assert.Equal("4-3-3", shape.Formation);
        Assert.Equal(2, shape.Need.First(x => x.Role == "CB").N);
        Assert.Equal(2, shape.Need.First(x => x.Role == "CM").N);
        var pred = Nation.PredictedXi(Team, new HashSet<int>())!;
        Assert.Equal(11, pred.Picks.Count);
        Assert.Equal(11, pred.Picks.First(p => p.Role == "ST").Pid);
        Assert.Equal("GK", pred.Picks[0].Role);
        // a regular who is injured is left out, and said to be
        var hurt = Nation.PredictedXi(Team, new HashSet<int> { 11 })!;
        Assert.Equal(12, hurt.Picks.First(p => p.Role == "ST").Pid);
        Assert.Equal([11], hurt.Out);
    }

    static Player Listed(int id, string position, double ord, double? rank = 80) =>
        new(id, $"Player {id}", position, rank, 42, ord, null, null, null, false);
    static readonly List<Player> List = [Listed(11, "ST", 0), Listed(50, "ST", 1), Listed(9, "RW", 2), Listed(60, "AM", 3, null)];

    [Fact]
    public void The_overview_puts_the_best_in_each_position_of_the_usual_shape_with_everyone_the_coach_has_picked()
    {
        var pitch = Nation.OverviewPitch(List, Team);
        Assert.Equal(("4-3-3", "T. Tuchel", true), (pitch.Formation, pitch.Coach, pitch.HasShape));
        var st = pitch.Boxes.First(b => b.Label == "ST");
        Assert.Equal([(11, false), (50, true), (12, false)], st.Players.Select(x => (x.P.Id, x.Unpicked)));
        Assert.Equal(("O. Watkins", false, (double?)null), (st.Players[2].P.Name, st.Players[2].P.Listed, st.Players[2].P.Rank));
        // a player whose own position the shape lacks goes in the nearest it has
        Assert.Contains(pitch.Boxes.First(b => b.Label == "CM").Players, x => x.P.Id == 60);
    }

    [Fact]
    public void Without_line_ups_the_overview_shows_the_top_three_in_a_fixed_set_of_positions()
    {
        var pitch = Nation.OverviewPitch(List, null);
        Assert.False(pitch.HasShape);
        Assert.Equal(["GK", "RB", "CB", "LB", "DM", "CM", "RW", "AM", "LW", "ST"], pitch.Boxes.Select(b => b.Label));
        Assert.Equal([false, false], pitch.Boxes.First(b => b.Label == "ST").Players.Select(x => x.Unpicked));
    }

    [Fact]
    public void Players_under_the_coach_add_up_his_matches_and_sort_by_the_column_asked_for()
    {
        var spell = Nation.SpellOf(Team);
        var players = Nation.Players(Team, spell, _ => "AM", "minutes");
        Nation.NatPlayer Of(int id) => players.First(p => p.Id == id);
        Assert.Equal((2, 180, 2, "ST", "2026-10-06"), (Of(11).Apps, Of(11).Minutes, Of(11).Goals, Of(11).Role, Of(11).Last));
        Assert.DoesNotContain(players, p => p.Id == 20);
        // a match with no stat line is one whose minutes aren't known; no start falls back to his club position
        Assert.Equal((1, 0, 1, 1, 3, "AM"), (Of(13).Apps, Of(13).Minutes, Of(13).NoMins, Of(13).R, Of(13).Cards, Of(13).Role));
        Assert.Equal((2, 110, 1), (Of(12).Apps, Of(12).Minutes, Of(12).Y));
        Assert.Equal(13, Nation.Players(Team, spell, _ => null, "cards")[0].Id);
        Assert.Equal(270, players[0].Minutes);
    }

    [Fact]
    public void A_garbled_names_invisible_control_characters_are_dropped()
    {
        Assert.Equal("K. UrbaÅski", ClubData.Decode("K. UrbaÅ\u0084ski"));
        Assert.Equal("N. O'Reilly", ClubData.Decode("N. O&apos;Reilly"));
    }
}
