using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.PlayerTabs;

// A player's Overview: his club's next match and whether he is in its predicted XI, his
// positions and this season
public sealed class IndexModel(Database db) : PlayerPageModel(db)
{
    static readonly HashSet<string> BanReasons = ["Red Card", "Yellow Cards", "Suspended"];
    sealed record NextXi(int Fixture, JsonElement[][]? Players, bool? Locked);

    public NextMatch? Next { get; private set; }
    public (string Cls, string Text)? Status { get; private set; }
    public List<PlayerPage.Chip> Chips { get; private set; } = [];
    public bool Keeper { get; private set; }
    public string? Listed { get; private set; }
    public PlayerSkills.View? Skills { get; private set; }

    protected override async Task<IActionResult?> Load()
    {
        var p = P;
        Skills = PlayerSkills.Of(p, Site);
        // his club's next match: when, who, the model's view, and whether he is listed unavailable
        // for it (the injury itself isn't published: only "Doubtful", "Suspended" or "Out")
        TheCornerFC.Web.Data.Match? m = null;
        if (p.Team is { } team)
        {
            var answer = await Db.AskAs<MatchesAnswer>(Visitor.Token, "site_matches", new { p_team = team });
            m = ClubData.Upcoming(ClubData.MatchRows(Site, answer)).FirstOrDefault();
        }
        // his club's predicted XI for that match (for subscribers: `Locked` for anyone else)
        NextXi? xi = null;
        if (m is not null)
            try { xi = await Db.AskAs<NextXi?>(Visitor.Token, "site_next_xi", new { p_team = p.Team }); }
            catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { xi = null; }
        var xiHere = xi is not null && xi.Locked != true && xi.Players is not null && xi.Fixture == m?.Id;
        var inXi = xiHere ? xi!.Players!.FirstOrDefault(r => r[0].GetInt32() == p.Id) : null;
        var inj = Doc?.Injury is { ValueKind: JsonValueKind.Array } j ? j.EnumerateArray().ToArray() : null;
        string? InjType() => inj is not null && inj.Length > 1 ? inj[1].GetString() : null;
        string? InjBan() => inj is not null && inj.Length > 2 && inj[2].ValueKind == JsonValueKind.String ? inj[2].GetString() : null;
        bool Suspended() => InjType() == "Suspended" || (InjBan() is { } ban && BanReasons.Contains(ban));
        if (m is not null && p.Team is { } t)
        {
            var home = m.Home == t;
            var opp = home ? m.Away : m.Home;
            Next = new(DateTimeOffset.Parse(m.Kickoff), ClubData.Live.Contains(m.Status), home, opp, Site.TeamName(opp), Site.CompLabel(m.League),
                m.PHome is { } ph && m.PAway is { } pa ? Js.RoundInt(100 * (home ? ph : pa)) : null,
                Proj: m.HomeXg is { } hx && m.AwayXg is { } ax ? $"{Js.ToFixed(home ? hx : ax, 1)}–{Js.ToFixed(home ? ax : hx, 1)}" : "");
            Status = inj is not null && inj[0].GetInt32() == m.Id
                ? (InjType() == "Questionable" ? "warn" : "bad", InjType() == "Questionable" ? "Doubtful" : Suspended() ? "Suspended" : "Out")
                : inXi is not null ? ("good", $"In the predicted XI{(inXi.Length > 2 && inXi[2].ValueKind == JsonValueKind.String ? $" as {inXi[2].GetString()}" : "")}")
                : xiHere ? ("muted", "Not in the predicted XI") : null;
        }
        Chips = PlayerPage.PositionChips(p.Position, p.Rank, p.PositionRanks, Doc?.Positions);
        Keeper = p.Position is not null && Names.GroupOf.GetValueOrDefault(p.Position) == "GK";
        Listed = inj is null ? null : InjType() == "Questionable" ? "doubtful" : Suspended() ? "suspended" : "out";
        return null;
    }
}
