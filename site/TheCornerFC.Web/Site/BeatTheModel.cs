using System.Text.Json;
using System.Text.Json.Nodes;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// Beat the Model (/beat-the-model, T-095): signed-in accounts predict the score of every Premier
// League match of a round before kick-off, against the model's most likely score
// (db/migrations/20261123_beat_the_model.sql has the rules). Everything is asked of the database
// as the visitor, with their own token; the database decides who they are, what they may see and
// whether a pick is still open. Nothing here is kept between visitors.
public static class BeatTheModel
{
    public const int League = 39;   // the Premier League: the game's matches (btm_round)
    const string NoStore = "private, no-store";
    const string Unreachable = "Couldn't reach the database just now.";

    static IResult Json(object? o, int status = 200) => Results.Json(o, Database.Json, statusCode: status);
    static IResult SignIn() => Json(new { ok = false, error = "Sign in to play" }, 401);
    static bool Failed(Exception e) => e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException;

    static async Task<JsonElement?> Body(HttpRequest request)
    {
        try { return (await JsonDocument.ParseAsync(request.Body)).RootElement; }
        catch (JsonException) { return null; }
    }
    // a whole number in a body field, or null
    public static int? Whole(JsonElement? b, string key) =>
        b is { ValueKind: JsonValueKind.Object } o && o.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.Number
            && v.TryGetDouble(out var x) && Math.Floor(x) == x && Math.Abs(x) <= int.MaxValue ? (int)x : null;
    // a round asked for in the address (?r=13), or null for the one being played or next
    public static int? Round(HttpContext c) =>
        int.TryParse(c.Request.Query["r"], out var r) && r is >= 1 and <= 60 ? r : null;

    // The round's answer with the clubs' names beside it ("teams": {"40": "Liverpool"}), so the
    // page needn't know every club
    public static JsonNode WithTeams(JsonElement round, SiteDoc? site)
    {
        var node = JsonNode.Parse(round.GetRawText())!;
        var teams = new JsonObject();
        if (node["matches"] is JsonArray matches)
            foreach (var m in matches)
                foreach (var side in new[] { "home", "away" })
                    if (m?[side] is JsonValue v && v.TryGetValue<int>(out var id) && !teams.ContainsKey(id.ToString()))
                        teams[id.ToString()] = site?.TeamName(id) ?? $"Team {id}";
        node["teams"] = teams;
        return node;
    }

    public static void Map(WebApplication app)
    {
        app.MapGet("/btm/round", async (HttpContext c, Database db) =>
        {
            c.Response.Headers.CacheControl = NoStore;
            if (Visitor.Of(c).Token is not { } token) return SignIn();
            try
            {
                var siteTask = db.KeptDoc<SiteDoc>("site");
                var roundTask = db.SiteAsk<JsonElement>("btm_round", new { p_round = Round(c) }, token);
                try { await Task.WhenAll(siteTask, roundTask); } catch (Exception) when (roundTask.IsCompletedSuccessfully) { }
                return Json(WithTeams(roundTask.Result, siteTask.IsCompletedSuccessfully ? siteTask.Result : null));
            }
            catch (Exception e) when (Failed(e) || e is AggregateException) { return Json(new { ok = false, error = Unreachable }); }
        });

        app.MapGet("/btm/table", async (HttpContext c, Database db) =>
        {
            c.Response.Headers.CacheControl = NoStore;
            if (Visitor.Of(c).Token is not { } token) return SignIn();
            try { return Json(await db.SiteAsk<JsonElement>("btm_table", new { p_round = Round(c) }, token)); }
            catch (Exception e) when (Failed(e)) { return Json(new { ok = false, error = Unreachable }); }
        });

        // A pick: {"fixture": 1, "home": 2, "away": 1}. Final once saved; answers the model's score
        app.MapPost("/btm/pick", async (HttpContext c, Database db) =>
        {
            c.Response.Headers.CacheControl = NoStore;
            if (Visitor.Of(c).Token is not { } token) return SignIn();
            var b = await Body(c.Request);
            if (Whole(b, "fixture") is not { } fixture || Whole(b, "home") is not { } home || Whole(b, "away") is not { } away)
                return Json(new { ok = false, error = "Not a valid score" }, 400);
            try { return Json(await db.SiteAsk<JsonElement>("btm_pick", new { p_fixture = fixture, p_home = home, p_away = away }, token)); }
            catch (Exception e) when (Failed(e)) { return Json(new { ok = false, error = "Couldn't reach the database: the pick wasn't saved." }); }
        });

        // The name shown in the table: {"name": "..."}
        app.MapPost("/btm/name", async (HttpContext c, Database db) =>
        {
            c.Response.Headers.CacheControl = NoStore;
            if (Visitor.Of(c).Token is not { } token) return SignIn();
            var b = await Body(c.Request);
            var name = b is { ValueKind: JsonValueKind.Object } o && o.TryGetProperty("name", out var n) && n.ValueKind == JsonValueKind.String ? n.GetString() : null;
            if (name is null || name.Length > 40) return Json(new { ok = false, error = "Not a valid name" }, 400);
            try { return Json(await db.SiteAsk<JsonElement>("btm_set_name", new { p_name = name }, token)); }
            catch (Exception e) when (Failed(e)) { return Json(new { ok = false, error = "Couldn't reach the database: the name wasn't saved." }); }
        });
    }
}
