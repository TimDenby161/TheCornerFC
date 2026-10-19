using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.NationTabs;

// The current coach, the formations used under him, then match by match with each starting XI
public sealed class FormationsModel(Database db, TimeProvider clock) : NationPageModel(db)
{
    public sealed record Head(string Name, string When, string Record);
    public sealed record Starter(int Id, string Role, string Name, bool Link, int Goals);
    public sealed record Game(int Key, string Date, string Opp, string? Flag, string Venue, string VenueName, string Tournament, int Gf, int Ga, string? Formation, List<Starter> Xi);

    public bool Any { get; private set; }
    public string Label { get; private set; } = "";
    public string ThisYear { get; private set; } = "";
    public Head? Coach { get; private set; }
    public List<ClubPage.FormationUse> Used { get; private set; } = [];
    public int Missing { get; private set; }
    public string Note { get; private set; } = "";
    public List<Game> Games { get; private set; } = [];

    static readonly Dictionary<string, string> Venues = new() { ["H"] = "Home", ["A"] = "Away", ["N"] = "Neutral ground" };

    protected override Task<IActionResult?> Load()
    {
        if (N.Team is not { } team || N.Spell is not { } spell) return Task.FromResult<IActionResult?>(null);
        Any = true;
        var list = spell.Rows;
        var first = ClubPage.LongDate(list[0].Date);
        // (a nation's matches as the club formations count them: date, result and formation)
        static ClubMatch AsClub(Nation.NatMatch m) => new(m.Date, 0, 0, 0, m.Gf, m.Ga, 0, m.Formation, null, null, null, null, null, null);
        var knownF = list.Where(m => !string.IsNullOrEmpty(m.Formation)).Select(AsClub).ToList();
        ThisYear = clock.GetUtcNow().Year.ToString();
        string When(string d) => d[..4] == ThisYear ? ClubPage.ShortDate(d) : ClubPage.LongDate(d);
        Label = Nation.SpellLabel(spell);
        if (spell.Coach is { } coach)
            Coach = new(coach, spell.Since is { } s ? $"Since {ClubPage.LongDate(s)}" : $"First match {first}{(spell.Full ? "" : " (or before)")}",
                $"{list.Count} matches{(spell.Since is not null && !spell.Full ? $" from {first}" : "")} · {ClubPage.Wdl(list.Select(AsClub).ToList())}");
        Used = ClubPage.Formations(knownF);
        Missing = list.Count - knownF.Count;
        Note = $"International matches API-Football has line-ups for{(spell.Full ? "" : $", from {first}{(spell.Since is not null ? "" : " (his spell may have started earlier)")}")}. Formations as on each team sheet.";
        Games = Enumerable.Reverse(list).Select(m => new Game(m.I, When(m.Date), m.Opp, Names.FlagCodes.GetValueOrDefault(m.Opp), m.Venue, Venues.GetValueOrDefault(m.Venue) ?? "",
            m.Tournament ?? "", m.Gf, m.Ga, m.Formation,
            m.Xi.Select((a, i) => (a, i)).OrderBy(t => Nation.Order(t.a.Role)).ThenBy(t => t.i).Select(t => t.a)
                .Select(a => new Starter(a.Player, a.Role is { Length: > 0 } r ? r : "–", ClubPage.ShortName(team.PlayerName(a.Player) is { Length: > 0 } n ? n : "Unknown"),
                    N.Known.ContainsKey(a.Player), a.Goals ?? 0)).ToList())).ToList();
        return Task.FromResult<IActionResult?>(null);
    }
}
