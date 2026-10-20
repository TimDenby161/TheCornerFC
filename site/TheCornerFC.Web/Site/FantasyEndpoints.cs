using System.Text.Json;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// What the three fantasy pages ask for from the owner's browser (web/src/routes/fantasy). FPL's and
// Fantasy EFL's data never goes into a page the server writes: the database answers only the site
// owner (each function checks the visitor's own token), and anyone else gets its "no".
public static class FantasyEndpoints
{
    public const int FplEntry = 3996593; // the owner's FPL entry (FPL_ENTRY in web/src/lib/fantasy.ts)
    const string NoStore = "private, no-store";

    static IResult Json(object? o) => Results.Json(o, Database.Json);
    // a whole number, as JavaScript's Number.isInteger takes one (3 and 3.0 alike)
    static long? Whole(JsonElement e) =>
        e.ValueKind == JsonValueKind.Number && e.TryGetDouble(out var x) && Math.Floor(x) == x && Math.Abs(x) <= 9007199254740991 ? (long)x : null;
    static async Task<JsonElement?> Body(HttpRequest request)
    {
        try { return (await JsonDocument.ParseAsync(request.Body)).RootElement; }
        catch (JsonException) { return null; }
    }
    static JsonElement? Field(JsonElement? b, string k) =>
        b is { ValueKind: JsonValueKind.Object } o && o.TryGetProperty(k, out var v) ? v : null;
    static bool Truthy(JsonElement? v) => v is { } e && e.ValueKind switch
    {
        JsonValueKind.True => true,
        JsonValueKind.Number => e.GetDouble() != 0 && !double.IsNaN(e.GetDouble()),
        JsonValueKind.String => e.GetString() != "",
        JsonValueKind.Object or JsonValueKind.Array => true,
        _ => false,
    };

    public static void Map(WebApplication app)
    {
        // The fantasy pages' data, for the browser of whoever is signed in. The database's answer is
        // passed straight through.
        app.MapGet("/fantasy/data", async (HttpContext c, Database db) =>
        {
            c.Response.Headers.CacheControl = NoStore;
            if (Visitor.Of(c).Token is not { } token) return Json(new { ok = false });
            try { return Results.Content(await db.SiteAskText("fpl_owner_data", new { p_entry = FplEntry }, token), "application/json"); }
            catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException)
            {
                return Json(new { ok = false, error = "Couldn't reach the database just now." });
            }
        });

        // Which of these players are in the Players list, and so have a page of their own to link to
        app.MapPost("/fantasy/known", async (HttpContext c, Database db) =>
        {
            c.Response.Headers.CacheControl = NoStore;
            if (Visitor.Of(c).Token is not { } token) return Results.Text("Sign in first", statusCode: 401);
            var ids = Field(await Body(c.Request), "ids") is { ValueKind: JsonValueKind.Array } list
                ? list.EnumerateArray().Select(Whole).OfType<long>().Take(1000).ToArray() : [];
            if (ids.Length == 0) return Json(new { ids = Array.Empty<long>() });
            var siteTask = db.KeptDoc<SiteDoc>("site");
            var answerTask = db.SiteAsk<PlayersAnswer>("site_players", new { p_ids = ids, p_limit = ids.Length }, token);
            await Task.WhenAll(siteTask, answerTask);
            var at = Array.IndexOf(siteTask.Result.PlayerFields ?? [], "id");
            return Json(new { ids = answerTask.Result.Rows.Select(r => r[at]) });
        });

        // One of the owner's ticks on the FPL page (in my team, a target), saved to their account
        app.MapPost("/fantasy/mark", async (HttpContext c, Database db) =>
        {
            c.Response.Headers.CacheControl = NoStore;
            if (Visitor.Of(c).Token is not { } token) return Results.Text("Sign in first", statusCode: 401);
            var b = await Body(c.Request);
            if (Field(b, "player") is not { } pl || Whole(pl) is not { } player) return Results.Text("Bad request", statusCode: 400);
            try
            {
                return Json(await db.SiteAsk<JsonElement>("mark_fpl_player",
                    new { p_entry = FplEntry, p_player = player, p_mine = Truthy(Field(b, "mine")), p_target = Truthy(Field(b, "target")) }, token));
            }
            catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException)
            {
                return Json(new { ok = false, error = "Couldn't save that just now." });
            }
        });

        // "I've made these transfers" on My FPL team (and its Undo): a lock for the gameweek
        app.MapPost("/fantasy/lock", async (HttpContext c, Database db) =>
        {
            c.Response.Headers.CacheControl = NoStore;
            if (Visitor.Of(c).Token is not { } token) return Results.Text("Sign in first", statusCode: 401);
            var b = await Body(c.Request);
            if (Field(b, "event") is not { } ev || Whole(ev) is not { } eventId || Field(b, "season") is not { ValueKind: not JsonValueKind.Null } season)
                return Results.Text("Bad request", statusCode: 400);
            var undo = Truthy(Field(b, "undo"));
            object args = undo
                ? new { p_entry = FplEntry, p_season = season, p_event = eventId }
                : new { p_entry = FplEntry, p_season = season, p_event = eventId,
                        p_transfers = Field(b, "transfers") is { ValueKind: JsonValueKind.Array } t ? t : JsonSerializer.SerializeToElement(Array.Empty<object>()) };
            try { return Json(await db.SiteAsk<JsonElement>(undo ? "unlock_fpl_transfers" : "lock_fpl_transfers", args, token)); }
            catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException)
            {
                return Json(new { ok = false, error = "Couldn't reach the database: nothing was saved." });
            }
        });
    }
}
