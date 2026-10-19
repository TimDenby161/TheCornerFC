using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.ClubTabs;

// The manager, then the formations used since he took over and this season (league line-ups only:
// cup matches outside the player-data leagues have no formation)
public sealed class FormationsModel(Database db, TimeProvider clock) : ClubPageModel(db)
{
    public sealed record Manager(string Name, string? Since, int Matches, string Record);
    public sealed record Section(string Title, List<ClubPage.FormationUse> Used, int Missing);

    public bool Any { get; private set; }
    public Manager? Boss { get; private set; }
    public List<Section> Sections { get; private set; } = [];
    public string ThisYear { get; private set; } = "";

    protected override Task<IActionResult?> Load()
    {
        var rows = C.Rows;
        Any = rows.Any(m => m.Formation is not null);
        if (!Any) return Task.FromResult<IActionResult?>(null);
        var coach = C.Doc?.Coach?.Name is { Length: > 0 } ? C.Doc.Coach : null;
        var seasons = ClubPage.SeasonsOf(rows);
        var season = seasons.Of(rows[^1]);
        var sinceRows = coach?.Since is { } since ? rows.Where(m => string.CompareOrdinal(m.Date, since) >= 0).ToList() : [];
        var seasonRows = rows.Where(m => seasons.Of(m) == season).ToList();
        Section Of(string title, List<ClubMatch> list)
        {
            var known = list.Where(m => m.Formation is not null).ToList();
            return new(title, ClubPage.Formations(known), list.Count - known.Count);
        }
        // the same matches either way (he took over before this season's first match): one list
        var same = sinceRows.Count == seasonRows.Count && sinceRows.FirstOrDefault() == seasonRows.FirstOrDefault();
        if (coach is not null)
            Boss = new(coach.Name!, coach.Since is { } s ? ClubPage.LongDate(s) : null, sinceRows.Count, ClubPage.Wdl(sinceRows));
        Sections.Add(Of($"{(same && coach is not null ? $"Since {coach.Name} took over · " : "")}This season ({seasons.Label(season)})", seasonRows));
        if (coach?.Since is not null && !same) Sections.Add(Of($"Since {coach.Name} took over", sinceRows));
        ThisYear = clock.GetUtcNow().Year.ToString();
        return Task.FromResult<IActionResult?>(null);
    }
}
