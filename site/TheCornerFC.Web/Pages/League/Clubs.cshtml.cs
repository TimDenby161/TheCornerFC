using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.League;

// The competition's clubs by Baseline Strength, with their actual table position
public sealed class ClubsModel(Database db) : LeaguePage(db)
{
    public Leagues.Sort Sort { get; private set; } = new("lt", -1);
    public List<Leagues.RatingRow> Rows { get; private set; } = [];

    protected override Task<IActionResult?> Load()
    {
        var pos = L.Table.GroupBy(r => r.Team).ToDictionary(g => g.Key, g => g.Last().Rank);
        Sort = Leagues.PickSort(Leagues.StrengthCols, "lt", Request.Query["sort"].FirstOrDefault(), Request.Query.ContainsKey("rev"));
        var rows = Leagues.RatingRows(L.All, L.Club)(Leagues.LeagueRanked(L.All, L.Id, L.Table, L.Fixtures),
            L.Table.Count > 0 ? r => pos.TryGetValue(r.Team, out var p) ? p : null : null, null);
        Rows = Leagues.SortRows(rows, Sort, Leagues.StrengthCols);
        return Task.FromResult<IActionResult?>(null);
    }
}
