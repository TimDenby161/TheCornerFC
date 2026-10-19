using System.Globalization;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// How the models work: the words from web/src/text/methodology.html, with its boxes of live
// figures filled from the `methodology` document (how fresh the data is, the scored match
// predictions and line-ups, the model version in use), as the Svelte site's page has them.
public sealed class MethodologyModel(Database db, TimeProvider clock) : PageModel
{
    public const int StaleHours = 36;     // the nightly run plus a margin: older than this, say so
    static readonly CultureInfo British = CultureInfo.GetCultureInfo("en-GB");

    public TextPage Text { get; } = TextPage.Named("methodology");
    public Doc? Live { get; private set; }
    public double Hours { get; private set; }
    string tz = ZoneChoice.UkZone;

    public async Task OnGet()
    {
        tz = Visitor.Of(HttpContext).Zone.Tz;
        if (!Visitor.Of(HttpContext).SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        try { Live = await db.KeptDoc<Doc>("methodology", TimeSpan.FromMinutes(5)); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException) { Live = null; }
        if (Live is not null) Hours = (clock.GetUtcNow() - Live.GeneratedAt).TotalHours;
    }

    DateTimeOffset There(DateTimeOffset at) => TimeZoneInfo.ConvertTime(at, TimeZoneInfo.FindSystemTimeZoneById(tz));
    // "18 Oct 2026, 14:05" and "18 Oct 2026", in the visitor's time zone as the server has it
    public string When(DateTimeOffset at) => There(at).ToString("d MMM yyyy, HH:mm", British);
    public string Day(DateTimeOffset at) => There(at).ToString("d MMM yyyy", British);
    public static string Pct(double x) => Js.ToFixed(x * 100, 1) + "%";
    public static string Num(int x) => x.ToString("N0", British);
    public string Period(Span? p) => p is null ? "" : $"Kick-offs from {Day(p.From)} to {Day(p.To)}.";

    // how much weight a sample can bear, in words
    public static string SampleNote(int n, string what) =>
        n < 500 ? $"Very early: {Num(n)} {what} is far too few to judge the model. These figures will move a lot as more come in."
        : n < 2000 ? $"Still a small sample ({Num(n)} {what}). Small differences are likely to be luck." : "";

    public static string Versions(IReadOnlyList<Version>? vs, string what)
    {
        if (vs is not { Count: > 0 }) return "";
        var list = string.Join(", ", vs.Select(v => $"{v.Name} ({Num(v.N)})"));
        return vs.Count == 1 ? $"All {what} from model version {list}." : $"Pooled across model versions: {list}.";
    }

    public IEnumerable<(string Label, DateTimeOffset At)> Fresh() =>
        Live is null ? [] : new (string, DateTimeOffset?)[]
        {
            ("Site data exported", Live.GeneratedAt),
            ("Predictions last written", Live.Freshness?.Predictions),
            ("Injury lists last fetched", Live.Freshness?.Injuries),
            ("Odds last fetched", Live.Freshness?.Odds),
        }.Where(x => x.Item2 is not null).Select(x => (x.Item1, x.Item2!.Value));

    public sealed record Doc(
        [property: JsonPropertyName("generated_at")] DateTimeOffset GeneratedAt,
        Sources? Freshness, Matches? Matches, Lineups? Lineups);
    public sealed record Sources(DateTimeOffset? Predictions, DateTimeOffset? Injuries, DateTimeOffset? Odds, Model? Model);
    public sealed record Model(string Name, string? Code, DateTimeOffset? Registered);
    public sealed record Span(DateTimeOffset From, DateTimeOffset To);
    public sealed record Version(string Name, int N);
    public sealed record Share(int N, double Accuracy);
    public sealed record Matches(
        int N, Span? Period, IReadOnlyList<Version>? Versions, double Accuracy,
        [property: JsonPropertyName("log_loss")] double LogLoss, double Brier,
        [property: JsonPropertyName("exact_score")] Share? ExactScore,
        // [bin "0.4-0.5", predictions, average chance given, how often it happened]
        IReadOnlyList<System.Text.Json.JsonElement[]> Calibration,
        [property: JsonPropertyName("excluded_no_regulation_score")] int? ExcludedNoRegulationScore);
    public sealed record Lineups(
        int N, Span? Period, IReadOnlyList<Version>? Versions,
        [property: JsonPropertyName("correct_starters_mean")] double CorrectStartersMean,
        [property: JsonPropertyName("role_accuracy")] Share? RoleAccuracy,
        [property: JsonPropertyName("excluded_no_official_xi")] int? ExcludedNoOfficialXi);
}
