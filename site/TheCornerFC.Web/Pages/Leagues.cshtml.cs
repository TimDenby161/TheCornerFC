using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// Every league with rated clubs, laid out like the Clubs ranking: strongest first by the average
// Baseline Strength of its clubs (the number on each league's page), or by another column
// (web/src/routes/(app)/leagues).
public sealed class LeaguesModel(Database db) : PageModel
{
    static readonly string[] Sorts = ["clubs", "lt", "trend", "current"];
    public string Sort { get; private set; } = "lt";
    public List<Row> Rows { get; private set; } = [];

    public sealed record Row(int Lid, string Name, string CountryKey, string Country, bool HasFlag, int Clubs, int Lt, int LtTier, int Trend, int Current, int CurrentTier);

    public async Task OnGet()
    {
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var docTask = db.KeptDoc<Rankings>("rankings");
        await Task.WhenAll(siteTask, docTask);
        var all = Clubs.From(docTask.Result);
        var asked = Request.Query["sort"].ToString();
        Sort = Sorts.Contains(asked) ? asked : "lt";
        var ltTier = Clubs.Tiers(all, "lt");
        var currentTier = Clubs.Tiers(all, "current");
        if (!Visitor.Of(HttpContext).SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        ViewData["TabHead"] = TabHead.For("Leagues", "leagues");
        double Key(Leagues.Average c) => Sort switch { "clubs" => c.Clubs, "trend" => c.Trend, "current" => c.Current, _ => c.Lt };
        Rows = Leagues.Averages(siteTask.Result, all).OrderByDescending(Key).ThenByDescending(c => c.Lt).Select(c =>
        {
            var country = ClubTable.CountryDisplay(c.Country);
            return new Row(c.Lid, c.Name, c.Country, country, Names.FlagCodes.ContainsKey(country), c.Clubs,
                Js.RoundInt(c.Lt), ltTier(c.Lt), c.Trend, Js.RoundInt(c.Current), currentTier(c.Current));
        }).ToList();
    }
}
