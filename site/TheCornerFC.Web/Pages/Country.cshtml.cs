using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// A country: its leagues (strongest first), cups and clubs (web/src/routes/(app)/country/[name]).
public sealed class CountryModel(Database db) : PageModel
{
    const int Limit = 50;

    public string Name { get; private set; } = "";
    public string? Flag { get; private set; }
    public string Counts { get; private set; } = "";
    public (int Value, int Tier)? Avg { get; private set; }
    public List<Card> LeagueCards { get; private set; } = [];
    public List<Card> CupCards { get; private set; } = [];
    public List<Leagues.RatingRow> Rows { get; private set; } = [];
    public Leagues.Sort Sort { get; private set; } = new("current", -1);
    public bool ShowAll { get; private set; }
    public int Total { get; private set; }

    public sealed record Card(int Lid, string Name, string Sub, (int Value, int Tier)? Avg);

    public async Task<IActionResult> OnGet(string name)
    {
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var docTask = db.KeptDoc<Rankings>("rankings");
        await Task.WhenAll(siteTask, docTask);
        var site = siteTask.Result;
        var comps = site.Competitions.Where(kv => kv.Value.Country == name && kv.Value.Type != "International")
            .Select(kv => (Lid: int.Parse(kv.Key), Comp: kv.Value)).ToList();
        if (comps.Count == 0) return NotFound();
        var all = Clubs.From(docTask.Result);
        Name = ClubTable.CountryDisplay(name);
        var tier = Clubs.Tiers(all, "lt");
        var leagues = comps.Where(c => c.Comp.Type == "League")
            .Select(c => { var list = Leagues.LeagueClubs(all, c.Lid); return (c.Lid, c.Comp.Name, List: list, Avg: Leagues.AvgRating(list)); })
            .OrderByDescending(c => c.Avg ?? -1).ToList();
        int Order(int lid) { var k = Names.GroupOrder.ToList().IndexOf(lid); return k < 0 ? 999 : k; }
        var cups = comps.Where(c => c.Comp.Type != "League").OrderBy(c => Order(c.Lid)).ToList();
        var list = leagues.SelectMany(c => c.List).OrderByDescending(r => r.Lt).ToList();
        var avg = Leagues.AvgRating(list.Take(15).ToList()); // the country's level: its 15 best clubs
        // sorted by Current Strength to start; # stays the Baseline Strength rank
        Sort = Leagues.PickSort(Leagues.StrengthCols, "current", Request.Query["sort"].FirstOrDefault(), Request.Query.ContainsKey("rev"));
        ShowAll = Request.Query["all"] == "1";
        var rows = Leagues.SortRows(Leagues.RatingRows(all, site.TeamName)(list, null,
            leagues.Count > 1 ? r => (r.League, site.LeagueShort(r.League)) : null), Sort, Leagues.StrengthCols);
        if (!Visitor.Of(HttpContext).SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        Card ToCard(int lid, string cname, List<Club>? clubs, double? average) => new(lid, cname,
            clubs is { Count: > 0 } ? $"{clubs.Count} clubs · top rated {site.TeamName(clubs[0].Team)}" : "",
            average is { } a ? (Js.RoundInt(a), tier(a)) : null);
        Flag = Names.FlagCodes.GetValueOrDefault(Name);
        Total = list.Count;
        Counts = string.Join(" · ", new[] { (leagues.Count, "league"), (cups.Count, "cup"), (list.Count, "club") }
            .Where(x => x.Item1 > 0).Select(x => $"{x.Item1} {x.Item2}{(x.Item1 == 1 ? "" : "s")}"));
        Avg = avg is { } v ? (Js.RoundInt(v), tier(v)) : null;
        LeagueCards = leagues.Select(c => ToCard(c.Lid, c.Name, c.List, c.Avg)).ToList();
        CupCards = cups.Select(c => ToCard(c.Lid, c.Comp.Name, null, null)).ToList();
        Rows = ShowAll ? rows : rows.Take(Limit).ToList();
        ViewData["Name"] = Name;
        return Page();
    }
}
