using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.NationTabs;

// Everyone who has played under the current coach, with appearances, minutes, goals, assists and cards
public sealed class PlayersModel(Database db, TimeProvider clock) : NationPageModel(db)
{
    public sealed record Row(Nation.NatPlayer P, string Short, bool Link, int? Team, string? TeamName, string LastText);

    public bool Any { get; private set; }
    public string Sort { get; private set; } = "minutes";
    public int Matches { get; private set; }
    public bool AnyNoMins { get; private set; }
    public string Heading { get; private set; } = "";
    public List<Row> Rows { get; private set; } = [];

    protected override Task<IActionResult?> Load()
    {
        if (N.Team is not { } team || N.Spell is not { } spell) return Task.FromResult<IActionResult?>(null);
        Any = true;
        var asked = Request.Query["sort"].ToString();
        Sort = Nation.PlayerSorts.Contains(asked) ? asked : "minutes";
        var thisYear = clock.GetUtcNow().Year.ToString();
        var list = spell.Rows;
        Matches = list.Count;
        var players = Nation.Players(team, spell, id => N.Known.GetValueOrDefault(id)?.Position, Sort);
        AnyNoMins = players.Any(p => p.NoMins > 0);
        Heading = $"{Nation.SpellLabel(spell)}{(spell.Since is { } s ? $" (since {ClubPage.LongDate(s)})" : "")} · {list.Count} match{(list.Count == 1 ? "" : "es")}{(spell.Full ? "" : $" from {ClubPage.LongDate(list[0].Date)}")}";
        Rows = players.Select(p =>
        {
            var site = N.Known.GetValueOrDefault(p.Id);
            var team = site?.Team is { } t and not 0 ? t : (int?)null;
            return new Row(p, ClubPage.ShortName(p.Name), site is not null, site?.Team, team is { } tm ? N.Site.TeamName(tm) : null,
                p.Last[..4] == thisYear ? ClubPage.ShortDate(p.Last) : ClubPage.LongDate(p.Last));
        }).ToList();
        return Task.FromResult<IActionResult?>(null);
    }
}
