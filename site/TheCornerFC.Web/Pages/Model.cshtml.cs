using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// The Model (owner's decision 2026-10-16, the most transparent model): the live model's record and
// every change to it, in public (web/src/routes/(app)/model). The nightly export writes it. The
// model switch and where the two models part on matches to come stay in the Admin area.
public sealed class ModelModel(Database db) : PageModel
{
    public sealed record Example(string Home, string Away, string? Competition, string Kickoff, int? Hg, int? Ag, MatchDetail.Detail Detail);
    public sealed record Live(int N, int Weeks, string Start, int Tracked, string Protocol, int Matches, int MinWeeks);

    public bool Ready { get; private set; }
    public string Generated { get; private set; } = "";
    public string? Version { get; private set; }
    public List<ModelRecord.Tile> Tiles { get; private set; } = [];
    public List<ModelRecord.Card> InModel { get; private set; } = [];
    public List<ModelRecord.Card> Tried { get; private set; } = [];
    public int Registered { get; private set; }
    public Example? Worked { get; private set; }
    public Live? LiveTests { get; private set; }

    public async Task OnGet()
    {
        ViewData["TabHead"] = TabHead.For("The Model", "model");
        if (!Visitor.Of(HttpContext).SignedIn) Response.Headers.CacheControl = "public, max-age=300";
        var docTask = db.KeptDocOrNull<ModelDoc>("model", TimeSpan.FromMinutes(5));
        var siteTask = db.KeptDoc<SiteDoc>("site");
        await Task.WhenAll(docTask, siteTask);
        if (docTask.Result is not { } doc) return;
        Ready = true;
        Generated = doc.GeneratedAt;
        Version = doc.Current?.Version;
        Tiles = ModelRecord.ScoreTiles(doc);
        var live = doc.Tracking;
        // every change with a result: what is in the model now, then what was tried and where it
        // stands. The Admin area's notes speak to the owner deciding what to release, and point to
        // pages only it has: here a change in the model just says so
        var rows = ModelRecord.DeltaRows(doc.Changes, "log_loss", live).Select(d =>
        {
            var inModel = ModelRecord.InProduction(doc.Changes.First(x => x.Id == d.Id));
            var note = inModel ? "In the model" : d.ReadyNote.EndsWith(": see why on its page") ? d.ReadyNote[..^": see why on its page".Length] : d.ReadyNote;
            return (Row: d with { ReadyNote = note }, InModel: inModel);
        }).ToList();
        var cards = ModelRecord.Cards(doc.Changes, rows.Select(r => r.Row).ToList(), live, doc.Current?.LogLoss);
        InModel = cards.Where((_, i) => rows[i].InModel).ToList();
        Tried = cards.Where((_, i) => !rows[i].InModel).ToList();
        Registered = doc.Changes.Count;
        // one finished match worked through step by step (site_matches.worked_example)
        if (doc.Example is { Why.Steps: not null } ex)
        {
            var m = ModelRecord.ExampleMatch(siteTask.Result, ex.Match);
            string home = ex.HomeName is { Length: > 0 } h ? h : "Home", away = ex.AwayName is { Length: > 0 } a ? a : "Away";
            Worked = new(home, away, ex.Competition, m.Kickoff, m.Hg, m.Ag, MatchDetail.Of(m, ex.Why, null, home, away));
        }
        if (live is not null)
            LiveTests = new(live.N, live.Weeks, live.Start, live.Changes.Count, live.Protocol, live.Minimum.Matches, live.Minimum.Weeks);
    }
}
