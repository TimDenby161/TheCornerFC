using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.ClubTabs;

// The next match, the predicted XI on the pitch, and the expected squad's strength. Predicted
// line-ups are for subscribers: a visitor the database sent cut-down data is told so.
public sealed class XiModel(Database db) : ClubPageModel(db)
{
    public bool Paywall { get; private set; }
    public string[]? Kit { get; private set; }
    public List<Lineups.Spot>? Spots { get; private set; }
    public int? Average { get; private set; }
    public Depth.Strength? Squad { get; private set; }
    public NextMatch? Next { get; private set; }

    protected override async Task<IActionResult?> Load()
    {
        var site = C.Site;
        var squad = await C.SquadFor(Db, Visitor.Token);
        if (squad.Paywall) { Paywall = true; return null; }
        Kit = squad.Kit;
        var xi = Depth.PredictedXi(squad.Depth);
        var ranks = (xi ?? []).Where(c => c.Rank is not null).Select(c => c.Rank!.Value).ToList();
        Spots = xi is null ? null : Lineups.Spots(xi.Select(c => new Lineups.Starter(c.P.Id, c.P.Name, c.Box.Label, c.Rank, c.Chance, c.Mins)).ToList());
        Average = ranks.Count > 0 ? Js.RoundInt(ranks.Sum() / ranks.Count) : null;
        Squad = Depth.SquadStrength(squad.Depth);
        if (squad.Next is { } m)
        {
            var home = m.Home == C.Id;
            var opp = home ? m.Away : m.Home;
            var both = m.HomeXg is not null && m.AwayXg is not null;
            Next = new(DateTimeOffset.Parse(m.Kickoff), ClubData.Live.Contains(m.Status), home, opp, site.TeamName(opp), site.CompLabel(m.League),
                m.PHome is { } ph && m.PAway is { } pa ? Js.RoundInt(100 * (home ? ph : pa)) : null,
                both ? (home ? m.HomeXg : m.AwayXg) : null, both ? (home ? m.AwayXg : m.HomeXg) : null,
                Xi: home ? m.HomeXi : m.AwayXi, Missing: (home ? m.HomeMissing : m.AwayMissing) ?? 0);
        }
        return null;
    }
}
