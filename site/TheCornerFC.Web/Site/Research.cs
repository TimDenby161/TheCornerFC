using System.Net;
using System.Text;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// The Admin area's research dashboard (/admin/research): accuracy month by month for a competition,
// how well its stated chances match what happened, the model against the bookmakers in every
// competition, and every challenger's running score on live matches; The Model shows the same in
// public (owner, 2026-10-21: the most transparent model). Read from the "stats"
// document (export_stats in thecornerfc/publish/site_record.py) and the live tests (the
// administrator's "live_tracking", or its public copy in the "model" document): nothing new is
// asked of the database.
public static class Research
{
    // ---- the three accuracy sections, for the competition picked (?c=): shared by the dashboard and
    // The Model (/model), which shows them in public: the "stats" document is the Stats page's
    public sealed record Accuracy(string Pick, string PickName, List<(string Key, string Name)> Choices, bool HasMonths, List<MonthRow> Months,
        (string Right, string LogLoss)? Charts, List<Band> Bands, string? Reliability, List<VsRow> VsMarket);
    public static Accuracy AccuracyOf(StatsDoc? stats, SiteDoc site, string requested)
    {
        string Name(string key) => key == "all" ? "All competitions" : key == "eng" ? "English competitions" : int.TryParse(key, out var id) ? site.LeagueName(id) : key;
        if (stats is null) return new("all", Name("all"), [], false, [], null, [], null, []);
        var year = stats.Ranges.GetValueOrDefault("365d") ?? [];
        // every competition with a year's record, the most matches first
        var choices = year.OrderBy(kv => kv.Key == "all" ? 0 : kv.Key == "eng" ? 1 : 2).ThenByDescending(kv => kv.Value.N).ThenBy(kv => kv.Key, StringComparer.Ordinal)
            .Select(kv => (kv.Key, $"{Name(kv.Key)} ({Js.Num(kv.Value.N)})")).ToList();
        var pick = year.ContainsKey(requested) ? requested : "all";
        var bands = Bands(year.GetValueOrDefault(pick));
        return new(pick, Name(pick), choices, stats.MonthsOf(pick) is not null, Months(stats, pick), MonthCharts(stats, pick),
            bands, bands.Count > 0 ? ReliabilitySvg(bands) : null, AgainstMarket(stats, Name));
    }

    static string Pct(double? x) => x is { } v ? $"{Js.ToFixed(100 * v, 1)}%" : "–";
    static string Ll(double? x) => x is { } v ? Js.ToFixed(v, 3) : "–";
    static string Signed(double v) => $"{(v > 0 ? "+" : v < 0 ? "−" : "")}{Js.ToFixed(Math.Abs(v), 3)}";
    static string Tone(double gap) => gap < 0 ? "pos" : gap > 0 ? "neg" : "";

    // ---- accuracy month by month
    public sealed record MonthRow(string Month, int N, string Right, string LogLoss, int Priced, string ModelLl, string MarketLl, string? Gap, string GapCls,
        string ModelRight, string MarketRight);
    public static List<MonthRow> Months(StatsDoc doc, string key) =>
        (doc.MonthsOf(key) ?? []).Select(m =>
        {
            var mk = m.Market;
            double? gap = mk is { ModelLl: { } a, MarketLl: { } b } ? a - b : null;
            return new MonthRow(m.Key, m.N, Pct(m.Correct), Ll(m.LogLoss), mk?.N ?? 0, Ll(mk?.ModelLl), Ll(mk?.MarketLl),
                gap is { } g ? Signed(g) : null, gap is { } g2 ? Tone(g2) : "", Pct(mk?.ModelCorrect), Pct(mk?.MarketCorrect));
        }).ToList();

    // the months as two charts: % right, and log loss beside the bookmakers' on the priced matches
    public static (string Right, string LogLoss)? MonthCharts(StatsDoc doc, string key)
    {
        var months = doc.MonthsOf(key) ?? [];
        if (months.Count == 0) return null;
        var right = new List<ChangeLines.Series> { new("Model, right results", "live", months.Where(m => m.Correct is not null).Select(m => new ChangeLines.Point(m.Key, 100 * m.Correct!.Value, $"{m.N} matches")).ToList()) };
        var priced = months.Where(m => m.Market is { N: > 0, MarketCorrect: not null }).ToList();
        if (priced.Count > 0) right.Add(new("Bookmakers' favourite, on priced matches", "recon", priced.Select(m => new ChangeLines.Point(m.Key, 100 * m.Market!.MarketCorrect!.Value, $"{m.Market.N} priced")).ToList()));
        var ll = new List<ChangeLines.Series> { new("Model, every match", "live", months.Where(m => m.LogLoss is not null).Select(m => new ChangeLines.Point(m.Key, m.LogLoss!.Value, $"{m.N} matches")).ToList()) };
        var pricedLl = months.Where(m => m.Market is { N: > 0, ModelLl: not null, MarketLl: not null }).ToList();
        if (pricedLl.Count > 0)
        {
            ll.Add(new("Model, priced matches", "model-priced", pricedLl.Select(m => new ChangeLines.Point(m.Key, m.Market!.ModelLl!.Value, $"{m.Market.N} priced")).ToList()));
            ll.Add(new("Bookmakers, priced matches", "recon", pricedLl.Select(m => new ChangeLines.Point(m.Key, m.Market!.MarketLl!.Value, $"{m.Market.N} priced")).ToList()));
        }
        return (ChangeLines.Svg(right, "Right results by month, %", 0), ChangeLines.Svg(ll, "Log loss by month, lower is better", 3));
    }

    // ---- reliability: each band of stated chance (0–10%, 10–20% ...) at its average said, against
    // how often it happened, beside the line where the two are equal
    public sealed record Band(string Name, double Count, double Said, double Hit);
    public static List<Band> Bands(StatsDoc.Stats? s) =>
        (s?.Calibration ?? []).Select((b, i) => (b, i)).Where(t => t.b[0] is { } n && n != 0 && t.b[1] is not null && t.b[2] is not null)
            .Select(t => new Band($"{t.i * 10}–{t.i * 10 + 10}%", t.b[0]!.Value, t.b[1]!.Value, t.b[2]!.Value)).ToList();
    public static string ReliabilitySvg(List<Band> bands)
    {
        const int S = 320, P = 40;
        static string F(double v) => Js.ToFixed(v, 1);
        double X(double v) => P + v * (S - 2 * P);
        double Y(double v) => S - P - v * (S - 2 * P);
        var max = bands.Count > 0 ? bands.Max(b => b.Count) : 1;
        var svg = new StringBuilder($"<figure class=\"mc-chart rs-reliability\"><svg viewBox=\"0 0 {S} {S}\" role=\"img\" aria-label=\"Reliability: chance said against how often it happened\"><g class=\"chart-grid\">");
        foreach (var v in new[] { 0, 0.25, 0.5, 0.75, 1.0 })
            svg.Append($"<line x1=\"{P}\" x2=\"{S - P}\" y1=\"{F(Y(v))}\" y2=\"{F(Y(v))}\" /><line y1=\"{P}\" y2=\"{S - P}\" x1=\"{F(X(v))}\" x2=\"{F(X(v))}\" />");
        svg.Append("</g><g class=\"chart-axis\">");
        foreach (var v in new[] { 0, 0.25, 0.5, 0.75, 1.0 })
            svg.Append($"<text x=\"{P - 6}\" y=\"{F(Y(v) + 3)}\" text-anchor=\"end\">{100 * v}%</text><text x=\"{F(X(v))}\" y=\"{S - P + 16}\" text-anchor=\"middle\">{100 * v}%</text>");
        svg.Append($"<text x=\"{S / 2}\" y=\"{S - 4}\" text-anchor=\"middle\">Chance the model said</text>");
        svg.Append($"<text x=\"12\" y=\"{S / 2}\" text-anchor=\"middle\" transform=\"rotate(-90 12 {S / 2})\">How often it happened</text></g>");
        svg.Append($"<line class=\"mc-zero\" x1=\"{F(X(0))}\" y1=\"{F(Y(0))}\" x2=\"{F(X(1))}\" y2=\"{F(Y(1))}\" />");
        if (bands.Count > 1)
            svg.Append($"<path class=\"mc-line live\" d=\"{string.Concat(bands.Select((b, i) => $"{(i > 0 ? "L" : "M")}{F(X(b.Said))},{F(Y(b.Hit))}"))}\" />");
        foreach (var b in bands)
            svg.Append($"<circle class=\"mc-dot live\" cx=\"{F(X(b.Said))}\" cy=\"{F(Y(b.Hit))}\" r=\"{F(3 + 5 * Math.Sqrt(b.Count / max))}\"><title>{WebUtility.HtmlEncode(b.Name)}: said {Pct(b.Said)}, happened {Pct(b.Hit)}, {Js.Num((long)b.Count)} calls</title></circle>");
        svg.Append("</svg></figure>");
        return svg.ToString();
    }

    // ---- the model against the bookmakers in each competition with priced matches, furthest behind first
    public sealed record VsRow(string Key, string Name, int Priced, string ModelLl, string MarketLl, string Gap, string GapCls, string ModelRight, string MarketRight);
    public static List<VsRow> AgainstMarket(StatsDoc doc, Func<string, string> name, string range = "365d") =>
        (doc.Ranges.GetValueOrDefault(range) ?? []).Where(kv => kv.Value.Market is { N: > 0, ModelLl: not null, MarketLl: not null })
            .Select(kv => (kv.Key, M: kv.Value.Market!, Gap: kv.Value.Market!.ModelLl!.Value - kv.Value.Market.MarketLl!.Value))
            .OrderBy(t => t.Key == "all" ? 0 : t.Key == "eng" ? 1 : 2).ThenByDescending(t => t.Gap).ThenBy(t => t.Key, StringComparer.Ordinal)
            .Select(t => new VsRow(t.Key, name(t.Key), t.M.N, Ll(t.M.ModelLl), Ll(t.M.MarketLl), Signed(t.Gap), Tone(t.Gap), Pct(t.M.ModelCorrect), Pct(t.M.MarketCorrect)))
            .ToList();

    // ---- every challenger on live matches: its gain week by week with the range it could still lie
    // in, and where it stands now
    public sealed record Challenger(string Id, string Title, int N, int Weeks, string Gain, string Range, string Standing, string Mark, string? Chart);
    public static List<Challenger> Challengers(ModelDoc.LiveDoc? live, List<ModelDoc.Change> changes)
    {
        if (live is null) return [];
        var titles = changes.ToDictionary(c => c.Id, c => c.Title);
        static string G(double v) => ModelRecord.Signed(v);
        return live.Changes.Where(kv => kv.Value.N > 0)
            .OrderBy(kv => kv.Value.Verdict == "better" ? 0 : kv.Value.Verdict == "worse" ? 2 : 1).ThenByDescending(kv => kv.Value.Gain ?? double.NegativeInfinity).ThenBy(kv => kv.Key, StringComparer.Ordinal)
            .Select(kv =>
            {
                var r = kv.Value;
                var points = r.Series ?? [];
                string? chart = null;
                if (points.Count > 0)
                {
                    static string Week(int w) => $"{w / 100}-W{w % 100:00}";
                    var series = new List<ChangeLines.Series> { new("Gain so far", "live", points.Select(p => new ChangeLines.Point(Week(p.Week), p.Gain, $"{p.N} matches")).ToList()) };
                    var ranged = points.Where(p => p.Low is not null && p.High is not null).ToList();
                    if (ranged.Count > 0)
                    {
                        series.Add(new("Lowest it could be", "band", ranged.Select(p => new ChangeLines.Point(Week(p.Week), p.Low!.Value)).ToList()));
                        series.Add(new("Highest it could be", "band", ranged.Select(p => new ChangeLines.Point(Week(p.Week), p.High!.Value)).ToList()));
                    }
                    chart = ChangeLines.Svg(series, $"{ModelRecord.ShortId(kv.Key)}: gain in log loss on live matches, week by week", 4, zero: true);
                }
                var standing = ModelRecord.LiveStanding(live, kv.Key).Text;
                return new Challenger(kv.Key, titles.GetValueOrDefault(kv.Key, kv.Key), r.N, r.Weeks, r.Gain is { } g ? G(g) : "–",
                    r.Low is { } lo && r.High is { } hi ? $"{G(lo)} to {G(hi)}" : "–", standing,
                    r.Verdict == "better" ? "ready" : r.Verdict == "worse" ? "worse" : "none", chart);
            }).ToList();
    }
}
