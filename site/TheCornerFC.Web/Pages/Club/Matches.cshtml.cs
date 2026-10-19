using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.ClubTabs;

// A club's fixtures with the model's win chance, or every result since 2020 with the rating after it
public sealed class MatchesModel(Database db, TimeProvider clock) : ClubPageModel(db)
{
    const int Limit = 40;

    public sealed record FixtureCard(Cards.View Card, string Comp, int? Win);
    public sealed record ResultCard(string Key, string Res, string Meta, Cards.Side Home, Cards.Side Away, int Hg, int Ag,
        double? HomeXg, double? AwayXg, double?[]? Lines, double Rank, double? Attack, double? Defence, double? Move);

    public string View { get; private set; } = "fixtures";
    public int FixtureCount { get; private set; }
    public int ResultCount { get; private set; }
    public bool ShowAll { get; private set; }
    public List<FixtureCard> Fixtures { get; private set; } = [];
    public List<ResultCard> Results { get; private set; } = [];

    protected override async Task<IActionResult?> Load()
    {
        var site = C.Site;
        var (matches, paywall) = await C.Fixtures(Db, Visitor.Token);
        var ranks = C.All.ToDictionary(c => c.Team);
        var next = ClubData.Upcoming(matches);
        var rows = C.Rows;
        // fixtures unless results are asked for, or there are only results
        View = Request.Query["view"] == "results" || (next.Count == 0 && rows.Count > 0) ? "results" : "fixtures";
        ShowAll = Request.Query["all"] == "1";
        FixtureCount = next.Count;
        ResultCount = rows.Count;
        var now = clock.GetUtcNow();
        var thisYear = now.Year.ToString();
        if (View == "fixtures")
            Fixtures = next.Select(m =>
            {
                var home = m.Home == C.Id;
                return new FixtureCard(Cards.Of(site, ranks, m, paywall, now), site.CompLabel(m.League),
                    m.PHome is { } ph && m.PAway is { } pa ? Js.RoundInt(100 * (home ? ph : pa)) : null);
            }).ToList();
        else
            Results = rows.Select((m, i) => (M: m, Move: ClubPage.Move(rows, i, C.Doc?.Start))).Reverse().Take(ShowAll ? int.MaxValue : Limit).Select(x =>
            {
                var m = x.M;
                var home = m.Home != 0;
                var us = new Cards.Side(C.Id, C.Name, false, null, m.Rank);
                var them = new Cards.Side(m.Opponent, C.Opponent(m.Opponent), false, null, null);
                return new ResultCard($"{m.Date}:{m.Opponent}:{m.League}", char.ToLowerInvariant(ClubPage.Result(m.Gf, m.Ga)).ToString(),
                    $"{ClubPage.ShortDate(m.Date)}{(m.Date[..4] != thisYear ? $" '{m.Date[2..4]}" : "")} · {site.CompLabel(m.League)}",
                    home ? us : them, home ? them : us, home ? m.Gf : m.Ga, home ? m.Ga : m.Gf,
                    m.Xgf is null ? null : home ? m.Xgf : m.Xga, m.Xgf is null ? null : home ? m.Xga : m.Xgf,
                    m.XiLines, m.Rank, m.Attack, m.Defence, x.Move);
            }).ToList();
        return null;
    }
}
