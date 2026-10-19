using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// Home: what the site is, for a visitor who isn't signed in, with a slide for each part of the site
// (web/src/routes/(app)/+page). A signed-in visitor arriving at the bare address goes on to Clubs,
// as on the old site; the site's name in the menu still opens Home for them (a link from one of the
// site's own pages). The example line-up's slide is asked for once the page is up (/home/xi): it can
// need the reconstructed history, which the database takes seconds over.
public sealed class IndexModel(Database db, TimeProvider clock) : PageModel
{
    public int ClubCount { get; private set; }
    public List<Home.ClubRow> Clubs { get; private set; } = [];
    public List<Home.PlayerRow>? Players { get; private set; }
    public Home.Calls? Calls { get; private set; }
    public Home.StatsSlide? Stats { get; private set; }
    public List<Home.LeagueRow> Leagues { get; private set; } = [];
    public List<Home.NationRow>? Nations { get; private set; }
    public bool SignedIn { get; private set; }

    public async Task<IActionResult> OnGet()
    {
        var visitor = Visitor.Of(HttpContext);
        SignedIn = visitor.SignedIn;
        var from = Request.Headers.Referer.ToString();
        if (SignedIn && !(Uri.TryCreate(from, UriKind.Absolute, out var r) && r.GetLeftPart(UriPartial.Authority) == $"{Request.Scheme}://{Request.Host}"))
            return Redirect("/clubs");
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var docTask = db.KeptDoc<Rankings>("rankings");
        await Task.WhenAll(siteTask, docTask);
        var site = siteTask.Result;
        var all = Data.Clubs.From(docTask.Result);
        var now = clock.GetUtcNow();
        var playersTask = Home.Players(db, site);
        var callsTask = Home.MatchCalls(db, site, all, visitor.Zone.Tz, now);
        var statsTask = Home.Stats(db);
        var nationsTask = Home.Nations(db);
        await Task.WhenAll(playersTask, callsTask, statsTask, nationsTask);
        (Players, Calls, Stats, Nations) = (playersTask.Result, callsTask.Result, statsTask.Result, nationsTask.Result);
        ClubCount = all.Count;
        Clubs = Home.Clubs(site, all);
        Leagues = Home.Leagues(site, all);
        if (!SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        return Page();
    }
}

// Home's example line-up, as its slide, for the page to add once it arrives (nothing: no slide)
public sealed class HomeXiModel(Database db, TimeProvider clock) : PageModel
{
    public async Task<IActionResult> OnGet()
    {
        var visitor = Visitor.Of(HttpContext);
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var docTask = db.KeptDoc<Rankings>("rankings");
        await Task.WhenAll(siteTask, docTask);
        Home.XiSlide? xi;
        try { xi = await Home.Xi(db, siteTask.Result, Data.Clubs.From(docTask.Result), visitor.Zone.Tz, clock.GetUtcNow()); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or System.Text.Json.JsonException) { xi = null; }
        // a part of Home, not a page of its own
        Response.Headers["X-Robots-Tag"] = "noindex";
        if (!visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        return xi is null ? StatusCode(204) : Partial("_HomeXi", xi);
    }
}
