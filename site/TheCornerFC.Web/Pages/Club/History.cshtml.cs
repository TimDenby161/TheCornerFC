using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.ClubTabs;

// Season by season from the club's matches since 2020
public sealed class HistoryModel(Database db) : ClubPageModel(db)
{
    public sealed record Row(ClubPage.Season S, string? LeagueName, double Bar);
    public List<Row> Seasons { get; private set; } = [];

    protected override Task<IActionResult?> Load()
    {
        var site = C.Site;
        var seasons = ClubPage.History(C.Rows, C.Doc?.Start, lg => site.Comp(lg)?.Type == "Cup");
        if (seasons.Count > 0)
        {
            double lo = seasons.Min(s => s.End) - 20, hi = seasons.Max(s => s.End);
            // its bar in the chart: the lowest season's end sits a little above the floor
            Seasons = seasons.Select(s => new Row(s, s.League is { } l && site.LeagueShort(l) is { Length: > 0 } ln ? ln : null, Math.Max(6, 100 * (s.End - lo) / (hi - lo is var span && span != 0 ? span : 1)))).ToList();
        }
        return Task.FromResult<IActionResult?>(null);
    }
}
