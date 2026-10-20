using System.Text.Json;
using System.Text.Json.Serialization;

namespace TheCornerFC.Web.Site;

// The Stats page's figures by range and competition (the "stats" row: ranges["30d"]["39"], with
// "all" for every competition together; web/src/lib/stats.ts)
// (Monthly: the same sums by calendar month for "all", "eng" and each competition, as short arrays
// named by MonthColumns, which only the Admin area's research dashboard reads)
public sealed record StatsDoc(Dictionary<string, Dictionary<string, StatsDoc.Stats>> Ranges,
    [property: JsonPropertyName("month_columns")] List<string>? MonthColumns = null, Dictionary<string, List<JsonElement[]>>? Monthly = null)
{
    public sealed record Month(string Key, int N, double? Correct, double? LogLoss, double? Brier, MarketPair? Market);
    // one group's months, read by column name
    public List<Month>? MonthsOf(string key)
    {
        if (Monthly is null || MonthColumns is null) return null;
        if (!Monthly.TryGetValue(key, out var rows)) return [];
        int At(string name) => MonthColumns.IndexOf(name);
        double? D(JsonElement[] r, string name) => At(name) is var i && i >= 0 && i < r.Length && r[i].ValueKind == JsonValueKind.Number ? r[i].GetDouble() : null;
        return rows.Select(r =>
        {
            var priced = (int)(D(r, "market_n") ?? 0);
            return new Month(r[At("month")].GetString()!, (int)(D(r, "n") ?? 0), D(r, "correct"), D(r, "log_loss"), D(r, "brier"),
                priced > 0 ? new MarketPair(priced, D(r, "model_ll"), D(r, "market_ll"), D(r, "model_correct"), D(r, "market_correct")) : null);
        }).ToList();
    }

    public sealed record Stats
    {
        public int N { get; init; }
        public int Live { get; init; }
        public int Rated { get; init; }
        public double? Correct { get; init; }
        public double? Exact { get; init; }
        [JsonPropertyName("home_rate")] public double? HomeRate { get; init; }
        [JsonPropertyName("log_loss")] public double? LogLoss { get; init; }
        public double? Brier { get; init; }
        [JsonPropertyName("goal_error")] public double? GoalError { get; init; }
        public MarketPair? Market { get; init; }
        [JsonPropertyName("rating_avg")] public double? RatingAvg { get; init; }
        [JsonPropertyName("rating_counts")] public double?[]? RatingCounts { get; init; }
        [JsonPropertyName("factor_avgs")] public Dictionary<string, double>? FactorAvgs { get; init; }
        // ten bands of stated chance (0-10%, 10-20% ...): [calls, average said, share that happened]
        public double?[][]? Calibration { get; init; }
        public Dictionary<string, MarketStats>? Markets { get; init; }
    }
    // the result market against the bookmakers' fair prices, on the matches that had odds
    public sealed record MarketPair(int N, [property: JsonPropertyName("model_ll")] double? ModelLl, [property: JsonPropertyName("market_ll")] double? MarketLl,
        [property: JsonPropertyName("model_correct")] double? ModelCorrect, [property: JsonPropertyName("market_correct")] double? MarketCorrect);
    // a bet market: log loss against the closing prices, and the opening ones where they were seen before kickoff
    public sealed record MarketStats(int N, [property: JsonPropertyName("model_ll")] double? ModelLl, [property: JsonPropertyName("close_ll")] double? CloseLl,
        [property: JsonPropertyName("open_n")] int OpenN, [property: JsonPropertyName("model_open_ll")] double? ModelOpenLl, [property: JsonPropertyName("open_ll")] double? OpenLl);
}

public static class StatsFigures
{
    public static readonly (string Key, string Label)[] Ranges = [("7d", "7 days"), ("30d", "30 days"), ("90d", "90 days"), ("365d", "12 months")];
    public static readonly string[] MarketKeys = ["1X2", "BTTS", "OU15", "OU25", "OU35", "OU45"];
    public static readonly Dictionary<string, string> MarketLabels = new()
    {
        ["1X2"] = "Result", ["OU15"] = "Over/Under 1.5", ["OU25"] = "Over/Under 2.5", ["OU35"] = "Over/Under 3.5", ["OU45"] = "Over/Under 4.5", ["BTTS"] = "Both teams score",
    };

    // Several competitions' stats as one: counts add up, averages are weighted by what they average
    // over. (A missing figure counts as nothing in the sums, as in JavaScript.)
    public static StatsDoc.Stats? Merge(List<StatsDoc.Stats> parts)
    {
        if (parts.Count < 2) return parts.FirstOrDefault();
        static double Sum<T>(IEnumerable<T> xs, Func<T, double?> f) { double t = 0; foreach (var x in xs) t += f(x) is { } v && !double.IsNaN(v) ? v : 0; return t; }
        static double? Avg<T>(List<T> xs, Func<T, double?> val, Func<T, double> w)
        {
            var n = Sum(xs, x => w(x));
            return n != 0 ? Sum(xs, x => val(x) is { } v ? v * w(x) : 0) / n : null;
        }
        var n = (int)Sum(parts, x => x.N);
        var rated = (int)Sum(parts, x => x.Rated);
        static double ByN(StatsDoc.Stats x) => x.N;
        var mk = parts.Select(x => x.Market).Where(m => m is not null).Select(m => m!).ToList();
        var ratingCounts = Enumerable.Range(0, 5).Select(i => (double?)Sum(parts, x => x.RatingCounts is { } rc && i < rc.Length ? rc[i] : null)).ToArray();
        var fa = parts.Where(x => x.FactorAvgs is not null).ToList();
        var markets = new Dictionary<string, StatsDoc.MarketStats>();
        foreach (var k in MarketKeys)
        {
            var ms = parts.Select(x => x.Markets?.GetValueOrDefault(k)).Where(m => m is not null).Select(m => m!).ToList();
            if (ms.Count == 0) continue;
            var open = ms.Where(m => m.OpenN != 0).ToList();
            markets[k] = new((int)Sum(ms, m => m.N), Avg(ms, m => m.ModelLl, m => m.N), Avg(ms, m => m.CloseLl, m => m.N),
                (int)Sum(open, m => m.OpenN), Avg(open, m => m.ModelOpenLl, m => m.OpenN), Avg(open, m => m.OpenLl, m => m.OpenN));
        }
        double?[] Band(int i)
        {
            var bins = parts.Select(x => x.Calibration![i]).Where(b => b[0] is { } c && c != 0).ToList();
            var c = Sum(bins, b => b[0]);
            return c != 0 ? [c, Sum(bins, b => b[0] * b[1]) / c, Sum(bins, b => b[0] * b[2]) / c] : [0, null, null];
        }
        return new()
        {
            N = n, Live = (int)Sum(parts, x => x.Live), Rated = rated,
            Correct = Avg(parts, x => x.Correct, ByN), Exact = Avg(parts, x => x.Exact, ByN), HomeRate = Avg(parts, x => x.HomeRate, ByN),
            LogLoss = Avg(parts, x => x.LogLoss, ByN), Brier = Avg(parts, x => x.Brier, ByN), GoalError = Avg(parts, x => x.GoalError, ByN),
            Market = mk.Count > 0 ? new((int)Sum(mk, m => m.N), Avg(mk, m => m.ModelLl, m => m.N), Avg(mk, m => m.MarketLl, m => m.N),
                Avg(mk, m => m.ModelCorrect, m => m.N), Avg(mk, m => m.MarketCorrect, m => m.N)) : null,
            RatingCounts = ratingCounts,
            RatingAvg = rated != 0 ? ratingCounts.Select((c, i) => (i + 1) * (c ?? 0)).Sum() / rated : null,
            FactorAvgs = rated != 0 && fa.Count > 0 ? fa[0].FactorAvgs!.Keys.ToDictionary(k => k, k => Sum(fa, x => x.FactorAvgs!.TryGetValue(k, out var v) ? v * x.Rated : null) / rated) : null,
            Calibration = Enumerable.Range(0, parts[0].Calibration?.Length ?? 0).Select(Band).ToArray(),
            Markets = markets.Count > 0 ? markets : null,
        };
    }
}
