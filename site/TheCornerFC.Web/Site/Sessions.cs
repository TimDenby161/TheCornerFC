using System.Text;
using System.Text.Json;

namespace TheCornerFC.Web.Site;

// Who is signed in (web/src/hooks.server.ts). The session lives in a cookie the page's scripts can't
// read (HttpOnly), sent only to this site and, on the live site, only over HTTPS; nothing about it is
// kept in the browser's storage. The token in it is what the database checks for itself on every
// request it is sent with, so nothing here decides what a visitor may see.
public static class Sessions
{
    public const string Cookie = "sb-session", PkceCookie = "sb-pkce";
    // a session is renewed when it has less than this left (as Supabase's own library does)
    static readonly TimeSpan Margin = TimeSpan.FromSeconds(90);
    // the kinds of emailed link that sign in
    static readonly HashSet<string> LinkTypes = ["signup", "email", "recovery", "magiclink", "invite", "email_change"];
    static readonly string[] LinkParams = ["code", "token_hash", "type", "error", "error_code", "error_description"];

    static CookieOptions Options(HttpRequest request, TimeSpan life) => new()
    {
        HttpOnly = true, Secure = request.IsHttps, SameSite = SameSiteMode.Lax, Path = "/", MaxAge = life,
    };
    public static void Keep(HttpContext c, Session s) =>
        c.Response.Cookies.Append(Cookie, Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(s)), Options(c.Request, TimeSpan.FromDays(400)));
    public static void Forget(HttpContext c) => c.Response.Cookies.Delete(Cookie, Options(c.Request, TimeSpan.Zero));
    public static void KeepVerifier(HttpContext c, string verifier) => c.Response.Cookies.Append(PkceCookie, verifier, Options(c.Request, TimeSpan.FromMinutes(10)));

    // the kinds of request a form sends (a script's own requests, JSON, are another matter)
    static bool IsForm(string? type) => type is not null &&
        (type.StartsWith("application/x-www-form-urlencoded", StringComparison.OrdinalIgnoreCase) || type.StartsWith("multipart/form-data", StringComparison.OrdinalIgnoreCase)
         || type.StartsWith("text/plain", StringComparison.OrdinalIgnoreCase));

    public static Session? Read(HttpRequest request)
    {
        if (request.Cookies[Cookie] is not { Length: > 0 } raw) return null;
        try
        {
            var s = JsonSerializer.Deserialize<Session>(Encoding.UTF8.GetString(Convert.FromBase64String(raw)));
            return s is { AccessToken.Length: > 0, RefreshToken.Length: > 0, UserId.Length: > 0 } ? s : null;
        }
        catch (Exception e) when (e is FormatException or JsonException) { return null; }
    }

    public static IApplicationBuilder UseSessions(this IApplicationBuilder app) => app.Use(async (context, next) =>
    {
        var auth = context.RequestServices.GetRequiredService<AuthClient>();
        var clock = context.RequestServices.GetRequiredService<TimeProvider>();
        var request = context.Request;
        // A form by the current site's addresses (/account?/signin, ?/switch: SvelteKit's form for an
        // action): the same page's handler here (?handler=signin)
        if (request.QueryString.Value is { } qs && qs.StartsWith("?/") && qs.Length > 2)
            request.QueryString = new QueryString($"?handler={Uri.EscapeDataString(qs[2..].Split('&')[0])}");
        var q = request.Query;

        // A form may only be sent here from this site's own pages (as SvelteKit checks every form
        // post): one from anywhere else, or that won't say where it is from, goes no further
        if (HttpMethods.IsPost(request.Method) && IsForm(request.ContentType) && request.Headers.Origin.ToString() != $"{request.Scheme}://{request.Host}")
        {
            context.Response.StatusCode = 403;
            await context.Response.WriteAsync("Cross-site form submissions are forbidden");
            return;
        }

        // Coming back from an emailed link (?token_hash=&type=, the form the email templates use, which
        // works in any browser) or from Google (?code=): finish the sign-in, then show the same address
        // without those. A link that has expired or been used opens the account page saying so.
        if (HttpMethods.IsGet(request.Method) && (q.ContainsKey("token_hash") || q.ContainsKey("code") || q.ContainsKey("error_description")))
        {
            var kept = q.Where(kv => !LinkParams.Contains(kv.Key)).SelectMany(kv => kv.Value.Select(v => new KeyValuePair<string, string>(kv.Key, v ?? ""))).ToList();
            var back = $"{request.Path}{(kept.Count > 0 ? "?" + Markup.Query(kept) : "")}";
            string? failed = q.ContainsKey("error_description") ? (q["error_code"].ToString() is { Length: > 0 } ec ? ec : "error") : null;
            var recovery = false;
            if (failed is null && q.ContainsKey("token_hash") && LinkTypes.Contains(q["type"].ToString()))
            {
                var a = await auth.Verify(q["token_hash"]!, q["type"]!);
                if (a.Ok && a.Session is { } s) Keep(context, s); else failed = a.Code ?? "error";
                recovery = q["type"] == "recovery";
            }
            else if (failed is null && q.ContainsKey("code"))
            {
                var verifier = request.Cookies[PkceCookie];
                var a = verifier is { Length: > 0 } v ? await auth.ExchangeCode(q["code"]!, v) : new AuthAnswer(null, "pkce_code_verifier_not_found", 400);
                if (a.Ok && a.Session is { } s) Keep(context, s); else failed = a.Code ?? "error";
                context.Response.Cookies.Delete(PkceCookie, Options(request, TimeSpan.Zero));
            }
            context.Response.StatusCode = 303;
            context.Response.Headers.Location = failed is not null ? $"/account?failed={Js.EncodeUriComponent(failed)}" : recovery ? "/account?view=newpass" : back;
            return;
        }

        // Who is signed in, if anyone: renewed first when the access token is about to run out. A
        // session the service no longer knows is forgotten; one it couldn't be asked about just now
        // counts as signed out for this request and is kept for the next.
        var session = Read(request);
        if (session is not null && DateTimeOffset.FromUnixTimeSeconds(session.ExpiresAt) - clock.GetUtcNow() < Margin)
        {
            var a = await auth.Refresh(session.RefreshToken);
            if (a.Ok && a.Session is { } fresh) { session = fresh; Keep(context, fresh); }
            else { if (!a.Unreachable) Forget(context); session = null; }
        }
        else if (session is null && request.Cookies.ContainsKey(Cookie)) Forget(context);
        var visitor = Visitor.For(context, session);
        context.Items[nameof(Visitor)] = visitor;

        // a signed-in visitor's pages are never kept, by the browser or anything between; nor is
        // anything in the Admin area, whoever asks
        if (visitor.SignedIn || Admin.IsAdminPath(request.Path.Value ?? ""))
            context.Response.OnStarting(() => { context.Response.Headers.CacheControl = "private, no-store"; return Task.CompletedTask; });
        // the Admin area: the administrator's only, checked here before any of it runs (Site/Admin.cs)
        if (!await Admin.Gate(context)) return;
        await next(context);
    });
}
