using System.Text.Json;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// The Admin area is the site administrator's only (web/src/lib/server/admin.ts). Who that is, the
// database decides: its am_admin() and admin_doc() answer for the visitor whose own token the
// request carries, from a list of administrators set by hand (db/migrations/20261013_admin_area.sql).
// Being signed in is not enough, and nothing in the browser is asked. No key that could read the
// documents without that token is held by this site.
public static class Admin
{
    // Every address the gate covers: /admin and everything under it, pages, their data and endpoints
    public static bool IsAdminPath(string path) => path == "/admin" || path.StartsWith("/admin/", StringComparison.Ordinal);

    // Whether this visitor is an administrator: asked once a request (the gate, and the menu's
    // Admin links). Any failure is a "no".
    public static Task<bool> IsAdmin(Database db, HttpContext context)
    {
        if (context.Items.TryGetValue(nameof(IsAdmin), out var kept) && kept is Task<bool> t) return t;
        var asked = Ask(db, Visitor.Of(context).Token);
        context.Items[nameof(IsAdmin)] = asked;
        return asked;
    }
    static async Task<bool> Ask(Database db, string? token)
    {
        if (token is null) return false;
        try { return (await db.SiteAsk<JsonElement>("am_admin", new { }, token)).ValueKind == JsonValueKind.True; }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { return false; }
    }

    // The Admin area, every address under /admin (pages, the data behind them, anything added later):
    // checked before any of it runs, and by the database, not by this code. A visitor who isn't
    // signed in is sent to sign in; one who is and isn't an administrator is told there is no such
    // page. The documents themselves are refused by the database again.
    public static async Task<bool> Gate(HttpContext context)
    {
        if (!IsAdminPath(context.Request.Path.Value ?? "")) return true;
        var visitor = Visitor.Of(context);
        if (visitor.Token is null)
        {
            context.Response.StatusCode = 303;
            context.Response.Headers.Location = "/account";
            return false;
        }
        if (!await IsAdmin(context.RequestServices.GetRequiredService<Database>(), context))
        {
            context.Response.StatusCode = 404;
            return false;
        }
        context.Items[nameof(Visitor)] = visitor with { Admin = true };
        return true;
    }

    // One of the administrator's documents ("bets", "model_changes", "live_tracking"), or null where
    // the export has not stored it yet; Refused where the database won't hand it to this visitor
    public sealed record Answer<T>(bool Refused, T? Doc);
    sealed record DocAnswer<T>(bool? Ok, T? Doc);
    public static async Task<Answer<T>> Doc<T>(Database db, string? token, string name) where T : class
    {
        if (token is null) return new(true, null);
        var a = await db.SiteAsk<DocAnswer<T>?>("admin_doc", new { p_name = name }, token);
        return a?.Ok == true ? new(false, a.Doc) : new(true, null);
    }

    // Which match model is live and the last switches, for an administrator; null for anyone else,
    // or before db/migrations/20261014_challenger_model.sql is applied
    public static readonly string[] MatchModels = ["base", "a18"];
    public static readonly Dictionary<string, string> MatchModelLabels = new()
    {
        ["base"] = "The base model (club rank with movers, new clubs and shots)",
        ["a18"] = "The base model with A18’s boosted trees",
    };
    public static string OtherModel(string live) => live == "base" ? "a18" : "base";
    public sealed record Switch(string At, string Live);
    public sealed record MatchModel(string Live, List<Switch> Switches);
    sealed record MatchModelAnswer(bool? Ok, string? Live, List<Switch>? Switches);
    static MatchModel? AsMatchModel(MatchModelAnswer? a) =>
        a?.Ok == true && a.Live is { } live && MatchModels.Contains(live) ? new(live, a.Switches ?? []) : null;

    public static async Task<MatchModel?> LiveModel(Database db, string? token)
    {
        if (token is null) return null;
        try { return AsMatchModel(await db.SiteAsk<MatchModelAnswer?>("admin_match_model", new { }, token)); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { return null; }
    }
    // Switch the live model; the database checks the caller is an administrator. From the next run.
    public static async Task<MatchModel?> SwitchModel(Database db, string? token, string live)
    {
        if (token is null) return null;
        try { return AsMatchModel(await db.SiteAsk<MatchModelAnswer?>("admin_set_match_model", new { p_live = live }, token)); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { return null; }
    }
    // Both match models compared on the same finished and upcoming matches, for an administrator
    public static async Task<JsonElement?> Compare(Database db, string? token)
    {
        if (token is null) return null;
        try
        {
            var a = await db.SiteAsk<JsonElement>("admin_match_model_compare", new { }, token);
            return a.ValueKind == JsonValueKind.Object && a.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True
                && a.TryGetProperty("upcoming", out var up) && up.ValueKind == JsonValueKind.Object
                && a.TryGetProperty("apart", out var apart) && apart.ValueKind == JsonValueKind.Array ? a : null;
        }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { return null; }
    }
}
