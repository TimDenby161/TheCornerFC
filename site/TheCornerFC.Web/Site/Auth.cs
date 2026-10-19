using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TheCornerFC.Web.Site;

// A signed-in visitor's session with Supabase Auth: the access token the database checks on every
// request it is sent with, the refresh token that gets a new one, and when the access token runs out
public sealed record Session(
    [property: JsonPropertyName("access_token")] string AccessToken,
    [property: JsonPropertyName("refresh_token")] string RefreshToken,
    [property: JsonPropertyName("expires_at")] long ExpiresAt,
    [property: JsonPropertyName("user_id")] string UserId,
    [property: JsonPropertyName("email")] string Email);

// What Supabase Auth answered: a session, or what went wrong (its code, as the error messages know them)
public sealed record AuthAnswer(Session? Session, string? Code, int Status = 200, bool Unreachable = false)
{
    public bool Ok => Code is null && !Unreachable;
}

// Sign-in is the server's job (web/src/lib/server/auth.ts, which uses Supabase's own library; this
// asks Supabase Auth's web addresses directly). Every request carries the site's public key, and a
// signed-in visitor's own access token where it acts as them.
public sealed class AuthClient(HttpClient http, SiteEnvironment env)
{
    static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    string Auth(string path) => $"{env.Url}/auth/v1/{path}";

    sealed record UserAnswer(string? Id, string? Email);
    sealed record SessionAnswer(
        [property: JsonPropertyName("access_token")] string? AccessToken, [property: JsonPropertyName("refresh_token")] string? RefreshToken,
        [property: JsonPropertyName("expires_in")] long? ExpiresIn, [property: JsonPropertyName("expires_at")] long? ExpiresAt, UserAnswer? User);
    // Supabase Auth's errors: error_code where it gives one (the newer form), or error (the older).
    // (Its "code" is the HTTP status, a number: not read)
    sealed record ErrorAnswer([property: JsonPropertyName("error_code")] string? ErrorCode, string? Error);

    async Task<(HttpStatusCode Status, string Body)?> Send(HttpMethod method, string url, object? body, string? token)
    {
        try
        {
            using var m = new HttpRequestMessage(method, url);
            m.Headers.Add("apikey", env.Key);
            if (token is not null) m.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            if (body is not null) m.Content = new StringContent(JsonSerializer.Serialize(body, Json), Encoding.UTF8, "application/json");
            using var r = await http.SendAsync(m);
            return (r.StatusCode, await r.Content.ReadAsStringAsync());
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException) { return null; }
    }

    static AuthAnswer Failed((HttpStatusCode Status, string Body) r)
    {
        string? code = null;
        try
        {
            var e = JsonSerializer.Deserialize<ErrorAnswer>(r.Body, Json);
            code = e?.ErrorCode ?? e?.Error;
        }
        catch (JsonException) { }
        return new(null, code ?? "error", (int)r.Status);
    }

    // a session from an answer that carries one (null where it has none: an email still to confirm)
    static Session? SessionOf(string body, DateTimeOffset now)
    {
        var s = JsonSerializer.Deserialize<SessionAnswer>(body, Json);
        if (s?.AccessToken is not { Length: > 0 } access || s.RefreshToken is not { Length: > 0 } refresh || s.User?.Id is not { } id) return null;
        var expires = s.ExpiresAt ?? now.ToUnixTimeSeconds() + (s.ExpiresIn ?? 3600);
        return new(access, refresh, expires, id, s.User.Email ?? "");
    }

    async Task<AuthAnswer> SessionCall(HttpMethod method, string url, object? body, string? token = null)
    {
        var r = await Send(method, url, body, token);
        if (r is null) return new(null, null, 0, Unreachable: true);
        if ((int)r.Value.Status >= 300) return Failed(r.Value);
        return new(SessionOf(r.Value.Body, DateTimeOffset.UtcNow), null);
    }
    static object Captcha(string? token) => new { captcha_token = token };

    public Task<AuthAnswer> SignIn(string email, string password, string? captcha) =>
        SessionCall(HttpMethod.Post, Auth("token?grant_type=password"), new { email, password, gotrue_meta_security = Captcha(captcha) });

    // (a session at once where the project doesn't ask for the email to be confirmed; none where it does)
    public Task<AuthAnswer> SignUp(string email, string password, string? captcha, string redirectTo) =>
        SessionCall(HttpMethod.Post, Auth($"signup?redirect_to={Uri.EscapeDataString(redirectTo)}"), new { email, password, gotrue_meta_security = Captcha(captcha) });

    public async Task<AuthAnswer> Recover(string email, string? captcha, string redirectTo)
    {
        var r = await Send(HttpMethod.Post, Auth($"recover?redirect_to={Uri.EscapeDataString(redirectTo)}"), new { email, gotrue_meta_security = Captcha(captcha) }, null);
        return r is null ? new(null, null, 0, true) : (int)r.Value.Status >= 300 ? Failed(r.Value) : new(null, null);
    }

    // an emailed link's token (the form the email templates use: ?token_hash=&type=)
    public Task<AuthAnswer> Verify(string tokenHash, string type) =>
        SessionCall(HttpMethod.Post, Auth("verify"), new { token_hash = tokenHash, type });

    // back from Google with a code, which only the browser that set off holds the key to (PKCE)
    public Task<AuthAnswer> ExchangeCode(string code, string verifier) =>
        SessionCall(HttpMethod.Post, Auth("token?grant_type=pkce"), new { auth_code = code, code_verifier = verifier });

    public Task<AuthAnswer> Refresh(string refreshToken) =>
        SessionCall(HttpMethod.Post, Auth("token?grant_type=refresh_token"), new { refresh_token = refreshToken });

    public async Task<AuthAnswer> UpdatePassword(string token, string password)
    {
        var r = await Send(HttpMethod.Put, Auth("user"), new { password }, token);
        return r is null ? new(null, null, 0, true) : (int)r.Value.Status >= 300 ? Failed(r.Value) : new(null, null);
    }

    // this browser only
    public async Task<AuthAnswer> SignOut(string token)
    {
        var r = await Send(HttpMethod.Post, Auth("logout?scope=local"), null, token);
        // an access token that has already run out has nothing left to sign out of
        return r is null ? new(null, null, 0, true) : (int)r.Value.Status >= 300 && r.Value.Status != HttpStatusCode.Unauthorized && r.Value.Status != HttpStatusCode.Forbidden ? Failed(r.Value) : new(null, null);
    }

    // Where to send the visitor to sign in with Google, and the key that finishes it when they come back
    public (string Url, string Verifier) GoogleUrl(string redirectTo)
    {
        var verifier = Base64Url(RandomNumberGenerator.GetBytes(48));
        var challenge = Base64Url(SHA256.HashData(Encoding.ASCII.GetBytes(verifier)));
        return (Auth($"authorize?provider=google&redirect_to={Uri.EscapeDataString(redirectTo)}&code_challenge={challenge}&code_challenge_method=s256"), verifier);
    }
    static string Base64Url(byte[] b) => Convert.ToBase64String(b).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    // What went wrong, in words. The same answer whether or not an email has an account, wherever
    // the service allows it, so the forms can't be used to find out.
    public static string ErrorText(AuthAnswer a) => a.Unreachable ? "Couldn't reach the sign-in service just now. Check your connection and try again."
        : a.Status == 429 ? "Too many tries. Wait a minute, then try again." : ErrorText(a.Code);
    public static string ErrorText(string? code) => code switch
    {
        "invalid_credentials" => "That email and password don't match an account.",
        "email_not_confirmed" => "Confirm your email first: open the link we sent you.",
        "user_already_exists" => "There's already an account for that email. Sign in instead.",
        "weak_password" => "That password is too easy to guess. Choose a longer one.",
        "captcha_failed" => "The check that you're not a bot didn't pass. Try again.",
        "same_password" => "That's already your password. Choose a different one.",
        "otp_expired" or "flow_state_not_found" or "flow_state_expired" => "That link has expired or has already been used. Ask for a new one.",
        // an emailed link, or a Google sign-in, finished in a browser other than the one that began it
        "pkce_code_verifier_not_found" => "That link was opened in a different browser from the one that asked for it. If you were confirming your email, it's confirmed: sign in here. If you were resetting your password, ask for a new link from this browser.",
        _ => "Something went wrong. Try again in a moment.",
    };

    // An address on this site to go back to after signing in: a path of ours, never somewhere else
    public static string SafePath(string? to) =>
        to is { Length: > 0 } && System.Text.RegularExpressions.Regex.IsMatch(to, @"^/(?!/)[\w\-./?=&%:|,+]*$", System.Text.RegularExpressions.RegexOptions.ECMAScript) ? to : "/";
}
