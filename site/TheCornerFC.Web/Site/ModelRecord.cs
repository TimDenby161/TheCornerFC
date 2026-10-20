using System.Text.Json;
using System.Text.Json.Serialization;
using TheCornerFC.Web.Data;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Site;

// The Model's document (the "model" row, written nightly by thecornerfc/publish/site_record.py,
// public_model): the Model Change Tracker's record and the live tests' results, without the Admin
// area's own notes, and one finished match worked through step by step
// (The Admin area's "model_changes" document is the same record in full: the environment it came
// from, whether it could be stored, and any file that no longer matches what was first recorded.)
public sealed record ModelDoc(
    [property: JsonPropertyName("generated_at")] string GeneratedAt, ModelDoc.CurrentRecord? Current, List<ModelDoc.SeriesPoint>? Series,
    List<ModelDoc.Change> Changes, ModelDoc.LiveDoc? Tracking, ModelDoc.WorkedExample? Example,
    string? Environment = null, bool? Stored = null, List<string>? Differs = null)
{
    public sealed record ExpectedMetric(string Metric, double Delta, double? Low = null, double? High = null, string? Source = null);
    public sealed record Expected(List<ExpectedMetric>? Metrics, string? Improves = null, string? Betting = null, string? Confidence = null, string? Evidence = null);
    public sealed record MarketGap(int N, [property: JsonPropertyName("model_minus_market")] double ModelMinusMarket, string? Note = null);
    public sealed record Result(string? Type, string Evaluation, string Metric, double Delta, int? N, double? Baseline, double? After, double[]? Interval,
        string? Date = null, string? Unseen = null, string? Label = null, string[]? Period = null,
        [property: JsonPropertyName("interval_level")] double? IntervalLevel = null, [property: JsonPropertyName("vs_market")] MarketGap? VsMarket = null,
        string? Meaningful = null, string? Source = null);
    public sealed record Code(string? Commit, string? Experiment, [property: JsonPropertyName("model_version")] string? ModelVersion);
    public sealed record WindowMarket(int N, [property: JsonPropertyName("model_minus_market")] double ModelMinusMarket);
    public sealed record Window(int N, [property: JsonPropertyName("log_loss")] double? LogLoss, double? Brier, [property: JsonPropertyName("vs_market")] WindowMarket? VsMarket);
    public sealed record Forward(string? From, string? To, Window? After, Window? Before, string Verdict, string Why, [property: JsonPropertyName("deployed_with")] List<string>? DeployedWith);
    // a registered test on matches played after the change was fixed: how far it has got
    public sealed record LiveTest(string Protocol, string Start, int Target, int Matches);
    public sealed record Change(string Id, string Title, string? Model, string Status, string Stage, bool Deployed,
        [property: JsonPropertyName("deployed_on")] string? DeployedOn, [property: JsonPropertyName("released_in")] string? ReleasedIn,
        Expected? Expected, List<Result>? Results, List<LiveTest>? Live,
        string? Date = null, string? Recorded = null, bool Retrospective = false, string? Component = null, string? Kind = null,
        string? What = null, string? Why = null, string? How = null, string? Hypothesis = null,
        [property: JsonPropertyName("success_criteria")] string? SuccessCriteria = null, Code? Code = null,
        [property: JsonPropertyName("recorded_at")] string? RecordedAt = null, [property: JsonPropertyName("deployed_day_known")] bool? DeployedDayKnown = null,
        List<JsonElement>? Events = null, Forward? Forward = null);
    public sealed record VsMarket(int N, [property: JsonPropertyName("model_log_loss")] double ModelLogLoss, [property: JsonPropertyName("market_log_loss")] double MarketLogLoss);
    public sealed record Period(string From, string To);
    public sealed record CurrentRecord(string? Version, int? N, Period? Period, [property: JsonPropertyName("log_loss")] double? LogLoss, double? Brier,
        double? Accuracy, [property: JsonPropertyName("vs_market")] VsMarket? VsMarket);
    public sealed record SeriesPoint(string Month, string Source, double N, [property: JsonPropertyName("log_loss")] double LogLoss,
        double? Home, double? Draw, double? Away);
    // the live running record: each change scored on every finished match since it began, judged by
    // a confidence sequence; gain is production's log loss minus the change's (plus is better)
    public sealed record Called(string Verdict, int Week, int N, double Gain);
    public sealed record LivePoint(int Week, int N, double Gain, double? Low, double? High);
    public sealed record LiveRecord(int N, int Weeks, double? Gain, double? Low, double? High, string? Verdict, Called? Called = null, List<LivePoint>? Series = null);
    public sealed record Minimum(int Matches, int Weeks);
    public sealed record LiveDoc(string Protocol, string Start, Minimum Minimum, int N, int Weeks, string? To,
        Dictionary<string, LiveRecord> Changes, [property: JsonPropertyName("not_run")] Dictionary<string, string>? NotRun,
        [property: JsonPropertyName("generated_at")] string? GeneratedAt = null);
    // its match as site.matches holds it, by field name
    public sealed record WorkedExample(Dictionary<string, JsonElement> Match, [property: JsonPropertyName("home_name")] string? HomeName,
        [property: JsonPropertyName("away_name")] string? AwayName, string? Competition, Why? Why);
}

// The sums behind The Model (web/src/lib/changes.ts): what a result shows, the rows of changes, best
// first, and the eight figures at the top
public static class ModelRecord
{
    static readonly HashSet<string> HigherIsBetter = ["accuracy", "roi"];
    static bool Better(string metric, double delta) => HigherIsBetter.Contains(metric) ? delta > 0 : delta < 0;

    // What a result shows. "better" and "worse" are said only when its interval leaves zero out
    public static string Tone(ModelDoc.Result r)
    {
        if (r.Interval is not [var lo, var hi, ..]) return "unclear";
        if (lo <= 0 && hi >= 0) return "unclear";
        return Better(r.Metric, r.Delta) ? "better" : "worse";
    }

    // A change in a measure, signed, to the places these measures move in
    public static string Signed(double value, int places = 5)
    {
        var text = Js.ToFixed(Math.Abs(value), places);
        return double.Parse(text, System.Globalization.CultureInfo.InvariantCulture) == 0 ? text : $"{(value < 0 ? "−" : "+")}{text}";
    }

    // A change's short name on the page: A7 for MC-0007
    public static string ShortId(string id) =>
        int.TryParse(id.StartsWith("MC-") ? id[3..] : id, out var n) && n != 0 ? $"A{n}" : $"A{id}";

    static readonly Dictionary<string, int> Rank = new() { ["prospective"] = 0, ["backtest"] = 1, ["development"] = 2 };
    // The one result that speaks for a change on a measure: the strongest kind of evidence it has,
    // and of those the first recorded
    public static ModelDoc.Result? Headline(ModelDoc.Change c, string metric = "log_loss") =>
        (c.Results ?? []).Where(r => r.Metric == metric).OrderBy(r => Rank.GetValueOrDefault(r.Evaluation, 99)).FirstOrDefault();

    // In production: deployed itself, or an experiment released inside a change that is
    public static bool InProduction(ModelDoc.Change c) => c.Deployed || !string.IsNullOrEmpty(c.ReleasedIn);
    static double Gain(string metric, double delta) => HigherIsBetter.Contains(metric) ? delta : delta == 0 ? 0 : -delta;

    // Where a change stands on live matches, in a few words
    public sealed record Standing(ModelDoc.LiveRecord? Record, string Text, string Why);
    public static Standing LiveStanding(ModelDoc.LiveDoc? doc, string id)
    {
        if (doc is null) return new(null, "No live record yet", "");
        if (!doc.Changes.TryGetValue(id, out var r)) return new(null, "Not run live", doc.NotRun?.GetValueOrDefault(id) ?? "There is nothing to run");
        if (r.N == 0) return new(r, "No live matches yet", "");
        var enough = r.N >= doc.Minimum.Matches && r.Weeks >= doc.Minimum.Weeks;
        return new(r, r.Verdict == "better" ? "Proven better on live matches" : r.Verdict == "worse" ? "Proven worse on live matches"
            : enough ? "Not proven either way yet" : $"Too early: needs {doc.Minimum.Matches} matches and {doc.Minimum.Weeks} weeks", "");
    }

    // Ready to implement: a test (not the matches it was built on) proves the change better, by any
    // amount, and it has been neither rejected nor already deployed
    public static bool Ready(ModelDoc.Change c, ModelDoc.Result r) =>
        !c.Deployed && c.Status != "Rejected" && c.Status != "Reverted" && r.Evaluation != "development" && Tone(r) == "better";
    // Why a proven gain is not green, in a few words; '' where there is nothing to explain
    public static string NotReadyNote(ModelDoc.Change c, ModelDoc.Result r)
    {
        if (Ready(c, r) || Tone(r) != "better") return "";
        if (c.Deployed) return "Already in production";
        if (c.Status is "Rejected" or "Reverted") return "Proven on this test, but rejected: see why on its page";
        return r.Evaluation == "development" ? "Only measured on the matches it was built on" : "";
    }

    // A row for each change with a result on the measure, best first: changes proven better lead, by
    // gain; then the ones not proven either way, by gain; then the ones proven worse.
    // Mark: the page's one colour rule (ready, worse or none)
    // (Expected: the gain the change wrote down before it was tested, on the same measure, as a gain;
    // Before and After: the measure without and with it, where recorded)
    public sealed record DeltaRow(string Id, string Title, string? Evaluation, double? Gain, string Tone, int? N, bool Ready, string ReadyNote,
        string Mark, ModelDoc.LiveRecord? LiveRecord, string LiveText, string LiveWhy, double? Expected = null, double? Before = null, double? After = null);
    static readonly Dictionary<string, int> Order = new() { ["better"] = 0, ["unclear"] = 1, ["worse"] = 2 };
    public static List<DeltaRow> DeltaRows(List<ModelDoc.Change> changes, string metric, ModelDoc.LiveDoc? liveDoc = null)
    {
        var rows = changes.SelectMany(c =>
        {
            var r = Headline(c, metric);
            var hoped = c.Expected?.Metrics?.FirstOrDefault(m => m.Metric == metric);
            double? expected = hoped is null ? null : Gain(metric, hoped.Delta);
            // the live record speaks for log loss only, and never for a change already in production
            var now = LiveStanding(metric == "log_loss" ? liveDoc : null, c.Id);
            bool liveReady = now.Record?.Verdict == "better" && !c.Deployed, liveWorse = now.Record?.Verdict == "worse";
            if (r is null)
            {
                // a change with no past result is listed only for its live record
                if (now.Record is null) return [];
                var note = c.Deployed ? "In production: checked on live matches" : liveReady ? "Ready: proven on live matches" : "";
                return new[] { new DeltaRow(c.Id, c.Title, null, null, "unclear", null, liveReady, note, liveReady ? "ready" : liveWorse ? "worse" : "none", now.Record, now.Text, now.Why, expected) };
            }
            var past = Ready(c, r);
            var ok = past || liveReady;
            var readyNote = liveReady ? "Ready: proven on live matches" : !past ? NotReadyNote(c, r) : r.Evaluation == "prospective" ? "Ready: proven on new matches"
                : c.Status == "Testing" ? "Ready on the historical test; being confirmed on new matches" : "Ready on the historical test";
            var tone = Tone(r);
            return [new DeltaRow(c.Id, c.Title, r.Evaluation, Gain(metric, r.Delta), tone, r.N, ok, readyNote,
                ok ? "ready" : liveWorse ? "worse" : tone == "worse" ? "worse" : "none", now.Record, now.Text, now.Why, expected, r.Baseline, r.After)];
        }).ToList();
        static int Compare(DeltaRow a, DeltaRow b)
        {
            var d = (b.Ready ? 1 : 0) - (a.Ready ? 1 : 0);
            if (d != 0) return d;
            d = Order[a.Tone] - Order[b.Tone];
            if (d != 0) return d;
            // (as JavaScript: a missing gain sorts below any other, and two missing ones tie)
            var g = (b.Gain ?? double.NegativeInfinity) - (a.Gain ?? double.NegativeInfinity);
            if (g != 0 && !double.IsNaN(g)) return g > 0 ? 1 : -1;
            return string.CompareOrdinal(a.Id, b.Id) < 0 ? -1 : 1;
        }
        return rows.Select((r, i) => (r, i)).OrderBy(t => t.r, Comparer<DeltaRow>.Create(Compare)).ThenBy(t => t.i).Select(t => t.r).ToList();
    }

    // The running total across the versions that went to production: each deployed change's own
    // backtest gain on the measure, added in the order they went live
    public sealed record Step(string Id, string Title, string On, double? Delta, double Total);
    public static List<Step> Cumulative(List<ModelDoc.Change> changes, string metric = "log_loss", string model = "match")
    {
        double total = 0;
        return changes.Where(c => c.Deployed && c.Model == model)
            .OrderBy(c => c, Comparer<ModelDoc.Change>.Create((a, b) => string.CompareOrdinal(a.DeployedOn, b.DeployedOn) is var d && d != 0 ? d : string.CompareOrdinal(a.Id, b.Id) < 0 ? -1 : 1))
            .Select(c =>
            {
                var r = Headline(c, metric);
                double? delta = r is not null && r.Evaluation != "development" ? r.Delta : null;
                total += delta ?? 0;
                return new Step(c.Id, c.Title, c.DeployedOn!, delta, total);
            }).ToList();
    }

    // The model beside the simplest forecaster there is: one that gives every match the same three
    // chances, the shares of home wins, draws and away wins in the months before the live record
    // began. null where the months don't carry what happened, or there is no earlier month to learn from.
    public sealed record BaseRates(double N, double Model, double Base, double[] Rates);
    public static BaseRates? AgainstBaseRates(List<ModelDoc.SeriesPoint> series)
    {
        static bool Counted(ModelDoc.SeriesPoint s) => s.Home is not null && s.Draw is not null && s.Away is not null;
        var live = series.Where(s => s.Source == "live" && Counted(s)).ToList();
        if (live.Count == 0) return null;
        var first = live.Select(s => s.Month).OrderBy(m => m, StringComparer.Ordinal).First();
        var past = series.Where(s => s.Source == "backfill" && Counted(s) && string.CompareOrdinal(s.Month, first) < 0).ToList();
        static double Sum(List<ModelDoc.SeriesPoint> rows, Func<ModelDoc.SeriesPoint, double?> k) { double t = 0; foreach (var s in rows) t += k(s) ?? 0; return t; }
        Func<ModelDoc.SeriesPoint, double?>[] keys = [s => s.Home, s => s.Draw, s => s.Away];
        double before = Sum(past, keys[0]) + Sum(past, keys[1]) + Sum(past, keys[2]), n = Sum(live, s => s.N);
        if (before == 0 || n == 0) return null;
        var rates = keys.Select(k => Sum(past, k) / before).ToArray();
        if (rates.Any(r => r <= 0)) return null;
        double logs = 0;
        for (var i = 0; i < 3; i++) logs += Sum(live, keys[i]) * Math.Log(rates[i]);
        double model = 0;
        foreach (var s in live) model += s.N * s.LogLoss;
        return new(n, model / n, -logs / n, rates);
    }

    // The largest gain on a measure that a change not yet in production has proven, or null
    public static DeltaRow? BestWaiting(List<ModelDoc.Change> changes, string metric = "log_loss") =>
        DeltaRows(changes.Where(c => !InProduction(c) && c.Status != "Rejected").ToList(), metric)
            .FirstOrDefault(r => r.Tone == "better" && r.Evaluation != "development");

    // The eight figures at the top of The Model: how the live model is doing on its locked pre-kickoff
    // record, how it compares with the bookmakers and with guessing, and how the changes have moved
    // it. Every figure that compares is a change in log loss, so minus is better throughout.
    public sealed record Tile(string Label, string Value, string Note, string? Cls = null);
    public static List<Tile> ScoreTiles(ModelDoc doc)
    {
        var cur = doc.Current;
        var steps = Cumulative(doc.Changes);
        var total = steps.Where(s => s.Delta is not null).ToList();
        double? gap = cur?.VsMarket is { } vm ? vm.ModelLogLoss - vm.MarketLogLoss : null;
        static string Day(string? iso) => iso is null ? "" : iso.Length >= 10 ? iso[..10] : iso;
        var b = AgainstBaseRates(doc.Series ?? []);
        var next = BestWaiting(doc.Changes);
        static string Pos(double v) => v < 0 ? "pos" : v > 0 ? "neg" : "";
        var bestStage = next is null ? "" : doc.Changes.First(c => c.Id == next.Id).Stage;
        return
        [
            new("Base log loss", cur?.LogLoss is { } ll ? Js.ToFixed(ll, 4) : "Not recorded",
                cur?.Period is { } p ? $"The live model's predictions stored before kickoff, {Day(p.From)} to {Day(p.To)}. Lower is better" : "The live record"),
            new("vs Bookmakers", gap is { } g ? Signed(g, 4) : "Not recorded",
                gap is { } g2 ? $"Result log loss, model minus market, on {Js.Num(cur!.VsMarket!.N)} matches with stored prices in the last 12 months. {(g2 > 0 ? "Behind the market" : "Ahead of the market")}; the registered comparison is protocol P6" : "No matches with stored prices",
                gap is { } g3 ? Pos(g3) : ""),
            new("vs Guessing", b is not null ? Signed(b.Model - b.Base, 4) : "Not recorded",
                b is not null ? $"Log loss {Js.ToFixed(b.Model, 4)} against {Js.ToFixed(b.Base, 4)} for giving every match {Js.ToFixed(100 * b.Rates[0], 0)}% / {Js.ToFixed(100 * b.Rates[1], 0)}% / {Js.ToFixed(100 * b.Rates[2], 0)}%, on {Js.Num((long)b.N)} live matches. Minus means the model is better" : "Needs a live record and the months before it",
                b is not null ? Pos(b.Model - b.Base) : ""),
            new("Matches", cur?.N is { } mn ? Js.Num(mn) : "Not recorded", "Finished matches with a prediction stored before kickoff, behind the figures in this row"),
            new("Brier score", cur?.Brier is { } br ? Js.ToFixed(br, 4) : "Not recorded", "On the same matches as the log loss. Lower is better"),
            new("Improvement", total.Count > 0 ? Signed(steps[^1].Total) : "Not recorded",
                total.Count > 0 ? $"Change in log loss since the earliest dated version: the sum of {total.Count} deployed change{(total.Count == 1 ? "'s" : "s'")} own backtest{(total.Count == 1 ? "" : "s")}, on different samples. Minus is better. Earlier changes were never dated and are not counted" : "No deployed change has a recorded backtest",
                total.Count > 0 ? Pos(steps[^1].Total) : ""),
            new("Best gain not in production", next is not null ? Signed(-(next.Gain ?? 0)) : "None yet",
                next is not null ? $"Change in log loss. {ShortId(next.Id)} · {next.Title}{(next.N is { } nn && nn != 0 ? $", on {Js.Num(nn)} matches" : "")}. {bestStage}: a historical test, not yet confirmed on new matches" : "No change outside production has a proven gain",
                next is not null ? "pos" : ""),
            new("Right results", cur?.Accuracy is { } acc ? $"{Js.ToFixed(100 * acc, 1)}%" : "Not recorded", "The outcome the model made most likely happened, on the same matches"),
        ];
    }

    // ---- One change's own page (the Admin area)
    public const string NotSpecified = "Not specified";
    public static readonly Dictionary<string, string> MetricLabels = new()
    {
        ["log_loss"] = "Log loss", ["brier"] = "Brier score", ["rps"] = "Ranked probability score", ["accuracy"] = "Right result", ["calibration_error"] = "Calibration error",
        ["goal_markets_log_loss"] = "Goal markets log loss", ["mse"] = "Squared error", ["mae"] = "Absolute error", ["roi"] = "Return", ["other"] = "Other measure",
    };
    public static readonly Dictionary<string, string> ToneWords = new() { ["better"] = "Better", ["worse"] = "Worse", ["unclear"] = "Unclear" };
    public static readonly Dictionary<string, string> EvaluationLabels = new() { ["prospective"] = "Prospective test", ["backtest"] = "Historical backtest", ["development"] = "Development figure" };
    public static readonly Dictionary<string, string> UnseenLabels = new() { ["yes"] = "Matches the change had not seen", ["partly"] = "Held out, but looked at before", ["no"] = "The matches it was built on" };
    public static string MarkOf(bool ready, string tone) => ready ? "ready" : tone == "worse" ? "worse" : "none";

    // The change as a share of the figure before it, where that figure was recorded
    public static string? Percent(ModelDoc.Result r)
    {
        if (r.Baseline is not { } b || b == 0) return null;
        var p = 100 * r.Delta / b;
        return $"{(p < 0 ? "−" : "+")}{Js.ToFixed(Math.Abs(p), 2)}%";
    }
    public static string? IntervalText(ModelDoc.Result r, int places = 5) => r.Interval is [var lo, var hi, ..]
        ? $"{Signed(lo, places)} to {Signed(hi, places)}{(r.IntervalLevel is { } level && level != 0 ? $" ({JsNumber(double.Parse(Js.ToFixed(100 * level, 1), System.Globalization.CultureInfo.InvariantCulture))}%)" : "")}"
        : null;
    // a number as JavaScript writes it (`${v}`, +v.toFixed(1)): 95, 99.6
    static string JsNumber(double x) => x == Math.Floor(x) ? ((long)x).ToString(System.Globalization.CultureInfo.InvariantCulture) : x.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
    // A live test's progress in words: "312 of 9,400 (P13)"
    public static string LiveText(ModelDoc.LiveTest t) => $"{Js.Num(t.Matches)} of {Js.Num(t.Target)} ({t.Protocol})";

    // The forward record in a sentence each: what was expected, what the backtest gave, what has
    // been seen since, and how far the last is from the first
    public sealed record ForwardSummary(double? Expected, double? Backtest, double? Observed, double? Gap);
    public static ForwardSummary ForwardOf(ModelDoc.Change c, string metric = "log_loss")
    {
        var expected = c.Expected?.Metrics?.FirstOrDefault(m => m.Metric == metric)?.Delta;
        var tested = (c.Results ?? []).FirstOrDefault(r => r.Metric == metric && r.Evaluation == "backtest")?.Delta;
        var f = c.Forward;
        double? observed = f?.After?.VsMarket is { } a && f.Before?.VsMarket is { } b ? a.ModelMinusMarket - b.ModelMinusMarket : null;
        return new(expected, tested, observed, observed is { } o && expected is { } e ? o - e : null);
    }

    // The worked example's match, from its row by field name (as a row of site_matches, so it is read
    // the same way)
    public static Match ExampleMatch(SiteDoc site, Dictionary<string, JsonElement> row)
    {
        var fields = row.Keys.ToArray();
        var answer = new MatchesAnswer([row.Values.ToArray()], null, null);
        return ClubData.MatchRows(site with { MatchFields = fields }, answer)[0];
    }
}
