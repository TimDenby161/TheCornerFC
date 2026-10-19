using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// Clubs: every club ranked by strength, filtered by competition, country or region, with Exclude
// and a search, sorted by any rating column (web/src/routes/(app)/clubs).
public sealed class ClubsModel(Database db) : PageModel
{
    public static readonly string[] Sorts = ["lt", "trend", "current", "form"];

    public string Sort { get; private set; } = "current";
    public string Filter { get; private set; } = "all";
    public string Search { get; private set; } = "";
    public bool Wide { get; private set; }
    public FilterMenuModel Menu { get; private set; } = null!;
    public List<string> Excluded { get; private set; } = [];
    public List<Row> Rows { get; private set; } = [];

    public sealed record Row(int Team, string Name, string? Short, int League, string LeagueName, string CountryKey, string Country,
        Place Place, int Lt, int LtTier, int Current, int CurrentTier, int Trend, int? Form);

    public async Task OnGet()
    {
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var docTask = db.KeptDoc<Rankings>("rankings");
        var cupsTask = Cups.Load(db);
        await Task.WhenAll(siteTask, docTask, cupsTask);
        var site = siteTask.Result;
        var all = Clubs.From(docTask.Result);
        var countries = ClubTable.Countries(site, all);

        var q = Request.Query;
        var asked = q["sort"].ToString();
        // (the table opens sorted by Current Strength, as on the old site)
        Sort = Sorts.Contains(asked) ? asked : "current";
        Filter = ClubTable.KnownFilter(q["c"], countries) ? q["c"].ToString() : "all";
        var excluded = q["ex"].ToString().Split('|').Where(ClubTable.IsExcludeKey).ToHashSet();
        Excluded = excluded.ToList();
        var search = q["q"].ToString();
        Search = search.Length > 80 ? search[..80] : search;

        var (rows, wide) = ClubTable.Rows(site, all, countries, cupsTask.Result, new(Filter, excluded, Search, Sort));
        Wide = wide;
        Menu = ClubTable.Menu(site, countries, Filter, ClubTable.Counts(site, all, countries, cupsTask.Result, excluded), ClubTable.ClubTitles);
        var places = Clubs.Places(all);
        var baseTier = Clubs.Tiers(all, "lt");
        var currentTier = Clubs.Tiers(all, "current");
        // the same answer for every visitor: a shared cache may keep it for a minute
        if (!Visitor.Of(HttpContext).SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        ViewData["TabHead"] = TabHead.For("Clubs", "clubs");

        Rows = rows.Select(r =>
        {
            var comp = site.Comp(r.League);
            return new Row(r.Team, site.TeamName(r.Team), Names.ClubShort.GetValueOrDefault(r.Team), r.League, site.LeagueShort(r.League),
                comp?.Country ?? "", comp is null ? "" : ClubTable.CountryDisplay(comp.Country), places[r.Team],
                Js.RoundInt(r.Lt), baseTier(r.Lt), Js.RoundInt(r.Current), currentTier(r.Current), r.Trend,
                r.Form is { } f ? Js.RoundInt(f) : null);
        }).ToList();
    }

    // The page's choices as they go in the address, a default left out; `without` drops some
    public Dictionary<string, string> Choices(params string[] without)
    {
        var all = new Dictionary<string, string>();
        if (Filter != "all") all["c"] = Filter;
        if (Excluded.Count > 0) all["ex"] = string.Join('|', Excluded);
        if (Search != "") all["q"] = Search;
        if (Sort != "current") all["sort"] = Sort;
        foreach (var k in without) all.Remove(k);
        return all;
    }

    public string Address(Dictionary<string, string> q) => q.Count > 0 ? "?" + Markup.Query(q) : Request.Path.Value!;
}
