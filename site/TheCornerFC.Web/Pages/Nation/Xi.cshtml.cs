using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.NationTabs;

// The predicted XI, read off the current coach's recent team sheets
public sealed class XiModel(Database db) : NationPageModel(db)
{
    public sealed record Out(int Id, string Name, string Short, bool Link);
    public string State { get; private set; } = "none"; // none, few or xi
    public List<Lineups.Spot> Spots { get; private set; } = [];
    public List<Out> Outs { get; private set; } = [];

    protected override async Task<IActionResult?> Load()
    {
        if (N.Team is not { } team) return null;
        var pred = Nation.PredictedXi(team, await NationBase.InjuredPlayers(Db));
        if (pred is null) { State = "few"; return null; }
        State = "xi";
        string Name(int pid) => team.PlayerName(pid) is { Length: > 0 } n ? n : N.Known.GetValueOrDefault(pid)?.Name is { Length: > 0 } k ? k : "Unknown";
        Spots = Lineups.Spots(pred.Picks.Select(c => new Lineups.Starter(c.Pid, Name(c.Pid), c.Role, N.Known.GetValueOrDefault(c.Pid)?.Rank)).ToList());
        Outs = pred.Out.Select(pid => new Out(pid, Name(pid), ClubPage.ShortName(Name(pid)), N.Known.ContainsKey(pid))).ToList();
        return null;
    }
}
