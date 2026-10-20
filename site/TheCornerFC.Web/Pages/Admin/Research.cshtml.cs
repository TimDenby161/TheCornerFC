using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.AdminArea;

// The research dashboard (Site/Research.cs): accuracy month by month for the competition picked in
// the address (?c=), its reliability over the last 12 months, the model against the bookmakers in
// every competition, and every challenger's running score. The administrator's only.
public sealed class ResearchModel(Database db) : PageModel
{
    public string Pick { get; private set; } = "all";
    public string PickName { get; private set; } = "";
    public List<(string Key, string Name)> Choices { get; private set; } = [];
    public bool HasMonths { get; private set; }
    public List<Research.MonthRow> Months { get; private set; } = [];
    public (string Right, string LogLoss)? Charts { get; private set; }
    public List<Research.Band> Bands { get; private set; } = [];
    public string? Reliability { get; private set; }
    public List<Research.VsRow> VsMarket { get; private set; } = [];
    public List<Research.Challenger> Challengers { get; private set; } = [];
    public string? LiveNote { get; private set; }

    public async Task<IActionResult> OnGet()
    {
        ViewData["TabHead"] = TabHead.For("Research", "research");
        var token = Visitor.Of(HttpContext).Token;
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var statsTask = Quiet(db.KeptDoc<StatsDoc>("stats", TimeSpan.FromMinutes(5)));
        var liveTask = TheCornerFC.Web.Site.Admin.Doc<ModelDoc.LiveDoc>(db, token, "live_tracking");
        var changesTask = TheCornerFC.Web.Site.Admin.Doc<ModelDoc>(db, token, "model_changes");
        await Task.WhenAll(siteTask, statsTask, liveTask, changesTask);
        if (liveTask.Result.Refused || changesTask.Result.Refused) return NotFound();
        var (site, stats) = (siteTask.Result, statsTask.Result);
        string Name(string key) => key == "all" ? "All competitions" : key == "eng" ? "English competitions" : int.TryParse(key, out var id) ? site.LeagueName(id) : key;
        if (stats is not null)
        {
            var year = stats.Ranges.GetValueOrDefault("365d") ?? [];
            // every competition with a year's record, the most matches first
            Choices = year.OrderBy(kv => kv.Key == "all" ? 0 : kv.Key == "eng" ? 1 : 2).ThenByDescending(kv => kv.Value.N).ThenBy(kv => kv.Key, StringComparer.Ordinal)
                .Select(kv => (kv.Key, $"{Name(kv.Key)} ({Js.Num(kv.Value.N)})")).ToList();
            var c = Request.Query["c"].ToString();
            Pick = year.ContainsKey(c) ? c : "all";
            HasMonths = stats.MonthsOf(Pick) is not null;
            Months = Research.Months(stats, Pick);
            Charts = Research.MonthCharts(stats, Pick);
            Bands = Research.Bands(year.GetValueOrDefault(Pick));
            if (Bands.Count > 0) Reliability = Research.ReliabilitySvg(Bands);
            VsMarket = Research.AgainstMarket(stats, Name);
        }
        PickName = Name(Pick);
        var live = liveTask.Result.Doc;
        Challengers = Research.Challengers(live, changesTask.Result.Doc?.Changes ?? []);
        if (live is not null)
            LiveNote = $"{Js.Num(live.N)} finished matches since {live.Start}, over {live.Weeks} week{(live.Weeks == 1 ? "" : "s")} ({live.Protocol}). Nothing is called before {live.Minimum.Matches} matches and {live.Minimum.Weeks} weeks.";
        return Page();
    }

    static async Task<T?> Quiet<T>(Task<T> t) where T : class
    {
        try { return await t; }
        catch (DatabaseException) { return null; }
    }
}
