using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// What the list's table needs to draw rows: the page and its "more rows" both use it
public sealed record PlayerRowsView(List<PlayerRow> Rows, int Offset, bool Years, List<string> Groups, int[] Seasons, int[] Future);

// Players: every ranked player by Ability, with the competition menu, Exclude, ranges, age,
// position, club and nationality, a search, and a sort on any season (web/src/routes/(app)/players).
// The first 100 rows come with the page; the rest arrive 100 at a time as the list is scrolled
// (/players/rows).
public sealed class PlayersModel(Database db) : PageModel
{
    public Players.Base B { get; private set; } = null!;
    public Players.Choices Ch => B.Choices;
    public int Total { get; private set; }
    public bool Paywall { get; private set; }
    public List<PlayerRow> Rows { get; private set; } = [];
    public Dictionary<string, Slider> Sliders { get; private set; } = [];
    public FilterMenuModel Menu { get; private set; } = null!;
    public List<(int Id, string Name)> Clubs { get; private set; } = [];
    public List<(string Name, string? Flag)> Nats { get; private set; } = [];
    public int[] Seasons => B.Site.PlayerSeasons!;
    public int[] Future => B.Site.PlayerFutureSeasons ?? [];
    // with positions picked, his rank in them takes Ability's place and is the default sort
    public string Now => B.Groups.Count > 0 ? "pos" : $"s{Seasons[0]}";

    public async Task OnGet()
    {
        var visitor = Visitor.Of(HttpContext);
        B = await Players.Load(db, Request.Query);
        var pageTask = Players.Page(db, B, 0, visitor.Token);
        var countsTask = db.KeptAsk<Players.CountsAnswer>("site_players", Players.CountParams(B.Site, Ch));
        await Task.WhenAll(pageTask, countsTask);
        (Total, Paywall, Rows) = pageTask.Result;
        // the same answer for every visitor who isn't signed in: a shared cache may keep it for a minute
        if (!visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";

        Slider Make(string k)
        {
            var stops = Players.RangeStops(k, B.Facets, B.All.Count);
            var r = Ch.Ranges[k];
            return new(stops, Players.StopIndex(stops, r.Lo, 0), Players.StopIndex(stops, r.Hi, 1));
        }
        Sliders = new[] { "age", "ab", "crank", "mins" }.ToDictionary(k => k, Make);
        Clubs = Ch.Clubs.Select(id => (id, B.Site.TeamName(id))).ToList();
        Nats = Ch.Nats.Select(n => (n, Names.FlagCodes.GetValueOrDefault(ClubTable.CountryDisplay(n)))).ToList();
        Menu = ClubTable.Menu(B.Site, B.Countries, Ch.Filter, Players.Counts(countsTask.Result.Counts ?? [], B.Countries, B.Cups), ClubTable.ClubTitles);
        ViewData["TabHead"] = TabHead.For("Players", "players");
    }

    // a slider's range as the address would have it (null: both ends open)
    public string? RangeNow(string k) => Players.RangeText(Players.HandlesRange(Sliders[k].Stops, Sliders[k].A, Sliders[k].B));
    public int RangesOn => Players.RangeKeys.Count(k => RangeNow(k) is not null);
    public int FiltersOn => RangesOn + Ch.ExcludedList.Count + (RangeNow("age") is not null ? 1 : 0) + Ch.Positions.Count + Ch.Clubs.Count + Ch.Nats.Count;

    // The page's choices as they go in the address, a default left out; `without` drops some
    public Dictionary<string, string> Choices(params string[] without)
    {
        // (built in the address's order, leaving out `without`: a key removed from a Dictionary
        // frees a slot the next key added takes, so its order would no longer be the address's)
        var q = new Dictionary<string, string>();
        void Add(string k, string v) { if (!without.Contains(k)) q[k] = v; }
        if (Ch.Filter != "all") Add("c", Ch.Filter);
        if (Ch.ExcludedList.Count > 0) Add("ex", string.Join('|', Ch.ExcludedList));
        if (Ch.Search != "") Add("q", Ch.Search);
        if (Ch.Sort != Now) Add("sort", Ch.Sort);
        foreach (var k in new[] { "ab", "crank", "mins", "age" }) if (RangeNow(k) is { } r) Add(k, r);
        if (Ch.Positions.Count > 0) Add("pos", string.Join(',', Ch.Positions));
        if (Ch.Clubs.Count > 0) Add("club", string.Join(',', Ch.Clubs));
        if (Ch.Nats.Count > 0) Add("nat", string.Join('|', Ch.Nats));
        if (B.Years) Add("y", "1");
        return q;
    }

    public string Address(Dictionary<string, string> q) => q.Count > 0 ? "?" + Markup.Query(q) : Request.Path.Value!;
    public string SortHref(string key)
    {
        var q = Choices("sort");
        if (key != Now) q["sort"] = key;
        return Address(q);
    }
    // the + / − beside Ability: open or close the other seasons (closing drops a sort on one of them)
    public string YearsHref()
    {
        if (!B.Years) { var q = Choices(); q["y"] = "1"; return Address(q); }
        return Address(System.Text.RegularExpressions.Regex.IsMatch(Ch.Sort, "^[sf][0-9]") ? Choices("y", "sort") : Choices("y"));
    }
    public string PosToggled(string pos) =>
        string.Join(',', Ch.Positions.Contains(pos) ? Ch.Positions.Where(x => x != pos) : Ch.Positions.Append(pos));

    public PlayerRowsView RowsView => new(Rows, 0, B.Years, B.Groups, Seasons, Future);
    public bool Wide => Ch.Search != "" || Ch.Filter == "all" || !Ch.Filter.All(char.IsAsciiDigit);
}

// The next rows of the Players list, as it is scrolled: the page's own address with ?offset=,
// answered as table rows ready to add
public sealed class PlayerRowsModel(Database db) : PageModel
{
    public async Task<IActionResult> OnGet()
    {
        var visitor = Visitor.Of(HttpContext);
        var offset = int.TryParse(Request.Query["offset"], out var o) ? Math.Clamp(o, 0, 100_000) : 0;
        var b = await Players.Load(db, Request.Query);
        var (_, _, rows) = await Players.Page(db, b, offset, visitor.Token);
        Response.Headers.CacheControl = visitor.Token is not null ? "private, no-store" : "public, max-age=60";
        return Partial("_PlayerRows", new PlayerRowsView(rows, offset, b.Years, b.Groups, b.Site.PlayerSeasons!, b.Site.PlayerFutureSeasons ?? []));
    }
}
