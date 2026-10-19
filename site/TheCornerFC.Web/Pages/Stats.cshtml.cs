using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// Stats: how the model's match predictions have done against results, by range and competition,
// and against the bookmakers (web/src/routes/(app)/stats)
public sealed class StatsModel(Database db) : PageModel
{
    public sealed record Gap(string Text, string Cls);
    public sealed record Pair(string Model, string Market, bool ModelBetter, bool MarketBetter);
    public sealed record MarketLine(int N, bool Small, Pair Right, Pair Ll);
    public sealed record BetMarket(string Label, int N, string Model, string Close, Gap? Gap, (Gap? Gap, int N)? Open);
    public sealed record Band(string Name, double Count, string Said, string Hit, int Bar, string Cls);
    public sealed record Dist(int R, string Label, int Share, string Pct);
    public sealed record FactorLine(string Label, string Weight, string Value, int Share);
    public sealed record RatingView(string Avg, string Label, List<Dist> Dist, List<FactorLine> Factors);
    public sealed record View(List<(string Label, string Value, string Note)> Cards, MarketLine? Market, List<BetMarket> Markets, List<Band> Calibration, RatingView? Rating);

    public string Filter { get; private set; } = "all";
    public string Range { get; private set; } = "30d";
    public FilterMenuModel Menu { get; private set; } = null!;
    public View? S { get; private set; }

    static readonly MenuTitles Titles = new(
        "All competitions", c => $"All {c} competitions", r => $"All competitions in {r}",
        "Champions League, Europa League and Conference League", n => n,
        Intl: "National team matches: World Cup, qualifiers, Nations League, friendlies and others");
    static readonly Dictionary<int, string> RatingLabels = new() { [1] = "Terrible", [2] = "Poor", [3] = "Decent", [4] = "Very good", [5] = "Excellent" };
    static readonly (string Key, string Label, string Weight)[] Factors = [("winner", "Winner", "30%"), ("margin", "Margin", "25%"), ("clean_sheets", "Clean sheets", "20%"), ("shape", "Shape", "15%"), ("goals", "Goals", "10%")];
    static string Pct(double x, int d = 1) => Home.PctText(x, d);

    public async Task OnGet()
    {
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var docTask = db.KeptDoc<StatsDoc>("stats", TimeSpan.FromMinutes(5));
        await Task.WhenAll(siteTask, docTask);
        var (site, doc) = (siteTask.Result, docTask.Result);
        // every competition with stats in any range, so the menu stays put when the range changes
        var ids = doc.Ranges.Values.SelectMany(r => r.Keys).Where(k => k.Length > 0 && k.All(char.IsAsciiDigit)).Distinct().Select(int.Parse).ToList();
        int N(int id) => doc.Ranges.GetValueOrDefault("365d")?.GetValueOrDefault(id.ToString())?.N ?? 0;
        var countries = Matchday.CompCountries(site, ids);
        var intl = ids.Where(id => site.Comp(id)?.Type == "International").OrderByDescending(N).ThenBy(id => id).ToList();
        var q = Request.Query;
        var c = q["c"].ToString();
        Filter = Matchday.KnownFilter(c, site, countries) ? c : "all";
        var r = q["r"].ToString();
        Range = StatsFigures.Ranges.Any(x => x.Key == r) ? r : "30d";
        Menu = ClubTable.Menu(site, countries, Filter, null, Titles, intl);
        if (!Visitor.Of(HttpContext).SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        ViewData["TabHead"] = TabHead.For("Stats", "stats");
        var all = doc.Ranges.GetValueOrDefault(Range);
        var picked = Matchday.FilterComps(Filter, countries, intl);
        var s = all is null ? null : picked is not null
            ? StatsFigures.Merge(picked.Select(id => all.GetValueOrDefault(id.ToString())).Where(x => x is not null).Select(x => x!).ToList())
            : all.GetValueOrDefault("all");
        if (s is not null) S = ViewOf(s);
    }

    static View ViewOf(StatsDoc.Stats s)
    {
        var rc = s.RatingCounts ?? [0, 0, 0, 0, 0];
        var rated = rc.Sum(x => x ?? 0);
        var mk = s.Market;
        static bool Better(double? a, double? b, bool lower = false) => a is { } x && b is { } y && (lower ? x < y : x > y);
        static Gap? GapOf(double? model, double? book)
        {
            if (model is not { } m || book is not { } b) return null;
            var d = m - b;
            return new($"{(d > 0 ? "+" : "")}{Js.ToFixed(d, 3)}", d < 0 ? "pos" : d > 0 ? "neg" : "");
        }
        return new(
            [
                ("Matches", Js.Num(s.N), s.Live == s.N ? "All recorded before kickoff" : s.Live == 0 ? "Reconstructed from pre-match data" : $"{Js.Num(s.Live)} recorded before kickoff, rest reconstructed"),
                ("Right result", Pct(s.Correct ?? 0), $"Picking the home team every time: {Pct(s.HomeRate ?? 0)}"),
                ("Exact score", Pct(s.Exact ?? 0), "Most likely scoreline was spot on"),
                ("Goal error", Js.ToFixed(s.GoalError ?? 0, 2), "Average goals off per team"),
                ("Log loss", Js.ToFixed(s.LogLoss ?? 0, 3), "Lower is better. Guessing ≈ 1.07"),
                ("Brier score", Js.ToFixed(s.Brier ?? 0, 3), "Lower is better. Guessing ≈ 0.64"),
            ],
            mk is null ? null : new(mk.N, mk.N < 1000,
                new(Pct(mk.ModelCorrect ?? 0), Pct(mk.MarketCorrect ?? 0), Better(mk.ModelCorrect, mk.MarketCorrect), Better(mk.MarketCorrect, mk.ModelCorrect)),
                new(Js.ToFixed(mk.ModelLl ?? 0, 3), Js.ToFixed(mk.MarketLl ?? 0, 3), Better(mk.ModelLl, mk.MarketLl, true), Better(mk.MarketLl, mk.ModelLl, true))),
            // the model against the market in every bet market: log loss on the same matches against
            // the closing prices, and against opening prices where the odds were first seen before kickoff
            mk is null || s.Markets is null ? [] : StatsFigures.MarketKeys.Where(k => s.Markets.ContainsKey(k)).Select(k =>
            {
                var m = s.Markets[k];
                return new BetMarket(StatsFigures.MarketLabels[k], m.N, Js.ToFixed(m.ModelLl ?? 0, 3), Js.ToFixed(m.CloseLl ?? 0, 3), GapOf(m.ModelLl, m.CloseLl),
                    m.OpenN != 0 ? (GapOf(m.ModelOpenLl, m.OpenLl), m.OpenN) : null);
            }).ToList(),
            (s.Calibration ?? []).Select((b, i) => (b, i)).Where(t => t.b[0] is { } n && n != 0 && t.b[1] is not null && t.b[2] is not null).Select(t =>
            {
                double count = t.b[0]!.Value, said = t.b[1]!.Value, hit = t.b[2]!.Value;
                return new Band($"{t.i * 10}–{t.i * 10 + 10}%", count, Pct(said), Pct(hit), Js.RoundInt(hit * 60),
                    Math.Abs(hit - said) <= 0.03 ? "gap-ok" : Math.Abs(hit - said) > 0.06 ? "gap-off" : "");
            }).ToList(),
            rated == 0 || s.RatingAvg is not { } avg ? null : new(Js.ToFixed(avg, 2), RatingLabels.GetValueOrDefault(Js.RoundInt(avg), ""),
                new[] { 5, 4, 3, 2, 1 }.Select(r => new Dist(r, $"{r} {RatingLabels[r]}", Js.RoundInt(100 * (rc[r - 1] ?? 0) / rated), Pct((rc[r - 1] ?? 0) / rated, 0))).ToList(),
                s.FactorAvgs is { } fa ? Factors.Select(f => new FactorLine(f.Label, f.Weight, Js.ToFixed(fa[f.Key], 2), Js.RoundInt(fa[f.Key] / 5 * 100))).ToList() : []));
    }

    public string Address(string r)
    {
        var q = new Dictionary<string, string>();
        if (Filter != "all") q["c"] = Filter;
        if (r != "30d") q["r"] = r;
        return q.Count > 0 ? "?" + Markup.Query(q) : Request.Path.Value!;
    }
}
