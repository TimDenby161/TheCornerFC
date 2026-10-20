using System.Text.Json;

namespace TheCornerFC.Web.Site;

// The two match models that run side by side, compared for the switch card in the Admin area
// (web/src/lib/matchModels.ts; admin_match_model_compare(), db/migrations/20261014_match_model_compare.sql).
// Chances are 0 to 1; a fixture's five numbers are home, draw and away chances, then home and away
// expected goals.
public static class MatchModels
{
    static string Pct(double p, int places = 0) => $"{Js.ToFixed(100 * p, places)}%";
    // a difference in percentage points, with its sign
    static string Points(double d) => $"{(d > 0 ? "+" : d < 0 ? "−" : "")}{Js.ToFixed(Math.Abs(100 * d), 2)}";
    static string Four(double v) => Js.ToFixed(v, 4);
    static string Sign4(double d) => $"{(d > 0 ? "+" : d < 0 ? "−" : "")}{Js.ToFixed(Math.Abs(d), 4)}";
    static string Mark(double d, bool lowerBetter) => d == 0 ? "" : (d < 0) == lowerBetter ? "better" : "worse";

    // Each measure on the same finished matches: both models, and A18 minus base, marked better or
    // worse for A18 (lower is better for log loss and Brier, higher for right results)
    public sealed record ScoreRow(string Label, string Base, string A18, string Gap, string Mark, string? Market, string? MarketGap, string MarketMark, string MarketNote);
    public sealed record Scores(int N, int Priced, List<ScoreRow> Rows);
    static readonly (string Label, string Key, bool Accuracy)[] Measures = [("Log loss", "log_loss", false), ("Brier", "brier", false), ("Right result", "accuracy", true)];

    // The bookmakers are read on the matches with stored prices, beside both models on those same
    // matches, so the three are always compared on the same games.
    public static Scores ScoreRows(JsonElement finished)
    {
        JsonElement? Of(string k) => finished.ValueKind == JsonValueKind.Object && finished.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Object ? v : null;
        static double Get(JsonElement e, string k) => e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : 0;
        JsonElement? b = Of("base"), a = Of("a18"), m = Of("market"), bp = Of("base_priced"), ap = Of("a18_priced");
        if (b is not { } bb || a is not { } aa || Get(bb, "n") == 0) return new(0, 0, []);
        var priced = m is { } mm && bp is not null && ap is not null && Get(mm, "n") != 0 ? (int)Get(mm, "n") : 0;
        int nA = (int)Get(aa, "n"), nB = (int)Get(bb, "n");
        return new(Math.Min(nA, nB), priced, Measures.Select(x =>
        {
            Func<double, string> show = x.Accuracy ? v => Pct(v, 1) : Four;
            Func<double, string> gap = x.Accuracy ? d => $"{Points(d)} pts" : Sign4;
            var lowerBetter = !x.Accuracy;
            double bx = Get(bb, x.Key), ay = Get(aa, x.Key), d = ay - bx;
            var dm = priced != 0 ? Get(ap!.Value, x.Key) - Get(m!.Value, x.Key) : 0;
            return new ScoreRow(x.Label, show(bx), show(ay), gap(d), Mark(d, lowerBetter),
                priced != 0 ? show(Get(m!.Value, x.Key)) : null, priced != 0 ? gap(dm) : null, priced != 0 ? Mark(dm, lowerBetter) : "",
                priced != 0 && priced < Math.Min(nA, nB) ? $"A18 {show(Get(ap!.Value, x.Key))} on these {priced}" : "");
        }).ToList());
    }

    // A18's test on past matches (its change record's results from one results file): base and A18
    // on each measure. No bookmakers: there are no clean stored prices for that period.
    public sealed record Past(int? N, string[]? Period, List<ScoreRow> Rows);
    public static Past PastRows(List<ModelDoc.Result> results)
    {
        var rows = Measures.SelectMany(x =>
        {
            var r = results.FirstOrDefault(y => y.Metric == x.Key && y.Baseline is not null && y.After is not null);
            if (r is null) return [];
            Func<double, string> show = x.Accuracy ? v => Pct(v, 1) : Four;
            var d = r.After!.Value - r.Baseline!.Value;
            return new[] { new ScoreRow(x.Label, show(r.Baseline.Value), show(r.After.Value), x.Accuracy ? $"{Points(d)} pts" : Sign4(d), Mark(d, !x.Accuracy), null, null, "", "") };
        }).ToList();
        var first = results.FirstOrDefault(r => r.N is not null);
        return new(first?.N, first?.Period, rows);
    }

    // One upcoming fixture as shown: both models' chances and expected goals
    public sealed record Apart(int Fixture, string Kickoff, string Match, string League, string Base, string A18, string? Market, string BaseXg, string A18Xg, string Gap, bool Differ);
    public static Apart ApartRow(JsonElement r)
    {
        static double?[] Nums(JsonElement e) => e.ValueKind == JsonValueKind.Array ? e.EnumerateArray().Select(x => x.ValueKind == JsonValueKind.Number ? x.GetDouble() : (double?)null).ToArray() : [];
        static string Hda(double?[] p) => $"{Pct(p[0] ?? 0)} · {Pct(p[1] ?? 0)} · {Pct(p[2] ?? 0)}";
        static string Xg(double?[] p) => p.Length > 4 && p[3] is { } h && p[4] is { } a ? $"{Js.ToFixed(h, 2)}–{Js.ToFixed(a, 2)}" : "–";
        string S(string k) => r.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "";
        var b = Nums(r.GetProperty("base"));
        var a = Nums(r.GetProperty("a18"));
        var market = r.TryGetProperty("market", out var mk) && mk.ValueKind == JsonValueKind.Array ? Hda(Nums(mk)) : null;
        return new(r.GetProperty("fixture").GetInt32(), S("kickoff"), $"{S("home")} v {S("away")}", S("league"), Hda(b), Hda(a), market, Xg(b), Xg(a),
            $"{Js.ToFixed(Math.Abs(100 * r.GetProperty("gap").GetDouble()), 1)} pts", r.TryGetProperty("differ", out var df) && df.ValueKind == JsonValueKind.True);
    }
}
