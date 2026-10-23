using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.PlayerTabs;

// A player's page (web/src/routes/(app)/player/[id]; this folder is Pages/Player): the header every
// tab shares, then the tab. It starts from his row in the Players list and his own file, both as
// this visitor may see them; a player who isn't in the current ranks has no page.
public abstract class PlayerPageModel(Database db) : PageModel
{
    const int RecentDays = 45; // latest appearance older than this: not shown as recent form

    protected Database Db { get; } = db;
    protected Visitor Visitor => TheCornerFC.Web.Site.Visitor.Of(HttpContext);
    public int Id { get; private set; }
    public SiteDoc Site { get; private set; } = null!;
    public Player P { get; private set; } = null!;
    public PlayerDoc? Doc { get; private set; }
    // the database held back the paid fields for this visitor (his skill scores among them, even in the free slice)
    public bool Paywall { get; private set; }
    public List<SeasonLine> Lines { get; private set; } = [];
    public List<Appearance> Apps { get; private set; } = [];
    public PlayerPage.SeasonSum? Now { get; private set; }
    public int Year { get; private set; }

    public sealed record Link(int Id, string Name);
    public sealed record Nat(string Name, string? Flag);
    public sealed record RecentApp(int Gf, int Ga, int Goals, int Assists, string Title);
    public sealed record Recent(bool Stale, int? Days, string? LastDate, List<RecentApp> Apps);

    public Link? Team { get; private set; }
    public Link? League { get; private set; }
    public Nat? Nationality { get; private set; }
    public string? Born { get; private set; }
    public int? Rank { get; private set; }
    public string Season { get; private set; } = "";
    public string SeasonName { get; private set; } = "";
    public (int Place, int Of)? LeagueRank { get; private set; }
    public Recent RecentForm { get; private set; } = new(true, null, null, []);

    // a club's name as his file has it (clubs the names row doesn't hold), else the site's
    public string Club(int t) => Doc?.Teams?.GetValueOrDefault(t.ToString()) ?? Site.TeamName(t);

    public async Task<IActionResult> OnGet(string id)
    {
        if (id.Length is 0 or > 9 || !id.All(char.IsAsciiDigit)) return NotFound();
        Id = int.Parse(id);
        Site = await Db.KeptDoc<SiteDoc>("site");
        var answerTask = Db.AskAs<PlayersAnswer>(Visitor.Token, "site_players", new { p_ids = new[] { Id }, p_limit = 1 });
        var docTask = DocOrNull();
        await Task.WhenAll(answerTask, docTask);
        var p = ClubData.Players(Site, answerTask.Result.Rows).FirstOrDefault();
        Paywall = answerTask.Result.Paywall == true;
        if (p is null) return NotFound();
        P = p;
        Doc = docTask.Result;
        Year = Site.PlayerSeasons![0];
        Lines = PlayerFiles.Seasons(Doc);
        Apps = PlayerFiles.Appearances(Doc);
        // his league minutes and stats this season, all his clubs (none yet: zero minutes)
        Now = Doc is null ? null : PlayerPage.Sum(Lines.Where(r => r.Season == Year).ToList()) ?? new(null, null, 0, null, null, null, null);
        if (!Visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        ViewData["Name"] = p.Name;

        var league = p.Team is not null && p.League is { } lg ? Site.LeagueShort(lg) : "";
        var last = Apps.FirstOrDefault();
        int? days = last is null ? null : (int)Math.Floor((DateTimeOffset.UtcNow - DateTimeOffset.Parse(last.Date + "T00:00:00Z")).TotalDays);
        Team = p.Team is { } t ? new(t, Club(t)) : null;
        League = league != "" && p.League is { } l2 ? new(l2, league) : null;
        Nationality = p.Nationality is { } n ? new(n, Names.FlagCodes.GetValueOrDefault(n) ?? Names.FlagCodes.GetValueOrDefault(ClubTable.CountryDisplay(n))) : null;
        Born = Doc?.Born is { } b ? ClubPage.LongDate(b) : null;
        Rank = p.Rank is { } r ? Js.RoundInt(r) : null;
        Season = ClubPage.SeasonShort(Year);
        SeasonName = $"{Year}/{(Year + 1).ToString()[2..]}";
        // his place by Ability among his league's players, counted by the export
        LeagueRank = p.LgN is > 0 && p.LgRank is { } lr ? (lr, p.LgN.Value) : null;
        // Recent Performance: his latest league appearances, dated so old ones aren't read as form
        RecentForm = new(days is null || days > RecentDays, days, last is null ? null : ClubPage.LongDate(last.Date),
            Apps.Take(10).Select(m => new RecentApp(m.Gf, m.Ga, m.Goals, m.Assists,
                $"{ClubPage.ShortDate(m.Date)} {(m.Home != 0 ? "v" : "@")} {Club(m.Opponent)} {m.Gf}–{m.Ga} · {m.Minutes}′{(m.Goals > 0 ? $" · {m.Goals} G" : "")}{(m.Assists > 0 ? $" · {m.Assists} A" : "")}")).ToList());
        return await Load() ?? Page();
    }

    async Task<PlayerDoc?> DocOrNull()
    {
        try { return await Db.AskAs<PlayerDoc?>(Visitor.Token, "site_player_page", new { p_id = Id }); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or System.Text.Json.JsonException) { return null; }
    }

    // the tab's own part; a result in place of the page where it has one
    protected abstract Task<IActionResult?> Load();
}
