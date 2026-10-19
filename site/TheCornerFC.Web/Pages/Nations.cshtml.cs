using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// The national team ranking: the club Elo run over every men's international since 1872
// (web/src/routes/(app)/nations).
public sealed partial class NationsModel(Database db) : PageModel
{
    static readonly string[] Sorts = ["current", "change"];
    public string Sort { get; private set; } = "current";
    public string Confed { get; private set; } = "all";
    public NationsDoc Doc { get; private set; } = null!;
    public string Latest { get; private set; } = "";
    public List<Row> Rows { get; private set; } = [];

    public sealed record Row(string Name, string? Page, string? Flag, string? Confed, int Current, int Tier, int? Change, string Tip);

    public async Task OnGet()
    {
        var docTask = db.KeptDoc<NationsDoc>("nations", TimeSpan.FromMinutes(5));
        // (the Players page's filters' read, kept for both: here, the nationalities the site has players from)
        var facetsTask = Players.Facets(db);
        await Task.WhenAll(docTask, facetsTask);
        var d = Doc = docTask.Result;
        var asked = Request.Query["sort"].ToString();
        Sort = Sorts.Contains(asked) ? asked : "current";
        var c = Request.Query["c"].ToString();
        Confed = NationsDoc.Confeds.Contains(c) ? c : "all";
        var nations = d.Nations.Select(n => (N: n, Change: n.YearAgo is { } y ? n.Current - y : (double?)null)).ToList();
        var worldRank = nations.OrderByDescending(n => n.N.Current).Select((n, i) => (n.N.Name, i + 1)).ToDictionary(x => x.Name, x => x.Item2);
        // the nationality page's name for a nation (the feed's), if the site has players from it
        var nats = facetsTask.Result.Nats.ToHashSet();
        string? PageName(string name) => new[] { name }.Concat(d.Aliases?.GetValueOrDefault(name) ?? []).FirstOrDefault(nats.Contains);
        if (!Visitor.Of(HttpContext).SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        ViewData["TabHead"] = TabHead.For("Nations", "nations");
        Latest = $"{NationsDoc.ShortDate(d.LatestMatch)} {d.LatestMatch[..4]}";
        double Key((NationsDoc.Nation N, double? Change) n) => Sort == "change" ? n.Change ?? double.NegativeInfinity : n.N.Current;
        Rows = nations.Where(n => Confed == "all" || n.N.Confed == Confed)
            .OrderByDescending(Key).ThenByDescending(n => n.N.Current)
            .Select(x =>
            {
                var n = x.N;
                return new Row(n.Name, PageName(n.Name), FlagRe().IsMatch(n.Flag) ? n.Flag : null, n.Confed, Js.RoundInt(n.Current), d.Tier(n.Current),
                    x.Change is { } ch ? Js.RoundInt(ch) : null,
                    $"World #{worldRank[n.Name]} · Last 12 months: {n.W}W {n.D}D {n.L}L · Last match: {n.Last.Gf}–{n.Last.Ga} v {n.Last.Opp} ({n.Last.Comp}, {NationsDoc.ShortDate(n.Last.Date)} {n.Last.Date[..4]}) · {n.Played} internationals rated");
            }).ToList();
    }

    public string Address(string? c = null, string? sort = null)
    {
        c ??= Confed;
        sort ??= Sort;
        var q = new Dictionary<string, string>();
        if (c != "all") q["c"] = c;
        if (sort != "current") q["sort"] = sort;
        return q.Count > 0 ? "?" + Markup.Query(q) : Request.Path.Value!;
    }

    [GeneratedRegex("^[a-z]{2}(-[a-z]{3})?$")] private static partial Regex FlagRe();
}
