using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.PlayerTabs;

// Rank by season with his clubs, and the clubs his current rank is built on
public sealed class CareerModel(Database db) : PlayerPageModel(db)
{
    public sealed record SpellView(int Team, string Name, double? ClubRank, int Minutes, int Goals, int Assists);
    public sealed record Row(int Y, string Label, int? Age, double Rank, bool Est, List<SpellView> Spells, List<PlayerPage.Share> Shares, string? RatedAs);

    public List<Row> Rows { get; private set; } = [];
    public List<PlayerPage.ChartPoint> Points { get; private set; } = [];
    public List<SpellView> NowSpells { get; private set; } = [];

    protected override Task<IActionResult?> Load()
    {
        var seasons = Site.PlayerSeasons!;
        List<SpellView> View(List<Spell> sp) => sp.Select(x => new SpellView(x.Team, Club(x.Team), x.ClubRank, x.Minutes ?? 0, x.Goals ?? 0, x.Assists ?? 0)).ToList();
        Rows = seasons.Select((y, k) => (y, k)).SelectMany(t =>
        {
            var v = P.Seasons is { } s && t.k < s.Length ? s[t.k] : null;
            if (v is null) return [];
            var pos = Doc?.Positions?.GetValueOrDefault(t.y.ToString()) is { } rows ? PlayerFiles.Roles(rows) : null;
            var group = PlayerPage.SeasonGroup(pos);
            return new[] { new Row(t.y, ClubPage.SeasonShort(t.y), P.Age is { } a ? a - (seasons[0] - t.y) : null, v.Value, P.Estimated?.Contains(t.k) == true,
                View(PlayerFiles.Spells(Doc, t.y.ToString())), pos is not null ? PlayerPage.PositionShares(pos) : [], pos is not null && group is not null ? Names.GroupSingle[group] : null) };
        }).ToList();
        // the chart's points, oldest first
        var points = Enumerable.Reverse(Rows).Select(r => new PlayerPage.ChartPoint(r.Label, $"{r.Y}/{(r.Y + 1).ToString()[2..]}", r.Rank, r.Est)).ToList();
        Points = points.Count >= 2 ? points : [];
        NowSpells = View(PlayerFiles.Spells(Doc, "now"));
        return Task.FromResult<IActionResult?>(null);
    }
}
