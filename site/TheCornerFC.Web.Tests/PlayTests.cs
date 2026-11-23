using System.IO.Compression;
using System.Net;
using System.Text;
using System.Text.Json;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// The two things free with an account (T-095, T-104): Beat the Model and the Fantasy points page,
// against a stand-in database. Both are asked of the database with the visitor's own token, and
// neither puts its data into a page the server writes.
public class PlayTests
{
    static string Cookie() =>
        $"{Sessions.Cookie}={Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(new Session("access-9", "refresh-9", DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), "user-9", "fan@example.com")))}";
    static HttpRequestMessage Ask(HttpMethod method, string path, bool signedIn = true, string? json = null, bool gzip = false)
    {
        var m = new HttpRequestMessage(method, path);
        if (signedIn) m.Headers.Add("Cookie", Cookie());
        if (gzip) m.Headers.Add("Accept-Encoding", "gzip");
        if (json is not null) m.Content = new StringContent(json, Encoding.UTF8, "application/json");
        if (method == HttpMethod.Post) m.Headers.Add("Origin", "https://thecornerfc.com");
        return m;
    }
    static HttpClient Client(SiteFactory site) =>
        site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com"), HandleCookies = false });
    static string Fn(HttpRequestMessage r) => r.RequestUri!.AbsolutePath.Replace("/rest/v1/rpc/", "");

    const string Round = """{"ok":true,"season":2026,"round":13,"name":null,"matches":[{"id":5,"kickoff":"2026-11-28T15:00:00Z","home":40,"away":50,"status":"NS","hg":null,"ag":null,"pick":null,"points":null,"model":null,"model_points":null}]}""";
    static string stamp = "2026-11-23T01:00:00+00:00";
    static string Doc(string at) => $$$"""{"ok":true,"updated_at":"{{{at}}}","doc":{"model":"fantasy v1.6","players":[[1,"Secret Player"]]}}""";
    static SiteFactory Make(Func<string>? at = null) => new("production", r => Fn(r) switch
    {
        "fantasy_points_stamp" => StubHandler.Json($$"""{"ok":true,"updated_at":"{{(at ?? (() => stamp))()}}"}"""),
        "fantasy_points_doc" => StubHandler.Json(Doc((at ?? (() => stamp))())),
        "btm_round" => StubHandler.Json(Round),
        "btm_table" => StubHandler.Json("""{"ok":true,"season":2026,"round":null,"players":0,"top":[],"me":null,"model":[0,0,0,0]}"""),
        "btm_pick" => StubHandler.Json("""{"ok":true,"pick":[2,1],"model":"1-1"}"""),
        "btm_set_name" => StubHandler.Json("""{"ok":true,"name":"Fan"}"""),
        "site_doc" when r.RequestUri!.Query.Contains("p_key=site&") => StubHandler.Json("""{"generated_at":"","competitions":{},"teams":{"40":"Liverpool","50":"Manchester City"}}"""),
        _ => StubHandler.Json("null"),
    });

    [Fact]
    public async Task The_pages_are_shells_that_show_the_way_in_when_signed_out()
    {
        using var site = Make();
        foreach (var (path, island) in new[] { ("/fantasy-points", "fantasy-points"), ("/beat-the-model", "btm") })
        {
            var html = await (await Client(site).SendAsync(Ask(HttpMethod.Get, path, signedIn: false))).Content.ReadAsStringAsync();
            Assert.Contains($"data-island=\"{island}\"", html);
            Assert.Contains("href=\"/account?view=signin\"", html);
            Assert.Contains("Free with an account", html);
            var signedIn = await Client(site).SendAsync(Ask(HttpMethod.Get, path));
            Assert.True(signedIn.Headers.CacheControl is { Private: true, NoStore: true });
            Assert.Contains("Loading…", await signedIn.Content.ReadAsStringAsync());
        }
        Assert.DoesNotContain(site.Handler.Sent, x => Fn(x).StartsWith("btm_") || Fn(x).StartsWith("fantasy_points"));
    }

    [Fact]
    public async Task Both_are_in_the_menu_for_everyone()
    {
        using var site = Make();
        var html = await (await Client(site).SendAsync(Ask(HttpMethod.Get, "/clubs", signedIn: false))).Content.ReadAsStringAsync();
        Assert.Contains("href=\"/beat-the-model\"", html);
        Assert.Contains("href=\"/fantasy-points\"", html);
    }

    [Fact]
    public async Task The_points_are_checked_per_visitor_and_the_document_kept_until_it_changes()
    {
        var at = stamp;
        using var site = Make(() => at);
        var first = await Client(site).SendAsync(Ask(HttpMethod.Get, "/fantasy/points"));
        Assert.True(first.Headers.CacheControl is { Private: true, NoStore: true });
        Assert.Contains("Secret Player", await first.Content.ReadAsStringAsync());
        // gzipped once on the server for a browser (or Cloudflare) that takes it
        var packed = await Client(site).SendAsync(Ask(HttpMethod.Get, "/fantasy/points", gzip: true));
        Assert.Equal("gzip", packed.Content.Headers.ContentEncoding.Single());
        using (var gz = new GZipStream(await packed.Content.ReadAsStreamAsync(), CompressionMode.Decompress))
        using (var read = new StreamReader(gz)) Assert.Equal(Doc(at), await read.ReadToEndAsync());
        // every ask checks the visitor; the document is asked for once while the stamp stands
        Assert.Equal(2, site.Handler.Sent.Count(x => Fn(x) == "fantasy_points_stamp"));
        Assert.Single(site.Handler.Sent, x => Fn(x) == "fantasy_points_doc");
        Assert.All(site.Handler.Sent.Where(x => Fn(x).StartsWith("fantasy_points")), x => Assert.Equal("Bearer access-9", x.Headers.Authorization!.ToString()));
        // the nightly export changes it: asked for again
        at = "2026-11-24T01:00:00+00:00";
        Assert.Contains(at, await (await Client(site).SendAsync(Ask(HttpMethod.Get, "/fantasy/points"))).Content.ReadAsStringAsync());
        Assert.Equal(2, site.Handler.Sent.Count(x => Fn(x) == "fantasy_points_doc"));
        // signed out: refused, and the database isn't asked
        var outside = await Client(site).SendAsync(Ask(HttpMethod.Get, "/fantasy/points", signedIn: false));
        Assert.Equal(HttpStatusCode.Unauthorized, outside.StatusCode);
        Assert.DoesNotContain("Secret", await outside.Content.ReadAsStringAsync());
        Assert.Equal(3, site.Handler.Sent.Count(x => Fn(x) == "fantasy_points_stamp"));
    }

    [Fact]
    public async Task A_round_comes_with_its_clubs_names_and_is_asked_as_the_visitor()
    {
        using var site = Make();
        var r = await Client(site).SendAsync(Ask(HttpMethod.Get, "/btm/round?r=13"));
        Assert.True(r.Headers.CacheControl is { Private: true, NoStore: true });
        var body = JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement;
        Assert.Equal("Liverpool", body.GetProperty("teams").GetProperty("40").GetString());
        Assert.Equal("Manchester City", body.GetProperty("teams").GetProperty("50").GetString());
        var asked = site.Handler.Sent.Single(x => Fn(x) == "btm_round");
        Assert.Equal("Bearer access-9", asked.Headers.Authorization!.ToString());
        Assert.Contains("\"p_round\":13", site.Handler.Bodies[asked]);
        // a round that can't be one is left to the database to choose
        await Client(site).SendAsync(Ask(HttpMethod.Get, "/btm/round?r=99"));
        Assert.DoesNotContain("\"p_round\":99", site.Handler.Bodies[site.Handler.Sent.Last(x => Fn(x) == "btm_round")]);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Client(site).SendAsync(Ask(HttpMethod.Get, "/btm/round", signedIn: false))).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Client(site).SendAsync(Ask(HttpMethod.Get, "/btm/table", signedIn: false))).StatusCode);
    }

    [Fact]
    public async Task A_pick_and_a_name_are_saved_as_the_visitor_and_bad_ones_refused()
    {
        using var site = Make();
        Assert.Equal(HttpStatusCode.Unauthorized, (await Client(site).SendAsync(Ask(HttpMethod.Post, "/btm/pick", signedIn: false, json: """{"fixture":5,"home":2,"away":1}"""))).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Client(site).SendAsync(Ask(HttpMethod.Post, "/btm/pick", json: """{"fixture":5,"home":"2","away":1}"""))).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Client(site).SendAsync(Ask(HttpMethod.Post, "/btm/pick", json: """{"fixture":5,"home":1.5,"away":1}"""))).StatusCode);
        var pick = await Client(site).SendAsync(Ask(HttpMethod.Post, "/btm/pick", json: """{"fixture":5,"home":2,"away":1}"""));
        Assert.Contains("\"model\":\"1-1\"", await pick.Content.ReadAsStringAsync());
        var picked = site.Handler.Sent.Single(x => Fn(x) == "btm_pick");
        Assert.Contains("\"p_fixture\":5,\"p_home\":2,\"p_away\":1", site.Handler.Bodies[picked]);
        Assert.Equal("Bearer access-9", picked.Headers.Authorization!.ToString());

        Assert.Equal(HttpStatusCode.BadRequest, (await Client(site).SendAsync(Ask(HttpMethod.Post, "/btm/name", json: """{"name":7}"""))).StatusCode);
        await Client(site).SendAsync(Ask(HttpMethod.Post, "/btm/name", json: """{"name":"Fan"}"""));
        Assert.Contains("\"p_name\":\"Fan\"", site.Handler.Bodies[site.Handler.Sent.Single(x => Fn(x) == "btm_set_name")]);
        // a post from anywhere but the site's own pages goes no further
        var elsewhere = new HttpRequestMessage(HttpMethod.Post, "/btm/pick") { Content = new StringContent("""{"fixture":5,"home":2,"away":1}""", Encoding.UTF8, "application/json") };
        elsewhere.Headers.Add("Cookie", Cookie());
        elsewhere.Headers.Add("Origin", "https://evil.example");
        await Client(site).SendAsync(elsewhere);
        Assert.Single(site.Handler.Sent, x => Fn(x) == "btm_pick");
    }
}
