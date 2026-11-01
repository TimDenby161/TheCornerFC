using System.Text.Json;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.AdminArea;

// Posts ready for X (Site/XPosts.cs), drawn from what a signed-out visitor can see, so every read
// here is one the public pages already keep. The administrator's only, as all of /admin is.
public sealed class PostsModel(Database db, TimeProvider clock) : PageModel
{
    public List<XPosts.Post> Posts { get; private set; } = [];

    public async Task OnGet()
    {
        ViewData["TabHead"] = TabHead.For("X posts", "posts");
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var rankingsTask = Quiet(db.KeptDoc<Rankings>("rankings"));
        var modelTask = Quiet(db.KeptDocOrNull<ModelDoc>("model", TimeSpan.FromMinutes(5)));
        var recordTask = Quiet(db.KeptAsk<PredictionRecordDoc>("site_prediction_record", new { p_limit = 1, p_offset = 0 }, TimeSpan.FromMinutes(5)));
        var matchesTask = Quiet(db.KeptAsk<MatchesAnswer>("site_matches", new { p_leagues = new[] { XPosts.PremierLeague } }));
        await Task.WhenAll(siteTask, rankingsTask, modelTask, recordTask, matchesTask);
        var site = siteTask.Result;
        var clubs = rankingsTask.Result is { } r ? Clubs.From(r) : [];
        var market = modelTask.Result?.Current?.VsMarket;
        Posts = new[]
        {
            XPosts.Round(site, matchesTask.Result is { } m ? ClubData.MatchRows(site, m) : [], clock.GetUtcNow()),
            XPosts.Movers(site, clubs),
            XPosts.Record(recordTask.Result, market is null ? null : market.ModelLogLoss - market.MarketLogLoss),
            XPosts.Strongest(site, clubs),
        }.OfType<XPosts.Post>().ToList();
    }

    public static string CardJson(XPosts.Card card) => JsonSerializer.Serialize(card, JsonSerializerOptions.Web);

    static async Task<T?> Quiet<T>(Task<T> t) where T : class
    {
        try { return await t; }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { return null; }
    }
}
