using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.PlayerTabs;

// His last league appearances, newest first
public sealed class MatchesModel(Database db) : PlayerPageModel(db)
{
    public sealed record Row(int Key, string Date, int Opp, string OppName, bool Home, string Res, int Gf, int Ga, double? Rank, string? Card, List<string> Bits);
    public List<Row> Rows { get; private set; } = [];

    protected override Task<IActionResult?> Load()
    {
        Rows = Apps.Select(m => new Row(m.Fixture, ClubPage.ShortDate(m.Date), m.Opponent, Club(m.Opponent), m.Home != 0,
            char.ToLowerInvariant(ClubPage.Result(m.Gf, m.Ga)).ToString(), m.Gf, m.Ga, m.Rank, m.Red != 0 ? "red" : m.Yellow != 0 ? "yellow" : null,
            new[]
            {
                $"{m.Minutes}′{(m.Started != 0 ? "" : " off the bench")}", m.Started != 0 && m.Role is { } r ? PlayerPage.PosWord.GetValueOrDefault(r) ?? r : "",
                m.Goals > 0 ? $"{m.Goals} goal{(m.Goals > 1 ? "s" : "")}" : "", m.Assists > 0 ? $"{m.Assists} assist{(m.Assists > 1 ? "s" : "")}" : "",
            }.Where(x => x != "").ToList())).ToList();
        return Task.FromResult<IActionResult?>(null);
    }
}
