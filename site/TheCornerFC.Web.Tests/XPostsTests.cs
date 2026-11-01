using System.Net;
using System.Text.Json;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// The X page: each post's words and card from the public figures, and the page behind the Admin gate
public class XPostsTests
{
    static readonly DateTimeOffset Now = new(2026, 10, 30, 12, 0, 0, TimeSpan.Zero);
    static readonly SiteDoc Site = JsonSerializer.Deserialize<SiteDoc>("""
        {"generated_at":"2026-10-30T02:00:00+00:00","competitions":{"39":{"name":"Premier League","country":"England","type":"League"}},
         "teams":{"1":"Bournemouth","2":"Leeds","3":"Liverpool","4":"Arsenal","5":"Chelsea","6":"Everton"}}
        """, Database.Json)!;

    static Match M(int id, string kickoff, int home, int away, double h, double d, string status = "NS", int league = 39, string round = "Regular Season - 9") =>
        new(id, kickoff, league, round, home, away, status, null, null, null, null, h, d, 1 - h - d, null, null, null, null, null, null, null, null, null, null,
            null, null, null, null, null, null, null, null, null, []);
    static Club C(int team, double form, double current = 1000, int league = 39, bool inLeague = true) =>
        new(team, league, current, 0, 0, 10, form, inLeague, null, null, null, null);

    static PredictionRecordDoc Record(int total, int right) => new(true, null, total, right, 0.985, null, null, null, null, null);

    [Fact]
    public void The_record_says_it_is_behind_the_bookmakers_when_it_is_and_not_otherwise()
    {
        var behind = XPosts.Record(Record(2066, 1093), 0.017)!;
        Assert.Equal("Every prediction is locked before kick-off and kept. 2,066 matches so far, 52.9% right. Still behind the bookmakers, and the site says so. thecornerfc.com/record", behind.Text);
        Assert.Equal("Still behind the bookmakers, by 0.017 in log loss. The site says so.", behind.Card.Note);
        var unknown = XPosts.Record(Record(2066, 1093), null)!;
        Assert.DoesNotContain("behind", unknown.Text);
        Assert.Null(unknown.Card.Note);
        Assert.Null(XPosts.Record(Record(0, 0), 0.017));
        Assert.Null(XPosts.Record(null, 0.017));
    }

    [Fact]
    public void The_round_names_the_favourite_and_a_close_match_in_uk_time_and_skips_what_is_not_to_come()
    {
        var post = XPosts.Round(Site, [
            M(1, "2026-10-31T15:00:00+00:00", 1, 2, 0.61, 0.21),
            M(2, "2026-11-01T16:30:00+00:00", 3, 4, 0.37, 0.27),
            M(3, "2026-10-29T15:00:00+00:00", 5, 6, 0.90, 0.05),            // kicked off
            M(4, "2026-10-31T12:30:00+00:00", 5, 6, 0.90, 0.05, "PST"),     // put off
            M(5, "2026-10-31T12:30:00+00:00", 5, 6, 0.90, 0.05, league: 40), // another league
        ], Now)!;
        Assert.Matches(@"^The model's chances for Premier League .+\. Bournemouth the clearest favourite at 61%; Liverpool v Arsenal too close to call\. thecornerfc\.com/matches$", post.Text);
        Assert.Equal(["Sat 15:00", "Sun 16:30"], post.Card.Matches!.Select(m => m.When));
        Assert.Equal(new XPosts.Chances("Sat 15:00", "Bournemouth", "Leeds", 61, 21, 18), post.Card.Matches![0]);
        Assert.Null(XPosts.Round(Site, [M(3, "2026-10-29T15:00:00+00:00", 5, 6, 0.9, 0.05)], Now));
    }

    [Fact]
    public void A_favourite_away_from_home_is_the_one_named()
    {
        var post = XPosts.Round(Site, [M(1, "2026-10-31T15:00:00+00:00", 2, 3, 0.10, 0.20)], Now)!;
        Assert.Contains("Liverpool the clearest favourite at 70%.", post.Text);
    }

    [Fact]
    public void The_movers_name_the_two_at_each_end_and_leave_out_other_leagues()
    {
        var post = XPosts.Movers(Site, [C(1, 76.4), C(5, 32), C(3, 1), C(4, -31), C(2, -55), C(6, 99, league: 40)])!;
        Assert.Equal("Club ratings move after every match. Over the last six: Bournemouth +76, Chelsea +32. Leeds −55, Arsenal −31. thecornerfc.com/clubs", post.Text);
        Assert.Equal("Bournemouth rising, Leeds falling", post.Card.Title);
        Assert.Equal(5, post.Card.Movers!.Count);
        Assert.Null(XPosts.Movers(Site, [C(1, 5), C(2, 4), C(3, 3), C(4, 2)]));   // nobody falling
    }

    [Fact]
    public void The_strongest_are_the_top_ten_of_every_club_counted_once()
    {
        var clubs = Enumerable.Range(1, 12).Select(i => C(i, 0, 1200 - i)).Append(C(1, 0, 1199, league: 2, inLeague: false)).ToList();
        var post = XPosts.Strongest(Site, clubs)!;
        Assert.Equal("The ten strongest clubs in the world right now, on one scale with 2 others. Bournemouth top, then Leeds and Liverpool. thecornerfc.com/clubs", post.Text);
        Assert.Equal(10, post.Card.Clubs!.Count);
        Assert.Equal("12 clubs, one scale", post.Card.Kicker);
        Assert.Null(XPosts.Strongest(Site, clubs.Take(5)));
    }

    [Fact]
    public void Every_post_fits_on_x_and_opens_with_its_words_filled_in()
    {
        var post = XPosts.Movers(Site, [C(1, 76), C(5, 32), C(4, -31), C(2, -55)])!;
        Assert.StartsWith("https://x.com/intent/post?text=Club%20ratings%20move", post.ShareUrl);
        Assert.Equal(post.Text, Uri.UnescapeDataString(post.ShareUrl[(post.ShareUrl.IndexOf('=') + 1)..]));
        Assert.All(new[] { post, XPosts.Record(Record(2066, 1093), 0.017)! }, p => Assert.InRange(p.Text.Length, 1, 280));
    }

    static string Cookie() =>
        $"{Sessions.Cookie}={Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(new Session("access-1", "refresh-1", DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), "user-1", "admin@example.com")))}";
    static HttpRequestMessage Get(string path, bool signedIn = true)
    {
        var m = new HttpRequestMessage(HttpMethod.Get, path);
        if (signedIn) m.Headers.Add("Cookie", Cookie());
        return m;
    }
    static string Fn(HttpRequestMessage r) => r.RequestUri!.AbsolutePath.Replace("/rest/v1/rpc/", "");
    static SiteFactory SiteWith(bool admin) => new("production", r => Fn(r) switch
    {
        "am_admin" => StubHandler.Json(admin ? "true" : "false"),
        "site_prediction_record" => StubHandler.Json("""{"any":true,"total":2066,"right":1093,"log_loss":0.985}"""),
        _ when r.RequestUri!.Query.Contains("p_key=site") => StubHandler.Json("""{"generated_at":"2026-10-30T02:00:00+00:00","competitions":{},"teams":{}}"""),
        _ => StubHandler.Json("null"),
    });

    [Fact]
    public async Task The_page_is_the_administrators_alone()
    {
        using var open = SiteWith(admin: true);
        var client = open.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com"), HandleCookies = false });
        Assert.Equal(HttpStatusCode.SeeOther, (await client.SendAsync(Get("/admin/posts", signedIn: false))).StatusCode);

        using var refused = SiteWith(admin: false);
        var other = refused.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com"), HandleCookies = false });
        Assert.Equal(HttpStatusCode.NotFound, (await other.SendAsync(Get("/admin/posts"))).StatusCode);

        var r = await client.SendAsync(Get("/admin/posts"));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.True(r.Headers.CacheControl is { Private: true, NoStore: true });
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains("2,066 matches so far, 52.9% right", html);
        Assert.Contains("Open in X", html);
        // what the posts are made of is asked for as a signed-out visitor would, never with the token
        Assert.All(open.Handler.Sent.Where(x => Fn(x) is "site_prediction_record" or "site_matches"), x => Assert.NotEqual("Bearer access-1", x.Headers.Authorization?.ToString()));
        Assert.DoesNotContain(open.Handler.Sent, x => Fn(x) == "admin_doc");
    }
}
