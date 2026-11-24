using Microsoft.Extensions.Caching.Memory;
using SkiaSharp;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// The picture a shared link shows (og:image, T-094): a match's chances or result, or a club's world
// place, drawn as a 1200x630 PNG. A card holds only what a visitor who isn't signed in sees on the
// page: it reads the match as signed out, so chances the paywall holds back are never drawn.
// Drawn once, then kept here (up to 25 MB) and by Cloudflare for the max-age it is answered with.
public static class ShareCards
{
    public const int W = 1200, H = 630;
    public sealed record MatchCard(string Home, string Away, string Line, int? Hg, int? Ag, int[]? Probs, bool Finished);
    public sealed record ClubCard(string Name, string? Line, int Place, int Total, int Current, int? Form);

    static readonly SKColor Pitch = SKColor.Parse("#0e3b29"), Chalk = SKColor.Parse("#f4f1e8"),
        Soft = SKColor.Parse("#9fbfa9"), Panel = SKColor.Parse("#16533a");

    static readonly Lazy<(SKTypeface Bold, SKTypeface Medium)> Faces = new(() =>
    {
        var dir = Path.Combine(AppContext.BaseDirectory, "ShareFonts");
        return (SKTypeface.FromFile(Path.Combine(dir, "Archivo-ExtraBold.ttf")) ?? SKTypeface.Default,
                SKTypeface.FromFile(Path.Combine(dir, "Archivo-Medium.ttf")) ?? SKTypeface.Default);
    });

    static readonly MemoryCache Kept = new(new MemoryCacheOptions { SizeLimit = 25_000_000 });

    // A card from the cache, or drawn and kept for `keepFor`
    public static async Task<byte[]?> KeptOr(string key, TimeSpan keepFor, Func<Task<byte[]?>> draw)
    {
        if (Kept.TryGetValue(key, out byte[]? hit)) return hit;
        var bytes = await draw();
        if (bytes is not null)
            Kept.Set(key, bytes, new MemoryCacheEntryOptions { Size = bytes.Length, AbsoluteExpirationRelativeToNow = keepFor });
        return bytes;
    }

    // The largest size up to `max` at which `text` fits in `width`
    static float Fit(string text, SKTypeface face, float max, float width)
    {
        using var font = new SKFont(face, max);
        var w = font.MeasureText(text);
        return w <= width ? max : Math.Max(18, max * width / w);
    }

    static void Text(SKCanvas c, string text, SKTypeface face, float size, float x, float y, SKColor color, SKTextAlign align = SKTextAlign.Left)
    {
        using var font = new SKFont(face, size);
        using var paint = new SKPaint { Color = color, IsAntialias = true };
        c.DrawText(text, x, y, align, font, paint);
    }

    static void Box(SKCanvas c, SKRect r, SKColor color)
    {
        using var paint = new SKPaint { Color = color, IsAntialias = true };
        c.DrawRoundRect(r, 18, 18, paint);
    }

    // The frame every card shares: the name at the top, the line beside it, the address at the foot
    static byte[] Frame(string line, Action<SKCanvas, SKTypeface, SKTypeface> body)
    {
        var (bold, medium) = Faces.Value;
        using var surface = SKSurface.Create(new SKImageInfo(W, H, SKColorType.Rgba8888, SKAlphaType.Premul));
        var c = surface.Canvas;
        c.Clear(Pitch);
        Text(c, "TheCorner FC", bold, 34, 60, 82, Chalk);
        Text(c, line, medium, Fit(line, medium, 30, 700), W - 60, 80, Soft, SKTextAlign.Right);
        body(c, bold, medium);
        Text(c, "thecornerfc.com", bold, 30, 60, H - 44, Chalk);
        Text(c, "Club ratings and the model's chances for every match", medium, 24, W - 60, H - 46, Soft, SKTextAlign.Right);
        using var image = surface.Snapshot();
        using var data = image.Encode(SKEncodedImageFormat.Png, 100);
        return data.ToArray();
    }

    public static byte[] Draw(MatchCard m) => Frame(m.Line, (c, bold, medium) =>
    {
        // the two sides either side of the score, or of "v" before kick-off
        const float mid = W / 2f, nameY = 235, side = 430;
        var nameSize = Math.Min(Fit(m.Home, bold, 66, side), Fit(m.Away, bold, 66, side));
        Text(c, m.Home, bold, nameSize, mid - 90, nameY, Chalk, SKTextAlign.Right);
        Text(c, m.Away, bold, nameSize, mid + 90, nameY, Chalk);
        if (m.Finished && m.Hg is { } hg && m.Ag is { } ag)
            Text(c, $"{hg}–{ag}", bold, 76, mid, nameY + 6, Chalk, SKTextAlign.Center);
        else
            Text(c, "v", medium, 48, mid, nameY - 4, Soft, SKTextAlign.Center);

        if (m.Probs is { Length: 3 } p)
        {
            Text(c, m.Finished ? "The model's chances before kick-off" : "The model's chances", medium, 28, 60, 330, Soft);
            string[] labels = [$"{m.Home} win", "Draw", $"{m.Away} win"];
            var top = Array.IndexOf(p, p.Max());
            for (var i = 0; i < 3; i++)
            {
                var r = SKRect.Create(60 + i * 365, 355, 350, 165);
                var best = i == top;
                Box(c, r, best ? Chalk : Panel);
                var ink = best ? Pitch : Chalk;
                Text(c, $"{p[i]}%", bold, 76, r.MidX, r.Top + 92, ink, SKTextAlign.Center);
                Text(c, labels[i], medium, Fit(labels[i], medium, 28, r.Width - 40), r.MidX, r.Top + 138, ink, SKTextAlign.Center);
            }
        }
        else if (!m.Finished)
        {
            var r = SKRect.Create(60, 355, W - 120, 165);
            Box(c, r, Panel);
            Text(c, "The model's win, draw and loss chances", bold, 40, r.MidX, r.Top + 75, Chalk, SKTextAlign.Center);
            Text(c, "free on the site for every match in the next 7 days", medium, 30, r.MidX, r.Top + 122, Soft, SKTextAlign.Center);
        }
    });

    public static byte[] Draw(ClubCard k) => Frame(k.Line ?? "Club rating", (c, bold, medium) =>
    {
        Text(c, k.Name, bold, Fit(k.Name, bold, 96, W - 120), 60, 250, Chalk);
        (string Big, string Small)[] stats =
        [
            ($"#{k.Place:N0}", "in the world"),
            (k.Current.ToString(), "Current strength"),
            (k.Form is { } f ? (f > 0 ? $"+{f}" : f < 0 ? $"−{-f}" : "0") : "–", "Over the last 6 matches"),
        ];
        for (var i = 0; i < 3; i++)
        {
            var r = SKRect.Create(60 + i * 365, 330, 350, 190);
            Box(c, r, i == 0 ? Chalk : Panel);
            var ink = i == 0 ? Pitch : Chalk;
            Text(c, stats[i].Big, bold, Fit(stats[i].Big, bold, 84, r.Width - 40), r.MidX, r.Top + 108, ink, SKTextAlign.Center);
            Text(c, stats[i].Small, medium, Fit(stats[i].Small, medium, 26, r.Width - 30), r.MidX, r.Top + 155, ink, SKTextAlign.Center);
        }
    });

    // What the cards are drawn from, as a visitor who isn't signed in sees it
    public static async Task<(MatchCard Card, bool Done)?> MatchFor(Database db, string id, DateTimeOffset now)
    {
        var b = await MatchEndpoints.Base(db, id, null);
        if (b is not { } x) return null;
        var v = Cards.Of(x.Site, new Dictionary<int, Club>(), x.M, x.Paywall, now);
        var day = Times.Show(DateTimeOffset.Parse(x.M.Kickoff), "Europe/London", "day");
        return (new MatchCard(v.Home.Name, v.Away.Name, $"{x.Site.CompLabel(x.M.League)} · {day}", v.Hg, v.Ag, v.Probs, v.Finished), v.Finished);
    }

    public static async Task<ClubCard?> ClubFor(Database db, string id)
    {
        var c = await ClubBase.Load(db, id);
        if (c?.Rank is not { } r) return null;
        var league = c.Site.CompLabel(r.League);
        return new ClubCard(c.Name, string.IsNullOrEmpty(league) ? null : league, c.All.Count(x => x.Current > r.Current) + 1, c.All.Count,
            Js.RoundInt(r.Current), r.Form is { } f ? Js.RoundInt(f) : null);
    }

    public static void Map(WebApplication app)
    {
        // Only link previews and search engines ask for these. An address with no match or club
        // behind it is answered 404 and draws nothing.
        app.MapGet("/share/match/{id}.png", async (string id, HttpContext ctx, Database db, TimeProvider clock) =>
        {
            var done = false;
            var bytes = await KeptOr($"match:{id}", TimeSpan.FromMinutes(30), async () =>
            {
                var m = await MatchFor(db, id, clock.GetUtcNow());
                if (m is not { } x) return null;
                done = x.Done;
                return Draw(x.Card);
            });
            if (bytes is null) return Results.NotFound();
            ctx.Response.Headers.CacheControl = done ? "public, max-age=86400" : "public, max-age=3600";
            return Results.File(bytes, "image/png");
        });
        app.MapGet("/share/club/{id}.png", async (string id, HttpContext ctx, Database db) =>
        {
            var bytes = await KeptOr($"club:{id}", TimeSpan.FromHours(6), async () => await ClubFor(db, id) is { } k ? Draw(k) : null);
            if (bytes is null) return Results.NotFound();
            ctx.Response.Headers.CacheControl = "public, max-age=86400";
            return Results.File(bytes, "image/png");
        });
    }
}
