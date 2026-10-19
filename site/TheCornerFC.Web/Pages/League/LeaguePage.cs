using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.League;

// A competition's page (web/src/routes/(app)/league/[id]): the header every tab shares, then the
// tab. Each tab loads the competition (LeagueBase) and adds its own part.
public abstract class LeaguePage(Database db) : PageModel
{
    public LeagueBase L { get; private set; } = null!;
    public string Name { get; private set; } = "";
    public string Label { get; private set; } = "";
    public string CountryKey { get; private set; } = "";
    public string Country { get; private set; } = "";
    public string? Flag { get; private set; }
    public (int Value, int Tier)? Avg { get; private set; }
    public List<(string Key, string Label)> Tabs { get; private set; } = [];
    public string Tab { get; private set; } = "";
    protected Visitor Visitor => Site.Visitor.Of(HttpContext);

    public async Task<IActionResult> OnGet(string id)
    {
        var l = await LeagueBase.Load(db, id, Visitor.Token);
        if (l is null) return NotFound();
        L = l;
        if (!Visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        var avg = Leagues.AvgRating(Leagues.LeagueClubs(l.All, l.Id));
        Name = l.Comp?.Name ?? l.Site.CompLabel(l.Id);
        Label = l.Site.CompLabel(l.Id);
        CountryKey = l.Comp?.Country ?? "World";
        Country = ClubTable.CountryDisplay(CountryKey);
        Flag = Names.FlagCodes.GetValueOrDefault(Country);
        Avg = avg is { } a ? (Js.RoundInt(a), Clubs.Tiers(l.All, "lt")(a)) : null;
        // a cup without a table has no standings and nothing to project
        Tabs = new List<(string, string)> { ("table", "Standings"), ("clubs", "Strength ranking"), ("projected", "Projected table"), ("matches", "Matches") }
            .Where(t => (t.Item1 != "table" && t.Item1 != "projected") || l.Table.Count > 0).ToList();
        Tab = (Request.Path.Value ?? "").Split('/').ElementAtOrDefault(3) ?? "";
        ViewData["Name"] = Name;
        return await Load() ?? Page();
    }

    // the tab's own part; a result in place of the page where it has one (a redirect)
    protected abstract Task<IActionResult?> Load();
}
