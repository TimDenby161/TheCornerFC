using System.Net;
using System.Text.Json;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// The Admin area on the C# site: the gate before any of it runs, the Model Change Tracker drawn from
// the administrator's documents, and the switch (against a stand-in database: nothing sent anywhere)
public class AdminTests
{
    static string Cookie() =>
        $"{Sessions.Cookie}={Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(new Session("access-1", "refresh-1", DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), "user-1", "admin@example.com")))}";
    static HttpRequestMessage Get(string path, bool signedIn = true)
    {
        var m = new HttpRequestMessage(HttpMethod.Get, path);
        if (signedIn) m.Headers.Add("Cookie", Cookie());
        return m;
    }
    static HttpClient Client(SiteFactory site) =>
        site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com"), HandleCookies = false });
    static string Fn(HttpRequestMessage r) => r.RequestUri!.AbsolutePath.Replace("/rest/v1/rpc/", "");

    const string Changes = """
        {"generated_at":"2026-10-19T02:00:00+00:00","environment":"production","stored":true,"differs":[],
         "current":{"version":"match-prediction 9afa9ed","n":3359,"log_loss":0.9781,"brier":0.5803,"accuracy":0.512},"series":[],
         "changes":[
           {"id":"MC-0031","title":"Shots in the attack rating","model":"match","status":"Testing","stage":"Being tested","deployed":false,
            "expected":{"improves":"log loss","metrics":[{"metric":"log_loss","delta":-0.0007,"source":"DESIGN.md"}]},
            "results":[{"type":"result","date":"2026-10-12","evaluation":"backtest","unseen":"partly","label":"Final period","metric":"log_loss","delta":-0.0011,"n":20000,
              "baseline":0.99,"after":0.9889,"interval":[-0.002,-0.0002],"interval_level":0.95,"meaningful":"Small","source":"experiments/x/REPORT.md"}],
            "date":"2026-10-12","recorded":"2026-10-13","retrospective":true,"component":"Match probabilities","kind":"experiment",
            "what":"Adds shots","why":"Shots carry signal","how":"A new input","hypothesis":"Shots help","success_criteria":"Lower log loss",
            "code":{"commit":null,"experiment":"experiments/shots","model_version":null},
            "events":[{"type":"status","date":"2026-10-12","status":"Testing"},{"type":"live_test","date":"2026-10-14","protocol":"P17","start":"2026-10-14","target":6200}],
            "live":[{"protocol":"P17","start":"2026-10-14","target":6200,"matches":310}]}]}
        """;
    const string Live = """
        {"protocol":"P17","generated_at":"2026-10-18T04:00:00+00:00","start":"2026-10-14","minimum":{"matches":500,"weeks":8},"n":310,"weeks":1,"to":"2026-10-18",
         "changes":{"MC-0031":{"n":310,"weeks":1,"gain":0.0012,"low":-0.01,"high":0.012,"verdict":null,
           "series":[{"week":202642,"n":120,"gain":0.002,"low":-0.02,"high":0.024},{"week":202643,"n":310,"gain":0.0012,"low":-0.01,"high":0.012}]}},"not_run":{}}
        """;

    // a stand-in whose am_admin says `admin`, with the two documents and the model switch
    static SiteFactory Site(bool admin) => new("production", r => Fn(r) switch
    {
        "am_admin" => StubHandler.Json(admin ? "true" : "false"),
        "admin_doc" => StubHandler.Json(r.Content!.ReadAsStringAsync().Result.Contains("model_changes") ? $$"""{"ok":true,"doc":{{Changes}}}""" : $$"""{"ok":true,"doc":{{Live}}}"""),
        "admin_match_model" => StubHandler.Json("""{"ok":true,"live":"base","switches":[{"at":"2026-10-14T09:00:00+00:00","live":"base"}]}"""),
        "admin_set_match_model" => StubHandler.Json("""{"ok":true,"live":"a18","switches":[]}"""),
        _ => StubHandler.Json("null"),
    });

    [Fact]
    public async Task A_visitor_who_isnt_signed_in_is_sent_to_sign_in_from_every_admin_address()
    {
        using var site = Site(admin: true);
        foreach (var path in new[] { "/admin", "/admin/changes", "/admin/changes/MC-0031", "/admin/simulation", "/admin/anything/else" })
        {
            var r = await Client(site).SendAsync(Get(path, signedIn: false));
            Assert.Equal(HttpStatusCode.SeeOther, r.StatusCode);
            Assert.Equal("/account", r.Headers.Location!.ToString());
            Assert.True(r.Headers.CacheControl is { Private: true, NoStore: true }, path);
        }
        Assert.DoesNotContain(site.Handler.Sent, x => Fn(x) is "am_admin" or "admin_doc");
    }

    [Fact]
    public async Task A_signed_in_visitor_who_isnt_an_administrator_is_told_there_is_no_such_page()
    {
        using var site = Site(admin: false);
        var r = await Client(site).SendAsync(Get("/admin/changes"));
        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
        Assert.Contains("Page not found", await r.Content.ReadAsStringAsync());
        Assert.Equal("Bearer access-1", site.Handler.Sent.First(x => Fn(x) == "am_admin").Headers.Authorization!.ToString());
        // the documents are never asked for
        Assert.DoesNotContain(site.Handler.Sent, x => Fn(x) == "admin_doc");
        // and the menu has no Admin links for them
        var home = await (await Client(site).SendAsync(Get("/privacy"))).Content.ReadAsStringAsync();
        Assert.DoesNotContain("/admin/changes", home);
    }

    [Fact]
    public async Task An_administrator_sees_the_tracker_drawn_from_their_documents_asked_with_their_token()
    {
        using var site = Site(admin: true);
        Assert.Equal("/admin/changes", (await Client(site).SendAsync(Get("/admin"))).Headers.Location!.ToString());
        var r = await Client(site).SendAsync(Get("/admin/changes"));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.True(r.Headers.CacheControl is { Private: true, NoStore: true });
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains("Live now: <strong>The base model (club rank with movers, new clubs and shots)</strong>", html);
        Assert.Contains("Make live: The base model with A18’s boosted trees", html);
        Assert.Contains("<a class=\"team-link\" href=\"/admin/changes/MC-0031\">Shots in the attack rating</a>", html);
        Assert.Contains("Ready on the historical test; being confirmed on new matches", html);
        Assert.Contains("0.99000 → 0.98890", html);
        Assert.Contains("Expected &#x2B;0.00070", html);
        Assert.Contains("Too early: needs 500 matches and 8 weeks", html);
        // the menu's Admin links, for them
        Assert.Contains("href=\"/admin/simulation\"", html);
        Assert.All(site.Handler.Sent.Where(x => Fn(x).StartsWith("admin_") || Fn(x) == "am_admin"), x => Assert.Equal("Bearer access-1", x.Headers.Authorization!.ToString()));
    }

    [Fact]
    public async Task One_changes_page_sets_out_its_registration_results_live_record_and_events()
    {
        using var site = Site(admin: true);
        var html = await (await Client(site).SendAsync(Get("/admin/changes/MC-0031"))).Content.ReadAsStringAsync();
        Assert.Contains("<h2 class=\"mc-title\" id=\"mc-title\">Shots in the attack rating</h2>", html);
        Assert.Contains("Ready to implement", html);
        Assert.Contains("<td>−0.00200 to −0.00020 (95%)</td>", html);
        Assert.Contains("Live test registered: protocol P17, on matches from 2026-10-14, read once at 6,200", html);
        Assert.Contains("<figure class=\"mc-chart\">", html);
        Assert.Contains("2026-W42", html);
        Assert.Contains("<td>P17</td><td>2026-10-14</td><td>310</td><td>6,200</td><td>5%</td>", html);
        Assert.Equal(HttpStatusCode.NotFound, (await Client(site).SendAsync(Get("/admin/changes/MC-9999"))).StatusCode);
    }

    [Fact]
    public async Task The_switch_asks_the_database_as_the_administrator_and_refuses_anything_but_the_two_models()
    {
        using var site = Site(admin: true);
        HttpRequestMessage Post(string live)
        {
            var m = new HttpRequestMessage(HttpMethod.Post, "/admin/changes?/switch") { Content = new FormUrlEncodedContent(new Dictionary<string, string> { ["live"] = live }) };
            m.Headers.Add("Cookie", Cookie());
            m.Headers.Add("Origin", "https://thecornerfc.com");
            return m;
        }
        var r = await Client(site).SendAsync(Post("a18"));
        Assert.Equal("/admin/changes", r.Headers.Location!.ToString());
        var asked = site.Handler.Sent.Single(x => Fn(x) == "admin_set_match_model");
        Assert.Contains("\"p_live\":\"a18\"", site.Handler.Bodies[asked]);
        Assert.Equal("Bearer access-1", asked.Headers.Authorization!.ToString());
        var bad = await Client(site).SendAsync(Post("something-else"));
        Assert.Equal(HttpStatusCode.BadRequest, bad.StatusCode);
        Assert.Contains("That is not one of the two models.", await bad.Content.ReadAsStringAsync());
        Assert.Single(site.Handler.Sent, x => Fn(x) == "admin_set_match_model");
    }
}
