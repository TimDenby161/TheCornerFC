using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.PlayerTabs;

// One season (all his clubs added up), as totals or per 90 minutes: appearances, minutes, goals,
// assists and cards only (the feed's other counts aren't published)
public sealed class StatsModel(Database db) : PlayerPageModel(db)
{
    public sealed record ClubLine(int Team, string Name, string Comp, int Apps, int Minutes);
    public bool Any { get; private set; }
    public int Shown { get; private set; }
    public int Latest { get; private set; }
    public bool Per90 { get; private set; }
    public bool Partial { get; private set; }
    public List<(int Y, string Label)> Years { get; private set; } = [];
    public List<ClubLine> ClubLines { get; private set; } = [];
    public int? AppsTotal { get; private set; }
    public int? Started { get; private set; }
    public int Minutes { get; private set; }
    public string Goals { get; private set; } = "";
    public string Assists { get; private set; } = "";
    public string Yellow { get; private set; } = "";
    public string Red { get; private set; } = "";

    protected override Task<IActionResult?> Load()
    {
        Any = Lines.Count > 0;
        if (!Any) return Task.FromResult<IActionResult?>(null);
        var years = Lines.Select(r => r.Season).Distinct().OrderDescending().ToList();
        var asked = int.TryParse(Request.Query["s"], out var a) ? a : 0;
        Shown = years.Contains(asked) ? asked : years[0];
        Latest = years[0];
        var rows = Lines.Where(r => r.Season == Shown).ToList();
        var s = PlayerPage.Sum(rows)!;
        Per90 = Request.Query["per90"] == "1" && s.Minutes is > 0;
        Partial = rows.Any(r => r.Starts is null);
        Years = years.Select(y => (y, ClubPage.SeasonShort(y))).ToList();
        ClubLines = rows.Select(r => new ClubLine(r.Team, Club(r.Team), Site.CompLabel(r.League), r.Apps, r.Minutes)).ToList();
        AppsTotal = s.Apps;
        Started = s.Starts is not null && !Partial ? s.Starts : null;
        Minutes = s.Minutes ?? 0;
        Goals = PlayerPage.StatText(s, "goals", Per90);
        Assists = PlayerPage.StatText(s, "assists", Per90);
        Yellow = PlayerPage.StatText(s, "yellow", Per90);
        Red = PlayerPage.StatText(s, "red", Per90);
        return Task.FromResult<IActionResult?>(null);
    }

    // this tab with a season and totals or per 90 picked; the latest season and totals are left out
    public string Address(int year, bool per90)
    {
        var q = new Dictionary<string, string>();
        if (year != Latest) q["s"] = year.ToString();
        if (per90) q["per90"] = "1";
        return q.Count > 0 ? "?" + Markup.Query(q) : Request.Path.Value!;
    }
}
