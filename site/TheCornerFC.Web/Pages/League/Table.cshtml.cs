using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.League;

// This season's actual table, one per group, zones coloured from the feed's notes
public sealed class TableModel(Database db) : LeaguePage(db)
{
    public sealed record Row(TableRow R, string Name, double? Current, string Zone);
    public Leagues.Sort Sort { get; private set; } = new("rank", 1);
    public bool HasXg { get; private set; }
    public bool Several { get; private set; }
    public List<(string Name, List<Row> Rows)> Groups { get; private set; } = [];

    static readonly IReadOnlyDictionary<string, Leagues.Col<Row>> Cols = new Dictionary<string, Leagues.Col<Row>>
    {
        ["rank"] = new(1, r => r.R.Rank), ["club"] = new(1, r => r.Name),
        ["played"] = new(-1, r => r.R.Played), ["win"] = new(-1, r => r.R.Win), ["draw"] = new(-1, r => r.R.Draw),
        ["lose"] = new(-1, r => r.R.Lose), ["gf"] = new(-1, r => r.R.Gf), ["ga"] = new(1, r => r.R.Ga),
        ["gd"] = new(-1, r => r.R.Gd), ["points"] = new(-1, r => r.R.Points),
        ["xg90"] = new(-1, r => r.R.Xg90), ["xga90"] = new(1, r => r.R.Xga90),
        ["form"] = new(-1, r => Leagues.FormPoints(r.R.Form)), ["current"] = new(-1, r => r.Current),
    };

    protected override Task<IActionResult?> Load()
    {
        var rows = L.Table.Select(r => new Row(r, L.Club(r.Team), L.ByTeam.GetValueOrDefault(r.Team)?.Current, Leagues.ZoneOf(L.Zones, r.Description))).ToList();
        HasXg = rows.Any(r => r.R.Xg90 is not null); // leagues without shot data don't get the columns
        var asked = Request.Query["sort"].FirstOrDefault();
        Sort = Leagues.PickSort(Cols, "rank", !HasXg && asked?.StartsWith("xg") == true ? null : asked, Request.Query.ContainsKey("rev"));
        var groups = rows.Select(r => r.R.Group).Distinct().ToList();
        Several = groups.Count > 1;
        Groups = groups.Select(g => (g ?? "", Leagues.SortRows(rows.Where(r => r.R.Group == g), Sort, Cols))).ToList();
        return Task.FromResult<IActionResult?>(null);
    }
}
