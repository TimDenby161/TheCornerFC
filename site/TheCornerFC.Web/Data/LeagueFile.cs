using System.Text.Json;
using System.Text.Json.Serialization;

namespace TheCornerFC.Web.Data;

// A competition's own file (leagues/<id>, or the whole of it through site_league for a
// subscriber; web/src/lib/league.ts): the table, the season's fixtures with the model's
// predictions, and each club's recent expected goals. `Cut`: the database left the season's
// projections out for this visitor (the paywall); `Projected` is what it gives instead.
public sealed record LeagueFile(
    int Id, int Season, string? Start,
    [property: JsonPropertyName("table_fields")] string[] TableFields, JsonElement[][] Table,
    [property: JsonPropertyName("fixture_fields")] string[] FixtureFields, JsonElement[][] Fixtures,
    [property: JsonPropertyName("recent_xg_fields")] string[]? RecentXgFields,
    [property: JsonPropertyName("recent_xg")] Dictionary<string, double[]>? RecentXg,
    Dictionary<string, string>? Teams,
    bool? Cut,
    [property: JsonPropertyName("projected_fields")] string[]? ProjectedFields,
    JsonElement[][]? Projected);

public sealed record TableRow(string? Group, int Rank, int Team, int? Played, int? Win, int? Draw, int? Lose,
    int? Gf, int? Ga, int? Gd, int? Points, string? Form, string? Description,
    // estimated xG and xG conceded per 90 over its last five league games with shot counts
    double? Xg90, double? Xga90, int XgGames);

public sealed record Fixture(int Id, string Kickoff, string? Round, int Home, int Away, string Status,
    int? Hg, int? Ag, int? PenH, int? PenA, double? HomeXg, double? AwayXg, double? PHome, double? PDraw, double? PAway);

public sealed record Headline(string? Group, int Place, int Team, int Left, int Points);

// A row of a file's table, read by its field names
public sealed class Named(string[] fields, JsonElement[] row)
{
    JsonElement? At(string f) { var i = Array.IndexOf(fields, f); return i >= 0 && i < row.Length ? row[i] : null; }
    public string? S(string f) => At(f) is { ValueKind: JsonValueKind.String } e ? e.GetString() : null;
    public double? D(string f) => At(f) is { ValueKind: JsonValueKind.Number } e ? e.GetDouble() : null;
    public int? I(string f) => D(f) is { } d ? (int)d : null;
}

public static class LeagueFiles
{
    public static List<TableRow> TableRows(LeagueFile lg)
    {
        var xf = lg.RecentXgFields ?? [];
        return lg.Table.Select(r =>
        {
            var n = new Named(lg.TableFields, r);
            var team = n.I("team") ?? 0;
            var x = lg.RecentXg?.GetValueOrDefault(team.ToString());
            double? Xg(string f) => x is null ? null : x[Array.IndexOf(xf, f)];
            return new TableRow(n.S("group"), n.I("rank") ?? 0, team, n.I("played"), n.I("win"), n.I("draw"), n.I("lose"),
                n.I("gf"), n.I("ga"), n.I("gd"), n.I("points"), n.S("form"), n.S("description"),
                Xg("xg90"), Xg("xga90"), x is null ? 0 : (int)x[Array.IndexOf(xf, "games")]);
        }).ToList();
    }

    public static List<Fixture> FixtureRows(LeagueFile lg) => lg.Fixtures.Select(r =>
    {
        var n = new Named(lg.FixtureFields, r);
        return new Fixture(n.I("id") ?? 0, n.S("kickoff") ?? "", n.S("round"), n.I("home") ?? 0, n.I("away") ?? 0, n.S("status") ?? "",
            n.I("hg"), n.I("ag"), n.I("pen_h"), n.I("pen_a"), n.D("home_xg"), n.D("away_xg"), n.D("p_home"), n.D("p_draw"), n.D("p_away"));
    }).ToList();

    public static List<Headline> Headline(LeagueFile lg) => (lg.Projected ?? []).Select(r =>
    {
        var n = new Named(lg.ProjectedFields ?? [], r);
        return new Headline(n.S("group"), n.I("place") ?? 0, n.I("team") ?? 0, n.I("left") ?? 0, n.I("points") ?? 0);
    }).ToList();
}
