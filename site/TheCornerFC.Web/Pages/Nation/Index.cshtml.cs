using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.NationTabs;

// The best in each position, where they play, and every ranked player of the nationality
public sealed class IndexModel(Database db) : NationPageModel(db)
{
    const int Limit = 100;
    public sealed record Spot(int Id, string Name, int? Rank, bool Unpicked, bool Link, string Tip);
    public sealed record Box(string Label, int Row, int Col, List<Spot> Players);
    public sealed record Row(int Id, string Name, string Position, int? Team, string? TeamName, int? Age, double? Rank);

    public Nation.Overview? Shape { get; private set; }
    public List<Box> Boxes { get; private set; } = [];
    public List<Row> Rows { get; private set; } = [];
    public bool ShowAll { get; private set; }

    protected override Task<IActionResult?> Load()
    {
        var (site, list) = (N.Site, N.List);
        ShowAll = Request.Query["all"].ToString() == "1";
        if (list.Count > 0)
        {
            var pitch = Shape = Nation.OverviewPitch(list, N.Team);
            Boxes = pitch.Boxes.Select(b => new Box(b.Label, b.Row, b.Col, b.Players.Select(x =>
            {
                var p = x.P;
                return new Spot(p.Id, ClubPage.ShortName(p.Name), p.Rank is { } r ? Js.RoundInt(r) : null, x.Unpicked, N.Known.ContainsKey(p.Id),
                    $"{p.Name}{(p.Team is { } t and not 0 ? $" · {site.TeamName(t)}" : "")}{(x.Unpicked ? $" · not picked by {(pitch.Coach is { Length: > 0 } c ? c : "the current coach")}" : "")}");
            }).ToList())).ToList();
        }
        Rows = (ShowAll ? list : list.Take(Limit)).Select(p => new Row(p.Id, p.Name, p.Position ?? "", p.Team,
            p.Team is { } t and not 0 ? site.TeamName(t) : null, p.Age, p.Rank)).ToList();
        return Task.FromResult<IActionResult?>(null);
    }

    public string AllHref()
    {
        var q = Request.Query.ToDictionary(kv => kv.Key, kv => kv.Value.ToString());
        q["all"] = "1";
        return "?" + Markup.Query(q);
    }
}
