using System.Text.Json;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/club.test.ts and depth.test.ts, for the C# site: the same cases, the same answers
public class ClubTests
{
    static List<ClubMatch> Rows(string matches) => ClubData.Matches(JsonSerializer.Deserialize<ClubDoc>(
        $$$"""{"id":1,"start":1000,"fields":["date","rank","opponent","home","gf","ga","league","formation"],"matches":{{{matches}}},"coach":null,"colors":null,"teams":{}}""", Database.Json));

    static readonly List<ClubMatch> R = Rows("""[["2025-05-20",1010,2,1,2,0,39,"4-3-3"],["2025-08-16",1004,3,0,0,1,39,"4-3-3"],["2025-09-01",1004,4,1,1,1,45,null],["2025-12-26",1020,5,1,3,0,39,"4-2-3-1"],["2026-01-10",1031,6,0,2,1,39,"4-3-3"]]""");

    [Fact]
    public void Reads_each_figure_by_its_field_and_nothing_for_a_club_with_no_file()
    {
        Assert.Equal(("2025-05-20", 1010d, 2, "4-3-3"), (R[0].Date, R[0].Rank, R[0].Gf, R[0].Formation));
        Assert.Empty(ClubData.Matches(null));
    }

    [Fact]
    public void A_moves_change_is_from_the_rating_before_the_files_start_for_the_first_match()
    {
        Assert.Equal(10, ClubPage.Move(R, 0, 1000));
        Assert.Equal(-6, ClubPage.Move(R, 1, 1000));
        Assert.Null(ClubPage.Move(R, 0, null));
    }

    [Fact]
    public void Seasons_run_july_to_june_or_the_calendar_year_for_a_club_that_plays_through_the_summer()
    {
        var s = ClubPage.SeasonsOf(R);
        Assert.False(s.Calendar);
        Assert.Equal([2024, 2025, 2025, 2025, 2025], R.Select(s.Of));
        Assert.Equal("25/26", s.Label(2025));
        var summer = Rows("""[["2025-06-10",1,2,1,1,0,253,null],["2025-07-10",1,2,1,1,0,253,null],["2025-12-01",1,2,1,1,0,253,null]]""");
        var c = ClubPage.SeasonsOf(summer);
        Assert.Equal([2025, 2025, 2025], summer.Select(c.Of));
        Assert.Equal("2025", c.Label(2025));
    }

    [Fact]
    public void History_lists_seasons_newest_first_with_record_goals_and_rating()
    {
        var seasons = ClubPage.History(R, 1000, lg => lg == 45);
        Assert.Equal(["25/26", "24/25"], seasons.Select(s => s.Label));
        var s0 = seasons[0];
        Assert.Equal((4, 2, 1, 1, 6, 3, 1010d, 1031d, 1031d, 39), (s0.Played, s0.W, s0.D, s0.L, s0.Gf, s0.Ga, s0.Start, s0.End, s0.Peak, s0.League));
        Assert.Equal((1, 1000d, 1010d), (seasons[1].Played, seasons[1].Start, seasons[1].End));
        Assert.Null(ClubPage.History(R.Skip(2).Take(1).ToList(), null, _ => true)[0].League);
    }

    [Fact]
    public void Formations_put_the_most_used_first_and_draw_a_keeper_and_a_dot_a_player()
    {
        var use = ClubPage.Formations(R.Where(m => m.Formation is not null).ToList());
        Assert.Equal(["4-3-3", "4-2-3-1"], use.Select(u => u.Formation));
        Assert.Equal(new ClubPage.FormationUse("4-3-3", 3, 75, "2W 0D 1L", 4, 2, "2026-01-10"), use[0]);
        Assert.Equal(11, ClubPage.FormationDots("4-2-3-1").Count);
        Assert.Equal((30, 9), ClubPage.FormationDots("4-4-2")[0]);
        Assert.Empty(ClubPage.FormationDots("nonsense"));
        Assert.Equal(["GK", "LB", "CB", "RB", "DM", "LW", "AM", "RW", "ST"], ClubPage.FormationRoles("4-2-3-1"));
        Assert.Equal(["GK", "CB", "LWB", "CM", "RWB", "ST"], ClubPage.FormationRoles("3-5-2"));
        Assert.Empty(ClubPage.FormationRoles("nonsense"));
    }

    [Fact]
    public void Names_dates_and_records()
    {
        Assert.Equal("Haaland", ClubPage.ShortName("E. Haaland"));
        Assert.Equal("van Dijk", ClubPage.ShortName("V. van Dijk"));
        Assert.Equal("Gabriel", ClubPage.ShortName("Gabriel Magalhães"));
        Assert.Equal("MA", ClubPage.PersonInitials("Mikel Arteta"));
        Assert.Equal("R", ClubPage.PersonInitials("Rodri"));
        Assert.Equal("5 Sep", ClubPage.ShortDate("2026-09-05"));
        Assert.Equal("1 Dec 2019", ClubPage.LongDate("2019-12-01"));
        Assert.Equal("3W 1D 1L", ClubPage.Wdl(R));
    }
}

public class DepthTests
{
    static Depth.SquadPlayer P(int id, string pos, double rank) => new(id, $"P{id}", pos, rank, null, [pos]);
    static readonly List<Depth.SquadPlayer> Squad =
        [P(1, "GK", 80), P(2, "GK", 60), .. new[] { "RB", "CB", "CB", "LB", "CM", "CM", "AM", "RW", "LW", "ST" }.Select((pos, i) => P(10 + i, pos, 85 - i)), P(30, "ST", 70)];
    // six matches in a 4-2-3-1 with the same eleven, in team-sheet order
    static readonly object[] Line = [1, "GK", 10, "RB", 11, "CB", 12, "CB", 13, "LB", 14, "DM", 15, "DM", 16, "AM", 17, "RW", 18, "LW", 19, "ST"];
    static readonly Starts Starts = JsonSerializer.Deserialize<Starts>(JsonSerializer.Serialize(new
    {
        games = 6, xi = Enumerable.Repeat(Line, 6), xi_league = Enumerable.Repeat(39, 6), xi_formation = Enumerable.Repeat("4-2-3-1", 6),
        players = Enumerable.Range(0, 11).ToDictionary(i => Line[2 * i].ToString()!, i => new Dictionary<string, int> { [(string)Line[2 * i + 1]] = 6 }),
        mins = new Dictionary<string, double[]>(), mins_matches = 6,
    }), Database.Json)!;
    static Depth.Result? Of(params int[] o) => Depth.Of(new(Squad, o.ToHashSet(), Starts, null, Enumerable.Repeat<string?>("4-2-3-1", 6).ToList(), "league", _ => "league"));

    [Fact]
    public void Has_no_squad_without_players() => Assert.Null(Depth.Of(new([], [], null, null, [], null, _ => "league")));

    [Fact]
    public void Shows_only_the_positions_of_the_formations_used_with_their_usual_starters_adding_up_to_eleven()
    {
        var d = Of()!;
        Assert.Equal(["AM", "CB", "CM", "GK", "LB", "LW", "RB", "RW", "ST"], d.Shown.Select(b => b.Label).Order());
        Assert.Equal(11, d.Shown.Sum(b => b.N));
        Assert.Equal(2, d.Shown.First(b => b.Label == "CB").N);
    }

    [Fact]
    public void Gives_an_ever_present_nearly_all_the_start_chance_and_a_full_box_90_minutes_a_starter()
    {
        var d = Of()!;
        Assert.True(d.StartChance["GK:1"] > 95);
        Assert.True(d.StartChance["GK:2"] < 5);
        Assert.Equal(180, d.BoxMins["CB"]);
        foreach (var p in Squad) Assert.True(d.Shown.Sum(b => d.XMins.GetValueOrDefault($"{b.Label}:{p.Id}")) <= 90);
    }

    [Fact]
    public void Hands_an_injured_starters_share_to_whoever_else_plays_there()
    {
        var d = Of(19)!; // the striker is out
        Assert.Equal([30], d.Shown.First(b => b.Label == "ST").Ps.Select(x => x.P.Id));
        Assert.True(d.StartChance["ST:30"] > 95);
    }

    [Fact]
    public void The_predicted_xi_is_eleven_players_one_position_each_keeper_at_the_top_centre_backs_apart()
    {
        var xi = Depth.PredictedXi(Of())!;
        Assert.Equal([1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19], xi.Select(c => c.P.Id).Order());
        var spots = Depth.XiSpots(xi, c => c.Box.Label);
        var gk = spots.First(s => s.C.Box.Label == "GK");
        var cbs = spots.Where(s => s.C.Box.Label == "CB").ToList();
        Assert.True(gk.Y < cbs[0].Y);
        Assert.True(Math.Abs(cbs[0].X - cbs[1].X) >= 22);
        var s = Depth.SquadStrength(Of())!;
        Assert.InRange(s.Overall, 60, 86);
        Assert.NotNull(s.Attack);
    }

    [Theory]
    [InlineData("4-4-2")] [InlineData("4-3-3")] [InlineData("4-2-3-1")] [InlineData("4-1-4-1")] [InlineData("4-4-1-1")] [InlineData("4-3-2-1")]
    [InlineData("4-1-2-1-2")] [InlineData("4-2-2-2")] [InlineData("4-3-1-2")] [InlineData("4-5-1")] [InlineData("3-4-3")] [InlineData("3-5-2")]
    [InlineData("3-4-2-1")] [InlineData("3-4-1-2")] [InlineData("3-1-4-2")] [InlineData("5-3-2")] [InlineData("5-4-1")]
    public void Keeps_every_pair_on_the_same_or_neighbouring_lines_22_percent_apart(string shape)
    {
        // each line's roles as positions.py names them (one entry per player, so repeats kept)
        var lines = shape.Split('-').Select(int.Parse).ToArray();
        int last = lines.Length - 1;
        var roles = new List<string> { "GK" };
        static string Wide(int n, int col, string l, string m, string r) => col == 1 ? l : col == n ? r : m;
        for (var idx = 0; idx < lines.Length; idx++)
            for (int n = lines[idx], col = 1; col <= n; col++)
                roles.Add(idx == 0 ? (n == 4 ? Wide(n, col, "LB", "CB", "RB") : n == 5 ? Wide(n, col, "LWB", "CB", "RWB") : "CB")
                    : idx == last ? (n >= 3 ? Wide(n, col, "LW", "ST", "RW") : "ST")
                    : last == 2 || idx == 1 ? (last != 2 && n <= 2 ? "DM" : n == 4 ? (lines[0] == 3 ? Wide(n, col, "LWB", "CM", "RWB") : Wide(n, col, "LM", "CM", "RM")) : n == 5 ? Wide(n, col, "LWB", "CM", "RWB") : "CM")
                    : n <= 2 ? (idx == last - 1 ? "AM" : "CM") : n == 4 ? Wide(n, col, "LM", "CM", "RM") : Wide(n, col, "LW", "AM", "RW"));
        var spots = Depth.XiSpots(roles, r => r);
        Assert.Equal(11, spots.Count);
        foreach (var a in spots)
            foreach (var b in spots)
            {
                if (ReferenceEquals(a, b) || a.Equals(b) || Math.Abs(a.Y - b.Y) >= 10) continue;
                Assert.True(Math.Abs(a.X - b.X) >= 22, $"{shape}: {a.C} and {b.C}");
                Assert.InRange(a.X, 14, 86);
            }
    }
}
