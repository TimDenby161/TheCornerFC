using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.ClubTabs;

// A club's page (web/src/routes/(app)/club/[id]; this folder is Pages/Club): the header every tab shares (rating, form, its
// slice of the league table, best players, style), then the tab.
public abstract class ClubPageModel(Database db) : PageModel
{
    protected Database Db { get; } = db;
    public ClubBase C { get; private set; } = null!;
    protected Visitor Visitor => TheCornerFC.Web.Site.Visitor.Of(HttpContext);

    public sealed record LeagueLink(int Id, string Name, string CountryKey, string Country);
    public sealed record Rating(int Place, int? Form, int Lt, int LtTier, int Current, int CurrentTier);
    public sealed record FormDot(char C, string Title);
    public sealed record TableLine(int Team, bool Me, string Name, int Rank, int? Played, int? Gd, int? Points, string? Form, string Zone);
    public sealed record MiniTable(int League, string Title, List<TableLine> Rows);
    public sealed record Best(int Id, string Name, string Short, string? Position, double? Rank, int? Goals, int? Assists);

    public LeagueLink? League { get; private set; }
    public string? Coach { get; private set; }
    public Rating? Ratings { get; private set; }
    public List<FormDot> Form { get; private set; } = [];
    public MiniTable? Table { get; private set; }
    public (int X, string Text)? Style { get; private set; }
    public List<Best> BestPlayers { get; private set; } = [];

    public async Task<IActionResult> OnGet(string id)
    {
        var c = await ClubBase.Load(Db, id);
        if (c is null) return NotFound();
        C = c;
        ViewData["Name"] = c.Name;
        var r = c.Rank;
        var site = c.Site;
        var comp = r is null ? null : site.Comp(r.League);
        // the club's five best players by Ability: the export's order is by current rank, and a
        // player whose rank is hidden (the paywall) keeps his place in it
        List<Player> players;
        try { players = (await c.Players(Db, Visitor.Token)).List; }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException) { players = []; }
        BestPlayers = players.Where(p => p.Rank is not null || p.Locked)
            .OrderBy(p => p.Ord ?? 1e9).ThenBy(p => p.Name, Js.Compare).Take(5)
            .Select(p => new Best(p.Id, p.Name, ClubPage.ShortName(p.Name), p.Position, p.Rank, p.Season?.Goals, p.Season?.Assists)).ToList();
        var lg = r?.InLeague == true ? await LeagueFileOrNull(r.League) : null;
        if (!Visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";

        if (comp is not null && r is not null)
            League = new(r.League, site.LeagueShort(r.League) is { Length: > 0 } s ? s : site.CompLabel(r.League), comp.Country, ClubTable.CountryDisplay(comp.Country));
        Coach = c.Doc?.Coach?.Name;
        if (r is not null)
            Ratings = new(c.All.Count(x => x.Current > r.Current) + 1, r.Form is { } f ? Js.RoundInt(f) : null,
                Js.RoundInt(r.Lt), Clubs.Tiers(c.All, "lt")(r.Lt), Js.RoundInt(r.Current), Clubs.Tiers(c.All, "current")(r.Current));
        // recent form: results in all competitions, newest first
        Form = c.Rows.TakeLast(40).Reverse().Select(m => new FormDot(ClubPage.Result(m.Gf, m.Ga),
            $"{ClubPage.ShortDate(m.Date)} · {m.Gf}–{m.Ga} {(m.Home != 0 ? "v" : "@")} {c.Opponent(m.Opponent)} · {site.CompLabel(m.League)}")).ToList();

        // The club's slice of its league table: it and the two clubs either side (five rows,
        // shifted at the top and bottom), in the club's own group
        if (lg is not null && r is not null)
        {
            var tableRows = LeagueFiles.TableRows(lg);
            var me = tableRows.FirstOrDefault(t => t.Team == c.Id);
            if (me is not null)
            {
                var zones = Leagues.Zones(tableRows.Select(t => t.Description));
                var group = tableRows.Where(t => t.Group == me.Group).ToList();
                var i = group.IndexOf(me);
                var start = Math.Max(0, Math.Min(i - 2, group.Count - 5));
                var league = site.LeagueShort(r.League) is { Length: > 0 } ls ? ls : site.CompLabel(r.League);
                Table = new(r.League, me.Group is { Length: > 0 } g && g != site.Comp(r.League)?.Name ? $"{league} · {g}" : league,
                    group.Skip(start).Take(5).Select(t => new TableLine(t.Team, t == me, lg.Teams?.GetValueOrDefault(t.Team.ToString()) ?? site.TeamName(t.Team),
                        t.Rank, t.Played, t.Gd, t.Points, t.Form, Leagues.ZoneOf(zones, t.Description))).ToList());
            }
        }

        // Style: the lean between attack and defence. The ends of the meter are the most one-sided
        // clubs in the world
        if (r is { Attack: { } att, Defence: { } dfn })
        {
            var max = Math.Max(1, c.All.Where(x => x.Attack is not null && x.Defence is not null).Select(x => Math.Abs(x.Attack!.Value - x.Defence!.Value) / 2).DefaultIfEmpty(0).Max());
            var lean = (att - dfn) / 2;
            var k = Js.RoundInt(lean);
            Style = (ClubPage.Pct(50 + 50 * Math.Max(-1, Math.Min(1, lean / max))), k == 0 ? "Balanced" : $"{(k > 0 ? "Attacking" : "Defensive")} +{Math.Abs(k)}");
        }
        return await Load() ?? Page();
    }

    async Task<LeagueFile?> LeagueFileOrNull(int league)
    {
        try { return await Db.KeptDocOrNull<LeagueFile>($"leagues/{league}", TimeSpan.FromMinutes(5)); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or System.Text.Json.JsonException) { return null; }
    }

    // the tab's own part; a result in place of the page where it has one
    protected abstract Task<IActionResult?> Load();

    public static string Signed(int v) => $"{(v > 0 ? "+" : v < 0 ? "−" : "")}{Math.Abs(v)}";
}
