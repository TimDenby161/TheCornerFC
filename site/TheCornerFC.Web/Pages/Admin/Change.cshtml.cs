using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.AdminArea;

// One change in full (web/src/routes/(app)/admin/changes/[id]): what was registered, what was
// expected, each result, the decision and, for a change deployed to production, how it has done
// since. The administrator's only.
public sealed class ChangeModel(Database db) : PageModel
{
    public sealed record ResultView(string Label, string? Date, string Kind, string Unseen, string Metric, string Before, string After, string Delta,
        string? Percent, string? Interval, string N, string Period, string Mark, string Word, string? Meaningful, string? Source, string Market);
    public sealed record EventView(int N, string Date, bool Month, string? RecordedAt, string Text);
    public sealed record Tracking(string Protocol, string Text, string Why, string Start, string? To, string? Generated, int MinMatches, int MinWeeks,
        int N, int Weeks, string? Gain, string? Range, string? Called, List<ChangeLines.Point> Gains, List<ChangeLines.Point> Lows, List<ChangeLines.Point> Highs);
    public sealed record LiveTestView(string Protocol, string Start, int Matches, int Target, int Share);
    public sealed record ForwardView(ModelDoc.Forward F, string Expected, string Backtest, string? Observed, string? Gap);

    public ModelDoc Doc { get; private set; } = null!;
    public ModelDoc.Change C { get; private set; } = null!;
    public List<string> Differs { get; private set; } = [];
    public bool IsReady { get; private set; }
    public string Why { get; private set; } = "";
    public Tracking? Running { get; private set; }
    public List<ResultView> Results { get; private set; } = [];
    public List<EventView> Events { get; private set; } = [];
    public List<LiveTestView> Live { get; private set; } = [];
    public ForwardView? Forward { get; private set; }
    public static string Said(string? text) => text is { } t && t.Trim() != "" ? t : ModelRecord.NotSpecified;

    public async Task<IActionResult> OnGet(string id)
    {
        ViewData["TabHead"] = TabHead.For("Model Change Tracker", "changes");
        var token = Visitor.Of(HttpContext).Token;
        var docTask = TheCornerFC.Web.Site.Admin.Doc<ModelDoc>(db, token, "model_changes");
        var liveTask = TheCornerFC.Web.Site.Admin.Doc<ModelDoc.LiveDoc>(db, token, "live_tracking");
        await Task.WhenAll(docTask, liveTask);
        if (docTask.Result.Refused || liveTask.Result.Refused || docTask.Result.Doc is not { } doc || doc.Changes.FirstOrDefault(x => x.Id == id) is not { } c)
            return NotFound();
        (Doc, C) = (doc, c);
        var running = liveTask.Result.Doc;
        Differs = (doc.Differs ?? []).Where(line => line.StartsWith(c.Id, StringComparison.Ordinal)).ToList();
        static int Places(ModelDoc.Result r) => r.Metric is "mse" or "accuracy" or "roi" ? 4 : 5;
        var main = ModelRecord.Headline(c);
        var now = ModelRecord.LiveStanding(running, c.Id);
        var rec = now.Record;
        var liveReady = rec?.Verdict == "better" && !c.Deployed;
        // green on this page, as on the list, only for a change with enough evidence to implement
        IsReady = (main is not null && ModelRecord.Ready(c, main)) || liveReady;
        Why = liveReady ? "" : main is not null ? ModelRecord.NotReadyNote(c, main) : "";

        // the running record of this change on live matches (P15; from the club-rank release, P16 and P17)
        if (running is not null)
        {
            static string Week(int w) => $"{w.ToString()[..4]}-W{w.ToString()[4..]}";
            var series = (rec?.Series ?? []).Where(p => p.Low is not null && p.High is not null).ToList();
            Running = new(running.Protocol, now.Text, now.Why, running.Start, running.To, running.GeneratedAt, running.Minimum.Matches, running.Minimum.Weeks,
                rec?.N ?? 0, rec?.Weeks ?? 0, rec?.Gain is { } g ? ModelRecord.Signed(g) : null,
                rec?.Low is { } lo && rec.High is { } hi ? $"{ModelRecord.Signed(lo)} to {ModelRecord.Signed(hi)}" : null,
                rec?.Called is { } called ? $"{(called.Verdict == "better" ? "Proven better" : "Proven worse")} from week {called.Week.ToString()[4..]} of {called.Week.ToString()[..4]}, at {Js.Num(called.N)} matches" : null,
                series.Select(p => new ChangeLines.Point(Week(p.Week), p.Gain, $"{Js.Num(p.N)} matches")).ToList(),
                series.Select(p => new ChangeLines.Point(Week(p.Week), p.Low!.Value)).ToList(),
                series.Select(p => new ChangeLines.Point(Week(p.Week), p.High!.Value)).ToList());
        }

        Results = (c.Results ?? []).Select(r =>
        {
            var tone = ModelRecord.Tone(r);
            return new ResultView(r.Label ?? "", r.Date, ModelRecord.EvaluationLabels.GetValueOrDefault(r.Evaluation) ?? r.Evaluation, ModelRecord.UnseenLabels.GetValueOrDefault(r.Unseen ?? "") ?? "",
                ModelRecord.MetricLabels.GetValueOrDefault(r.Metric) ?? r.Metric,
                r.Baseline is { } b ? Js.ToFixed(b, 5) : ModelRecord.NotSpecified, r.After is { } a ? Js.ToFixed(a, 5) : ModelRecord.NotSpecified,
                ModelRecord.Signed(r.Delta, Places(r)), ModelRecord.Percent(r), ModelRecord.IntervalText(r, Places(r)),
                r.N is { } n ? Js.Num(n) : ModelRecord.NotSpecified, r.Period is [var from, var to, ..] ? $"{from} to {to}" : ModelRecord.NotSpecified,
                ModelRecord.MarkOf(ReferenceEquals(r, main) && ModelRecord.Ready(c, r), tone), ModelRecord.ToneWords[tone], r.Meaningful, r.Source,
                r.VsMarket is { } vm ? $"{ModelRecord.Signed(vm.ModelMinusMarket, 4)} against the market on {Js.Num(vm.N)} matches{(vm.Note is { Length: > 0 } note ? $". {note}" : "")}" : "Not measured against bookmakers");
        }).ToList();

        Events = (c.Events ?? []).Select((e, i) =>
        {
            string? S(string k) => e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
            var type = S("type") ?? "";
            string? note = S("note") is { Length: > 0 } nt ? nt : null;
            var text = type switch
            {
                "result" => $"{ModelRecord.EvaluationLabels.GetValueOrDefault(S("evaluation") ?? "")}: {S("label")}, {ModelRecord.Signed(e.GetProperty("delta").GetDouble())}",
                "status" => $"Status: {S("status")}{(note is not null ? $". {note}" : "")}",
                "decision" => $"Decision: {S("status")}. {S("reason")}",
                "deployed" => $"Deployed to production{(S("commit") is { Length: > 0 } commit ? $" ({commit})" : "")}{(note is not null ? $". {note}" : "")}",
                "released" => $"Released inside {S("as")}{(note is not null ? $". {note}" : "")}",
                "reverted" => $"Reverted. {S("reason")}",
                "live_test" => $"Live test registered: protocol {S("protocol")}, on matches from {S("start")}, read once at {(e.TryGetProperty("target", out var tg) && tg.ValueKind == JsonValueKind.Number ? Js.Num(tg.GetInt64()) : "undefined")}",
                _ => $"Correction of {(e.TryGetProperty("of", out var of) && of.ValueKind == JsonValueKind.String && of.GetString() == "registration" ? "the registration" : $"event {(e.TryGetProperty("of", out var of2) ? of2.GetRawText() : "")}")}: {S("text")}",
            };
            return new EventView(i + 1, S("date") ?? "", S("date_known_to") == "month", S("recorded_at"), text);
        }).ToList();

        Live = (c.Live ?? []).Select(t => new LiveTestView(t.Protocol, t.Start, t.Matches, t.Target, Math.Min(100, Js.RoundInt(100.0 * t.Matches / t.Target)))).ToList();
        if (c.Forward is { } f)
        {
            var fwd = ModelRecord.ForwardOf(c);
            Forward = new(f, fwd.Expected is { } ex ? ModelRecord.Signed(ex) : ModelRecord.NotSpecified, fwd.Backtest is { } bt ? ModelRecord.Signed(bt) : ModelRecord.NotSpecified,
                fwd.Observed is { } ob ? ModelRecord.Signed(ob) : null, fwd.Gap is { } gp ? ModelRecord.Signed(gp) : null);
        }
        return Page();
    }
}
