using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.AdminArea;

// The Model Change Tracker (web/src/routes/(app)/admin/changes): the figures at the top, the model
// comparison with the switch, and the changes not yet in production against the current version.
// The administrator's only (the gate, Site/Admin.cs, and the database again for the documents).
// (its switch is a form: posts are checked by where they come from, Site/Sessions.cs)
[IgnoreAntiforgeryToken]
public sealed class ChangesModel(Database db) : PageModel
{
    // A18's own record, and the results file of its test on past matches against the released club rank
    const string A18 = "MC-0018", A18Past = "experiments/a18_on_release/results.json";

    public sealed record Versus(MatchModels.Scores? Scores, string? Start, MatchModels.Past PastScores, List<MatchModels.Apart> Apart);
    public sealed record LiveSummary(int N, int Weeks, string Start, string? To, string? Generated, int Tracked, string Protocol, int Matches, int MinWeeks);

    public bool Ready { get; private set; }
    public ModelDoc Doc { get; private set; } = null!;
    public List<ModelRecord.Tile> Tiles { get; private set; } = [];
    public List<ModelRecord.DeltaRow> Deltas { get; private set; } = [];
    public TheCornerFC.Web.Site.Admin.MatchModel? Model { get; private set; }
    public Versus? Vs { get; private set; }
    public LiveSummary? Live { get; private set; }
    public string Refused { get; private set; } = "";

    async Task<IActionResult> Load()
    {
        ViewData["TabHead"] = TabHead.For("Model Change Tracker", "changes");
        var token = Visitor.Of(HttpContext).Token;
        var docTask = TheCornerFC.Web.Site.Admin.Doc<ModelDoc>(db, token, "model_changes");
        var liveTask = TheCornerFC.Web.Site.Admin.Doc<ModelDoc.LiveDoc>(db, token, "live_tracking");
        var modelTask = TheCornerFC.Web.Site.Admin.LiveModel(db, token);
        var compareTask = TheCornerFC.Web.Site.Admin.Compare(db, token);
        await Task.WhenAll(docTask, liveTask, modelTask, compareTask);
        // (anyone the database won't hand the documents to is told the page isn't there)
        if (docTask.Result.Refused || liveTask.Result.Refused) return NotFound();
        if (docTask.Result.Doc is not { } doc) return Page();
        Ready = true;
        Doc = doc;
        var live = liveTask.Result.Doc;
        Tiles = ModelRecord.ScoreTiles(doc);
        Model = modelTask.Result;
        var compare = compareTask.Result;
        // The model comparison above the switch: the bookmakers, the base model and A18 on A18's test
        // on past matches (its change record) and on the same finished live matches, and where the two
        // models part on the fixtures to come.
        if (Model is not null)
            Vs = new(compare is { } c ? MatchModels.ScoreRows(c.GetProperty("finished")) : null,
                compare is { } c2 && c2.TryGetProperty("start", out var st) ? st.GetString() : null,
                MatchModels.PastRows((doc.Changes.FirstOrDefault(x => x.Id == A18)?.Results ?? []).Where(r => r.Source == A18Past).ToList()),
                compare is { } c3 ? c3.GetProperty("apart").EnumerateArray().Select(MatchModels.ApartRow).ToList() : []);
        // the table is for deciding what to add, so changes already in production, themselves or
        // inside a release, are left out of it
        Deltas = ModelRecord.DeltaRows(doc.Changes.Where(x => !ModelRecord.InProduction(x)).ToList(), "log_loss", live);
        if (live is not null)
            Live = new(live.N, live.Weeks, live.Start, live.To, live.GeneratedAt, live.Changes.Count, live.Protocol, live.Minimum.Matches, live.Minimum.Weeks);
        return Page();
    }

    public Task<IActionResult> OnGet() => Load();

    // The switch: which match model the site and the paper bets use, from the next run of the
    // predictions. The database checks the caller is an administrator and logs every switch.
    public async Task<IActionResult> OnPostSwitch()
    {
        var live = Request.Form["live"].ToString();
        if (!TheCornerFC.Web.Site.Admin.MatchModels.Contains(live)) { Refused = "That is not one of the two models."; Response.StatusCode = 400; return await Load(); }
        if (await TheCornerFC.Web.Site.Admin.SwitchModel(db, Visitor.Of(HttpContext).Token, live) is null) { Refused = "The switch was refused, or is not there yet."; Response.StatusCode = 403; return await Load(); }
        return Redirect("/admin/changes");
    }
}
