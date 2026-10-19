using System.Net;
using System.Text;
using System.Text.Json;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// Signing in on the C# site (Site/Auth.cs, Site/Sessions.cs, Pages/Account): against a stand-in for
// Supabase Auth and the database, nothing sent anywhere
public class AccountTests
{
    const string Origin = "https://thecornerfc.com";
    static HttpClient Client(SiteFactory site) =>
        site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri(Origin), HandleCookies = false });

    static string SessionJson(long expiresAt, string access = "access-1", string refresh = "refresh-1") =>
        $$$"""{"access_token":"{{{access}}}","refresh_token":"{{{refresh}}}","expires_in":3600,"expires_at":{{{expiresAt}}},"user":{"id":"user-1","email":"fan@example.com"}}""";
    static long In(TimeSpan t) => DateTimeOffset.UtcNow.Add(t).ToUnixTimeSeconds();

    // the cookie the site keeps a session in, as it writes it
    static string Cookie(long expiresAt, string access = "access-1") =>
        $"{Sessions.Cookie}={Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(new Session(access, "refresh-1", expiresAt, "user-1", "fan@example.com")))}";

    // a stand-in that answers sign-in as `auth` says, my_subscription with nothing, and the rest with null
    static SiteFactory Site(Func<HttpRequestMessage, HttpResponseMessage?>? auth = null) => new("production", r =>
        r.RequestUri!.AbsolutePath.StartsWith("/auth/v1/") ? auth?.Invoke(r) ?? StubHandler.Json("{}", HttpStatusCode.BadRequest) : StubHandler.Json("null"));

    static HttpRequestMessage Post(string path, Dictionary<string, string> form, bool json = false, string? cookie = null, string? origin = Origin)
    {
        var m = new HttpRequestMessage(HttpMethod.Post, path) { Content = new FormUrlEncodedContent(form) };
        if (origin is not null) m.Headers.Add("Origin", origin);
        if (json) m.Headers.Add("Accept", "application/json");
        if (cookie is not null) m.Headers.Add("Cookie", cookie);
        return m;
    }
    static string? SetCookie(HttpResponseMessage r, string name) =>
        r.Headers.TryGetValues("Set-Cookie", out var all) ? all.FirstOrDefault(c => c.StartsWith(name + "=")) : null;
    static string Body(SiteFactory site, HttpRequestMessage r) => site.Handler.Bodies[r];
    static bool Private(HttpResponseMessage r) => r.Headers.CacheControl is { Private: true, NoStore: true };

    [Fact]
    public async Task Signing_in_keeps_the_session_in_a_cookie_the_pages_scripts_cant_read()
    {
        using var site = Site(r => r.RequestUri!.PathAndQuery == "/auth/v1/token?grant_type=password" ? StubHandler.Json(SessionJson(In(TimeSpan.FromHours(1)))) : null);
        var r = await Client(site).SendAsync(Post("/account?handler=signin", new() { ["email"] = " fan@example.com ", ["password"] = "pw", ["cf-turnstile-response"] = "ok" }, json: true));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Contains("\"done\":\"signin\"", await r.Content.ReadAsStringAsync());
        var cookie = SetCookie(r, Sessions.Cookie)!;
        Assert.Contains("httponly", cookie.ToLowerInvariant());
        Assert.Contains("samesite=lax", cookie.ToLowerInvariant());
        Assert.Contains("secure", cookie.ToLowerInvariant());
        // what was asked: the email trimmed, the bot check's answer, the site's public key
        var asked = site.Handler.Sent.Single(m => m.RequestUri!.AbsolutePath == "/auth/v1/token");
        Assert.Contains("\"email\":\"fan@example.com\"", Body(site, asked));
        Assert.Contains("\"captcha_token\":\"ok\"", Body(site, asked));
        Assert.Equal(SiteEnvironment.Named("production").Key, asked.Headers.GetValues("apikey").Single());
    }

    [Fact]
    public async Task A_form_without_the_bot_checks_answer_or_from_another_site_goes_no_further()
    {
        using var site = Site();
        var r = await Client(site).SendAsync(Post("/account?handler=signin", new() { ["email"] = "a@b.c", ["password"] = "pw" }, json: true));
        Assert.Contains("Wait for the check above the button to finish", await r.Content.ReadAsStringAsync());
        Assert.Equal(HttpStatusCode.Forbidden, (await Client(site).SendAsync(Post("/account?handler=signin", new() { ["email"] = "a@b.c" }, origin: "https://elsewhere.example"))).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await Client(site).SendAsync(Post("/account?handler=signin", new() { ["email"] = "a@b.c" }, origin: null))).StatusCode);
        Assert.DoesNotContain(site.Handler.Sent, m => m.RequestUri!.AbsolutePath.StartsWith("/auth/"));
    }

    [Fact]
    public async Task A_wrong_password_says_so_in_words_and_without_its_script_the_page_keeps_the_email()
    {
        using var site = Site(_ => StubHandler.Json("""{"code":400,"error_code":"invalid_credentials","msg":"Invalid login credentials"}""", HttpStatusCode.BadRequest));
        var r = await Client(site).SendAsync(Post("/account?handler=signin", new() { ["email"] = "fan@example.com", ["password"] = "no", ["cf-turnstile-response"] = "ok" }));
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
        var html = await r.Content.ReadAsStringAsync();
        Assert.Equal("That email and password don&#x27;t match an account.", System.Text.RegularExpressions.Regex.Match(html, "id=\"account-msg\"[^>]*>([^<]*)<").Groups[1].Value);
        Assert.Contains("value=\"fan@example.com\"", html);
        Assert.Null(SetCookie(r, Sessions.Cookie));
    }

    [Fact]
    public async Task A_signed_in_visitors_pages_are_private_and_the_database_is_asked_with_their_token()
    {
        using var site = Site();
        var m = new HttpRequestMessage(HttpMethod.Get, "/account");
        m.Headers.Add("Cookie", Cookie(In(TimeSpan.FromHours(1))));
        var r = await Client(site).SendAsync(m);
        Assert.True(Private(r));
        Assert.Contains("Signed in as <b>fan@example.com</b>", await r.Content.ReadAsStringAsync());
        var sub = site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/rest/v1/rpc/my_subscription");
        Assert.Equal("Bearer access-1", sub.Headers.Authorization!.ToString());
        // signed out: the same page, kept nowhere private, and no token sent
        using var other = Site();
        var plain = await Client(other).GetAsync("/account");
        Assert.False(Private(plain));
        Assert.Contains("Continue with Google", await plain.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task A_session_about_to_run_out_is_renewed_and_one_the_service_no_longer_knows_is_forgotten()
    {
        var fresh = In(TimeSpan.FromHours(1));
        using var site = Site(r => r.RequestUri!.PathAndQuery == "/auth/v1/token?grant_type=refresh_token" ? StubHandler.Json(SessionJson(fresh, "access-2", "refresh-2")) : null);
        var m = new HttpRequestMessage(HttpMethod.Get, "/account");
        m.Headers.Add("Cookie", Cookie(In(TimeSpan.FromSeconds(30))));
        var r = await Client(site).SendAsync(m);
        Assert.Contains("\"refresh_token\":\"refresh-1\"", Body(site, site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/auth/v1/token")));
        Assert.NotNull(SetCookie(r, Sessions.Cookie));
        Assert.Equal("Bearer access-2", site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/rest/v1/rpc/my_subscription").Headers.Authorization!.ToString());

        using var gone = Site(_ => StubHandler.Json("""{"error_code":"refresh_token_not_found"}""", HttpStatusCode.BadRequest));
        var g = new HttpRequestMessage(HttpMethod.Get, "/account");
        g.Headers.Add("Cookie", Cookie(In(TimeSpan.FromSeconds(-30))));
        var gr = await Client(gone).SendAsync(g);
        Assert.Contains("expires=Thu, 01 Jan 1970", SetCookie(gr, Sessions.Cookie)!);
        Assert.Contains("Continue with Google", await gr.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task An_emailed_link_signs_in_and_shows_the_same_address_without_its_token()
    {
        using var site = Site(r => r.RequestUri!.AbsolutePath == "/auth/v1/verify" ? StubHandler.Json(SessionJson(In(TimeSpan.FromHours(1)))) : null);
        var r = await Client(site).GetAsync("/clubs?c=39&token_hash=abc&type=signup");
        Assert.Equal(HttpStatusCode.SeeOther, r.StatusCode);
        Assert.Equal("/clubs?c=39", r.Headers.Location!.ToString());
        Assert.NotNull(SetCookie(r, Sessions.Cookie));
        Assert.Contains("\"token_hash\":\"abc\"", Body(site, site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/auth/v1/verify")));
        // a password reset goes on to choosing the new one; a link that has been used says so
        Assert.Equal("/account?view=newpass", (await Client(site).GetAsync("/?token_hash=abc&type=recovery")).Headers.Location!.ToString());
        using var used = Site(_ => StubHandler.Json("""{"error_code":"otp_expired"}""", HttpStatusCode.Forbidden));
        Assert.Equal("/account?failed=otp_expired", (await Client(used).GetAsync("/?token_hash=abc&type=signup")).Headers.Location!.ToString());
        Assert.Equal("/account?failed=access_denied", (await Client(used).GetAsync("/?error=x&error_code=access_denied&error_description=y")).Headers.Location!.ToString());
        var page = await Client(used).GetStringAsync("/account?failed=otp_expired");
        Assert.Contains("That link has expired or has already been used. Ask for a new one.", page);
    }

    [Fact]
    public async Task Google_is_reached_with_a_one_time_key_this_browser_alone_holds()
    {
        using var site = Site(r => r.RequestUri!.PathAndQuery == "/auth/v1/token?grant_type=pkce" ? StubHandler.Json(SessionJson(In(TimeSpan.FromHours(1)))) : null);
        var r = await Client(site).SendAsync(Post("/account?handler=google", new() { ["back"] = "/clubs?c=39" }, json: true));
        var to = JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement.GetProperty("location").GetString()!;
        Assert.StartsWith($"{SiteEnvironment.Named("production").Url}/auth/v1/authorize?provider=google&redirect_to=https%3A%2F%2Fthecornerfc.com%2Fclubs%3Fc%3D39&code_challenge=", to);
        var verifier = SetCookie(r, Sessions.PkceCookie)!.Split(';')[0];
        // back with the code: the key goes with it, and is then thrown away
        var back = new HttpRequestMessage(HttpMethod.Get, "/clubs?c=39&code=xyz");
        back.Headers.Add("Cookie", verifier);
        var b = await Client(site).SendAsync(back);
        Assert.Equal("/clubs?c=39", b.Headers.Location!.ToString());
        Assert.Contains($"\"code_verifier\":\"{verifier.Split('=', 2)[1]}\"", Body(site, site.Handler.Sent.Single(x => x.RequestUri!.PathAndQuery == "/auth/v1/token?grant_type=pkce")));
        Assert.NotNull(SetCookie(b, Sessions.Cookie));
        // the code without the key (another browser): said in words
        Assert.Equal("/account?failed=pkce_code_verifier_not_found", (await Client(site).GetAsync("/?code=xyz")).Headers.Location!.ToString());
        // somewhere else to come back to is never taken
        Assert.Equal("/", AuthClient.SafePath("//evil.example/x"));
        Assert.Equal("/", AuthClient.SafePath("https://evil.example"));
        Assert.Equal("/clubs?c=r:Asia", AuthClient.SafePath("/clubs?c=r:Asia"));
    }

    [Fact]
    public async Task Signing_out_forgets_the_session_here_and_tells_the_service()
    {
        using var site = Site(r => r.RequestUri!.AbsolutePath == "/auth/v1/logout" ? new HttpResponseMessage(HttpStatusCode.NoContent) : null);
        var r = await Client(site).SendAsync(Post("/account?handler=signout", [], cookie: Cookie(In(TimeSpan.FromHours(1)))));
        Assert.Equal("/account", r.Headers.Location!.ToString());
        Assert.Contains("expires=Thu, 01 Jan 1970", SetCookie(r, Sessions.Cookie)!);
        var logout = site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/auth/v1/logout");
        Assert.Equal("?scope=local", logout.RequestUri!.Query);
        Assert.Equal("Bearer access-1", logout.Headers.Authorization!.ToString());
    }

    [Fact]
    public async Task Deleting_an_account_asks_the_database_as_its_owner_then_signs_out()
    {
        using var site = Site(r => r.RequestUri!.AbsolutePath == "/auth/v1/logout" ? new HttpResponseMessage(HttpStatusCode.NoContent) : null);
        var r = await Client(site).SendAsync(Post("/account?handler=erase", [], json: true, cookie: Cookie(In(TimeSpan.FromHours(1)))));
        Assert.Contains("\"done\":\"erased\"", await r.Content.ReadAsStringAsync());
        Assert.Equal("Bearer access-1", site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/rest/v1/rpc/delete_my_account").Headers.Authorization!.ToString());
        Assert.Contains("expires=Thu, 01 Jan 1970", SetCookie(r, Sessions.Cookie)!);
        // signed out, there is nothing to delete
        Assert.Contains("Sign in first.", await (await Client(site).SendAsync(Post("/account?handler=erase", [], json: true))).Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Creating_an_account_that_must_be_confirmed_says_a_link_has_been_sent()
    {
        using var site = Site(r => r.RequestUri!.AbsolutePath == "/auth/v1/signup"
            ? StubHandler.Json("""{"id":"user-1","email":"fan@example.com","confirmation_sent_at":"2026-10-19T10:00:00Z"}""") : null);
        var r = await Client(site).SendAsync(Post("/account?handler=signup", new() { ["email"] = "fan@example.com", ["password"] = "longenough", ["cf-turnstile-response"] = "ok" }, json: true));
        Assert.Contains("We\\u0027ve sent a link to fan@example.com", await r.Content.ReadAsStringAsync());
        Assert.Null(SetCookie(r, Sessions.Cookie));
        Assert.Equal("?redirect_to=https%3A%2F%2Fthecornerfc.com%2F", site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/auth/v1/signup").RequestUri!.Query);
    }

    [Fact]
    public async Task The_current_sites_form_addresses_reach_the_same_handlers()
    {
        using var site = Site();
        var r = await Client(site).SendAsync(Post("/account?/signin", new() { ["email"] = "a@b.c", ["password"] = "pw" }, json: true));
        Assert.Contains("Wait for the check above the button to finish", await r.Content.ReadAsStringAsync());
    }
}
