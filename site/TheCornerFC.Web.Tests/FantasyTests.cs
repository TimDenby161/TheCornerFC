using System.Net;
using System.Text;
using System.Text.Json;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// The three fantasy pages and what their React parts ask for (against a stand-in database: nothing
// sent anywhere). FPL's and Fantasy EFL's data is never in a page the server writes: the owner's
// browser asks for it, asked of the database with the visitor's own token.
public class FantasyTests
{
    static string Cookie() =>
        $"{Sessions.Cookie}={Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(new Session("access-1", "refresh-1", DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), "user-1", "owner@example.com")))}";
    static HttpRequestMessage Ask(HttpMethod method, string path, bool signedIn = true, string? json = null)
    {
        var m = new HttpRequestMessage(method, path);
        if (signedIn) m.Headers.Add("Cookie", Cookie());
        if (json is not null) m.Content = new StringContent(json, Encoding.UTF8, "application/json");
        return m;
    }
    static HttpClient Client(SiteFactory site) =>
        site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com"), HandleCookies = false });
    static string Fn(HttpRequestMessage r) => r.RequestUri!.AbsolutePath.Replace("/rest/v1/rpc/", "");

    const string Owner = """{"ok":true,"docs":{"fpl_predictions":{"model":"fantasy v1.6","players":[[1,"Secret Player"]]}},"locks":[],"marks":[]}""";
    const string Findings = """{"criteria":[],"note":"the model's own test results"}""";
    static SiteFactory Make() => new("production", r => Fn(r) switch
    {
        "fpl_owner_data" => StubHandler.Json(Owner),
        "mark_fpl_player" => StubHandler.Json("""{"ok":true}"""),
        "lock_fpl_transfers" => StubHandler.Json("""{"ok":true,"locked_at":"2026-10-20T10:00:00+00:00"}"""),
        "unlock_fpl_transfers" => StubHandler.Json("""{"ok":true}"""),
        "site_players" => StubHandler.Json("""{"total":1,"rows":[[7,"Seven"]]}"""),
        "site_doc" when r.RequestUri!.Query.Contains("p_key=site&") => StubHandler.Json("""{"generated_at":"","competitions":{},"teams":{},"player_fields":["id","name"]}"""),
        "site_doc" when r.RequestUri!.Query.Contains("p_key=fpl&") => StubHandler.Json(Findings),
        _ => StubHandler.Json("null"),
    });

    [Fact]
    public async Task The_pages_carry_no_fantasy_data_and_show_anyone_signed_out_the_way_in()
    {
        using var site = Make();
        foreach (var path in new[] { "/fpl", "/my-fpl-team", "/efl-fantasy" })
        {
            var html = await (await Client(site).SendAsync(Ask(HttpMethod.Get, path, signedIn: false))).Content.ReadAsStringAsync();
            Assert.Contains("Shown to the site owner only", html);
            Assert.Contains("class=\"mt-btn owner-signin\" href=\"/account?view=signin\"", html);
            Assert.Contains("<meta name=\"robots\" content=\"noindex\"", html);
        }
        var signedIn = await Client(site).SendAsync(Ask(HttpMethod.Get, "/fpl"));
        Assert.True(signedIn.Headers.CacheControl is { Private: true, NoStore: true });
        var page = await signedIn.Content.ReadAsStringAsync();
        Assert.Contains("Loading…", page);
        // the findings (the model's own test results) for a signed-in visitor; the predictions never
        Assert.Contains("own test results", page);
        Assert.DoesNotContain("Secret Player", page);
        Assert.DoesNotContain(site.Handler.Sent, x => Fn(x) == "fpl_owner_data");
    }

    [Fact]
    public async Task The_owners_data_is_asked_for_with_their_token_and_handed_on_unread()
    {
        using var site = Make();
        var r = await Client(site).SendAsync(Ask(HttpMethod.Get, "/fantasy/data"));
        Assert.Equal(Owner, await r.Content.ReadAsStringAsync());
        Assert.True(r.Headers.CacheControl is { Private: true, NoStore: true });
        var asked = site.Handler.Sent.Single(x => Fn(x) == "fpl_owner_data");
        Assert.Equal("Bearer access-1", asked.Headers.Authorization!.ToString());
        Assert.Contains("\"p_entry\":3996593", site.Handler.Bodies[asked]);
        // signed out: no, and the database isn't asked
        Assert.Equal("""{"ok":false}""", await (await Client(site).SendAsync(Ask(HttpMethod.Get, "/fantasy/data", signedIn: false))).Content.ReadAsStringAsync());
        Assert.Single(site.Handler.Sent, x => Fn(x) == "fpl_owner_data");
    }

    [Fact]
    public async Task A_tick_and_a_lock_are_saved_as_the_owner_and_bad_ones_refused()
    {
        using var site = Make();
        Assert.Equal(HttpStatusCode.Unauthorized, (await Client(site).SendAsync(Ask(HttpMethod.Post, "/fantasy/mark", signedIn: false, json: """{"player":7}"""))).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await Client(site).SendAsync(Ask(HttpMethod.Post, "/fantasy/mark", json: """{"player":"x"}"""))).StatusCode);
        var mark = await Client(site).SendAsync(Ask(HttpMethod.Post, "/fantasy/mark", json: """{"player":7,"mine":true,"target":false}"""));
        Assert.Equal("""{"ok":true}""", await mark.Content.ReadAsStringAsync());
        var marked = site.Handler.Sent.Single(x => Fn(x) == "mark_fpl_player");
        Assert.Contains("\"p_player\":7,\"p_mine\":true,\"p_target\":false", site.Handler.Bodies[marked]);
        Assert.Equal("Bearer access-1", marked.Headers.Authorization!.ToString());

        Assert.Equal(HttpStatusCode.BadRequest, (await Client(site).SendAsync(Ask(HttpMethod.Post, "/fantasy/lock", json: """{"event":8}"""))).StatusCode);
        var locked = await Client(site).SendAsync(Ask(HttpMethod.Post, "/fantasy/lock", json: """{"undo":false,"season":2026,"event":8,"transfers":[{"out":1,"in":2}]}"""));
        Assert.Contains("\"locked_at\"", await locked.Content.ReadAsStringAsync());
        Assert.Contains("\"p_transfers\":[{\"out\":1,\"in\":2}]", site.Handler.Bodies[site.Handler.Sent.Single(x => Fn(x) == "lock_fpl_transfers")]);
        await Client(site).SendAsync(Ask(HttpMethod.Post, "/fantasy/lock", json: """{"undo":true,"season":2026,"event":8}"""));
        Assert.DoesNotContain("p_transfers", site.Handler.Bodies[site.Handler.Sent.Single(x => Fn(x) == "unlock_fpl_transfers")]);
    }

    [Fact]
    public async Task Known_players_are_the_ones_the_Players_list_has()
    {
        using var site = Make();
        var r = await Client(site).SendAsync(Ask(HttpMethod.Post, "/fantasy/known", json: """{"ids":[7,8,"x",9.5]}"""));
        Assert.Equal("""{"ids":[7]}""", await r.Content.ReadAsStringAsync());
        Assert.Contains("\"p_ids\":[7,8],\"p_limit\":2", site.Handler.Bodies[site.Handler.Sent.Single(x => Fn(x) == "site_players")]);
    }
}
