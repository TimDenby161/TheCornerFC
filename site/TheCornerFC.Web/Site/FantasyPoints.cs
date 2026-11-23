using System.IO.Compression;
using System.Text;
using System.Text.Json;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// The Fantasy points page's data (/fantasy-points, T-104): every Premier League player's expected
// points by gameweek, for any signed-in account (owner's decision 2026-11-23). It is never written
// into a page: the visitor's browser asks /fantasy/points. Each ask checks the visitor with the
// database (fantasy_points_stamp, about 100 bytes, with their own token); the document itself
// (about 1 MB) is the same for everyone, so the server keeps one copy, gzipped once, and asks for
// it again only when the stamp says the nightly export has changed it
// (db/migrations/20261123_fantasy_points_public.sql).
public sealed class FantasyPointsCache
{
    public sealed record Copy(string Stamp, byte[] Plain, byte[] Gzipped);
    readonly SemaphoreSlim one = new(1, 1);
    Copy? kept;

    public Copy? Kept => kept;

    // The document for this stamp: the one kept, or asked for (by one request at a time)
    public async Task<Copy> For(string stamp, Func<Task<string>> fetch)
    {
        if (kept is { } k && k.Stamp == stamp) return k;
        await one.WaitAsync();
        try
        {
            if (kept is { } again && again.Stamp == stamp) return again;
            var text = await fetch();
            var plain = Encoding.UTF8.GetBytes(text);
            using var packed = new MemoryStream();
            using (var gz = new GZipStream(packed, CompressionLevel.Optimal, leaveOpen: true)) gz.Write(plain);
            var copy = new Copy(StampOf(text) ?? stamp, plain, packed.ToArray());
            // (a document answered as not ok isn't kept: the next ask tries again)
            if (OkOf(text)) kept = copy;
            return copy;
        }
        finally { one.Release(); }
    }

    static string? StampOf(string text)
    {
        try { return JsonDocument.Parse(text).RootElement.TryGetProperty("updated_at", out var u) ? u.ToString() : null; }
        catch (JsonException) { return null; }
    }
    static bool OkOf(string text)
    {
        try { return JsonDocument.Parse(text).RootElement.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True; }
        catch (JsonException) { return false; }
    }

    public static void Map(WebApplication app)
    {
        app.MapGet("/fantasy/points", async (HttpContext c, Database db, FantasyPointsCache cache) =>
        {
            c.Response.Headers.CacheControl = "private, no-store";
            c.Response.Headers.Vary = "Accept-Encoding";
            if (Visitor.Of(c).Token is not { } token)
                return Results.Json(new { ok = false, error = "Sign in to see this" }, Database.Json, statusCode: 401);
            try
            {
                var check = await db.SiteAsk<JsonElement>("fantasy_points_stamp", new { }, token);
                if (!check.TryGetProperty("ok", out var ok) || ok.ValueKind != JsonValueKind.True)
                    return Results.Json(new { ok = false, error = check.TryGetProperty("error", out var why) ? why.GetString() : "Sign in to see this" }, Database.Json);
                var stamp = check.TryGetProperty("updated_at", out var u) ? u.ToString() : "";
                var copy = await cache.For(stamp, () => db.SiteAskText("fantasy_points_doc", new { }, token));
                if (c.Request.Headers.AcceptEncoding.ToString().Contains("gzip", StringComparison.OrdinalIgnoreCase))
                {
                    c.Response.Headers.ContentEncoding = "gzip";
                    return Results.Bytes(copy.Gzipped, "application/json");
                }
                return Results.Bytes(copy.Plain, "application/json");
            }
            catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException)
            {
                return Results.Json(new { ok = false, error = "Couldn't reach the database just now." }, Database.Json);
            }
        });
    }
}
