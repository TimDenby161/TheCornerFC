using System.Globalization;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// The Prediction record (Site/PredictionRecord.cs): every finished match's prediction as it was
// locked before kick-off, for the month (?m=), competition (?c=) and page (?p=) in the address.
// Every signed-out visitor gets the same answer, so it is kept for five minutes and cached.
public sealed class RecordModel(Database db, TimeProvider clock) : PageModel
{
    public string State { get; private set; } = "waiting";       // waiting (no table or rows yet), empty or ok
    public string Month { get; private set; } = "all";
    public string Comp { get; private set; } = "all";
    public int PageNo { get; private set; } = 1;
    public List<(string Key, string Name)> Months { get; private set; } = [];
    public List<(string Key, string Name)> Comps { get; private set; } = [];
    public int Total { get; private set; }
    public int Right { get; private set; }
    public double? LogLoss { get; private set; }
    public List<PredictionRecord.Row> Rows { get; private set; } = [];
    public Dictionary<string, string> Teams { get; private set; } = [];
    public SiteDoc Site { get; private set; } = null!;
    public int Pages => Math.Max(1, (Total + PredictionRecord.Page - 1) / PredictionRecord.Page);

    public string TeamName(int id) => Teams.GetValueOrDefault(id.ToString(CultureInfo.InvariantCulture)) ?? Site.TeamName(id);

    // this page's address with one choice changed, the others kept, the defaults left out
    public string Address(string? month = null, string? comp = null, int? page = null)
    {
        var q = new List<string>();
        if ((month ?? Month) is var m && m != "all") q.Add($"m={m}");
        if ((comp ?? Comp) is var c && c != "all") q.Add($"c={c}");
        if ((page ?? 1) is var p && p > 1) q.Add($"p={p}");
        return "/record" + (q.Count > 0 ? "?" + string.Join("&", q) : "");
    }

    public async Task OnGet()
    {
        ViewData["TabHead"] = TabHead.For("Prediction record", "record");
        if (!Visitor.Of(HttpContext).SignedIn) Response.Headers.CacheControl = "public, max-age=300";
        Site = await db.KeptDoc<SiteDoc>("site");
        var q = Request.Query;
        var range = PredictionRecord.MonthRange(q["m"].ToString());
        Month = range is null ? "all" : q["m"].ToString();
        int? league = int.TryParse(q["c"].ToString(), NumberStyles.None, CultureInfo.InvariantCulture, out var lg) ? lg : null;
        PageNo = int.TryParse(q["p"].ToString(), NumberStyles.None, CultureInfo.InvariantCulture, out var pg) && pg is >= 1 and <= 1000 ? pg : 1;

        var ask = new Dictionary<string, object> { ["p_limit"] = PredictionRecord.Page, ["p_offset"] = (PageNo - 1) * PredictionRecord.Page };
        if (range is { } r) { ask["p_from"] = r.From.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture); ask["p_to"] = r.To.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture); }
        if (league is { } l) ask["p_leagues"] = new[] { l };
        PredictionRecordDoc? d;
        try { d = await db.KeptAsk<PredictionRecordDoc>("site_prediction_record", ask, TimeSpan.FromMinutes(5)); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or System.Text.Json.JsonException) { d = null; }
        if (d is not { Any: true }) return;

        Months = PredictionRecord.Months(d.Since, clock.GetUtcNow());
        // the competitions with matches in the month, the most first; one picked stays in the list
        var counts = d.Comps ?? [];
        Comps = counts.OrderByDescending(kv => kv.Value).ThenBy(kv => Site.LeagueName(int.Parse(kv.Key, CultureInfo.InvariantCulture)), StringComparer.Ordinal)
            .Select(kv => (kv.Key, $"{Site.LeagueName(int.Parse(kv.Key, CultureInfo.InvariantCulture))} ({Js.Num(kv.Value)})")).ToList();
        Comp = league is { } picked ? picked.ToString(CultureInfo.InvariantCulture) : "all";
        if (Comp != "all" && !counts.ContainsKey(Comp)) Comps.Add((Comp, $"{Site.LeagueName(league!.Value)} (0)"));
        Total = d.Total ?? 0;
        Right = d.Right ?? 0;
        LogLoss = d.LogLoss;
        Teams = d.Teams ?? [];
        Rows = (d.Rows ?? []).Select(PredictionRecord.Read).ToList();
        State = Total == 0 ? "empty" : "ok";
    }
}
