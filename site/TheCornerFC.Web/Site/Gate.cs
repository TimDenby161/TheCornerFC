using System.Security.Cryptography;

namespace TheCornerFC.Web.Site;

// What every request passes through before and after its page (web/src/hooks.server.ts and
// web/src/lib/server/headers.ts).
public static class Gate
{
    // The security headers every page and redirect carries (audit finding S19, 2026-10-16):
    //   Strict-Transport-Security   browsers use https for a year, here and on every subdomain
    //   X-Content-Type-Options      a file is only ever what its type says
    //   Referrer-Policy             other sites see only thecornerfc.com, never the page
    //   Permissions-Policy          no page may ask for the camera, microphone, location, payment
    //                               handler or USB, or join ad-topic tracking
    public static readonly IReadOnlyDictionary<string, string> SecurityHeaders = new Dictionary<string, string>
    {
        ["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains",
        ["X-Content-Type-Options"] = "nosniff",
        ["Referrer-Policy"] = "strict-origin-when-cross-origin",
        ["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
    };

    const string NonceKey = "csp-nonce";
    public static string Nonce(this HttpContext context) => (string)context.Items[NonceKey]!;

    // What a page may load and run. Scripts: this site's own files, the ones it writes into the
    // page (named by a one-off nonce) and Cloudflare's bot check. No inline styles, nothing framed
    // by another site, and the browser talks to this server only: the database is asked from here.
    public static string Policy(SiteEnvironment env, string nonce) => string.Join("; ",
        "default-src 'self'",
        $"script-src 'self' 'nonce-{nonce}' https://challenges.cloudflare.com",
        "frame-src https://challenges.cloudflare.com",
        "style-src 'self'",
        "img-src 'self' https://flagcdn.com",
        "connect-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        // a form may go on to Google's sign-in by way of the sign-in service, and to Stripe's
        // checkout and its page for managing a subscription
        $"form-action 'self' {env.Url} https://accounts.google.com https://checkout.stripe.com https://billing.stripe.com",
        "frame-ancestors 'none'");

    // Where a request is sent before any page runs, or null to go on: the site's address over
    // http, and www, go to https on the site's own address; the old site's files by their old
    // names (/terms.html) go to the page here.
    public static string? Redirect(SiteEnvironment env, string scheme, string host, string path, string query)
    {
        if ((host == env.Host && scheme == "http") || host == $"www.{env.Host}")
            return $"https://{env.Host}{path}{query}";
        return Menu.OldFile(path) is { } moved ? moved + query : null;
    }

    public static IApplicationBuilder UseGate(this IApplicationBuilder app, SiteEnvironment env) => app.Use(async (context, next) =>
    {
        var request = context.Request;
        var response = context.Response;
        // The other copy's address reaching this server means a staging server is answering for the
        // live site or the other way round: serve nothing.
        var other = SiteEnvironment.All.Values.First(e => e != env);
        if (request.Host.Host == other.Host)
        {
            response.StatusCode = 500;
            await response.WriteAsync("This server is not for this site");
            return;
        }

        // hex, not Base64: a + or / in it would be escaped where the page writes it, and the script
        // tag would no longer match the policy
        var nonce = Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16));
        context.Items[NonceKey] = nonce;
        response.OnStarting(() =>
        {
            var h = response.Headers;
            foreach (var (k, v) in SecurityHeaders) h[k] = v;
            if (response.ContentType?.StartsWith("text/html", StringComparison.Ordinal) == true)
                h.ContentSecurityPolicy = Policy(env, nonce);
            // a page differs by who asks: nothing may hand one visitor's copy to another
            h.Append("Vary", "Cookie");
            // staging is never for search engines, whatever links to it
            if (!env.IsProduction) h["X-Robots-Tag"] = "noindex, nofollow";
            return Task.CompletedTask;
        });

        if (Redirect(env, request.Scheme, request.Host.Host, request.Path.Value ?? "/", request.QueryString.Value ?? "") is { } to)
        {
            response.StatusCode = 301;
            response.Headers.Location = to;
            return;
        }
        await next(context);
    });
}
