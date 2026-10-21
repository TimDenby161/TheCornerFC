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
    public Research.Accuracy Accuracy { get; private set; } = null!;
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
        Accuracy = Research.AccuracyOf(statsTask.Result, siteTask.Result, Request.Query["c"].ToString());
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
