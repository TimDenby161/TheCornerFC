using System.Net;
using Microsoft.Extensions.DependencyInjection;
using SkiaSharp;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// The pictures a shared link shows (T-094), against a stand-in database. Each test uses its own
// match id: drawn cards are kept in memory for the whole run.
public class ShareCardTests
{
    const string Site = """
        {"generated_at":"2026-10-20T01:40:00+00:00","competitions":{"39":{"name":"Premier League","country":"England","type":"League"}},
         "teams":{"42":"Arsenal","49":"Chelsea"},
         "match_fields":["id","kickoff","league","round","home","away","status","hg","ag","p_home","p_draw","p_away","home_xg","away_xg","likely"]}
        """;
    static string Upcoming(int id) => $$"""{"matches":[[{{id}},"2030-10-26T16:30:00+00:00",39,"Regular Season - 9",42,49,"NS",null,null,0.5,0.27,0.23,1.7,1.1,"2-1"]],"paywall":false}""";
    static string Locked(int id) => $$"""{"matches":[[{{id}},"2030-10-26T16:30:00+00:00",39,"Regular Season - 9",42,49,"NS",null,null,null,null,null,null,null,null]],"paywall":true}""";

    static SiteFactory Factory(string matches) => new("production", r =>
    {
        var p = r.RequestUri!.AbsolutePath;
        if (p.EndsWith("site_matches")) return StubHandler.Json(matches);
        if (p.EndsWith("site_match_days")) return StubHandler.Json("""{"days":[["2030-10-26",39]],"leagues":[39],"intl":[]}""");
        if (r.RequestUri.Query.Contains("p_key=site&")) return StubHandler.Json(Site);
        if (r.RequestUri.Query.Contains("p_key=rankings")) return StubHandler.Json("""{"fields":["team"],"rankings":[]}""");
        return StubHandler.Json("null");
    });

    static async Task<HttpResponseMessage> Get(SiteFactory f, string path) =>
        await f.CreateClient(new() { BaseAddress = new Uri("https://thecornerfc.com") }).GetAsync(path);

    [Fact]
    public async Task A_match_card_is_a_1200_by_630_png_kept_for_an_hour_before_kick_off()
    {
        using var f = Factory(Upcoming(2001));
        var r = await Get(f, "/share/match/2001.png");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("image/png", r.Content.Headers.ContentType?.MediaType);
        Assert.Equal("public, max-age=3600", r.Headers.CacheControl?.ToString());
        Assert.False(r.Headers.Contains("Set-Cookie"));
        using var image = SKBitmap.Decode(await r.Content.ReadAsByteArrayAsync());
        Assert.Equal((1200, 630), (image.Width, image.Height));
    }

    [Fact]
    public async Task An_address_with_no_match_or_club_behind_it_draws_nothing()
    {
        using var f = Factory("""{"matches":[]}""");
        Assert.Equal(HttpStatusCode.NotFound, (await Get(f, "/share/match/2002.png")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Get(f, "/share/match/abc.png")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Get(f, "/share/club/777777.png")).StatusCode);
    }

    [Fact]
    public async Task A_card_holds_the_chances_only_where_a_visitor_who_isnt_signed_in_sees_them()
    {
        var now = DateTimeOffset.Parse("2030-10-01T00:00:00Z");
        using (var f = Factory(Upcoming(2003)))
        {
            var open = await ShareCards.MatchFor(f.Services.GetRequiredService<Database>(), "2003", now);
            Assert.Equal([50, 27, 23], open!.Value.Card.Probs);
            Assert.Equal("Premier League · Sat 26 Oct", open.Value.Card.Line);
        }
        using (var f = Factory(Locked(2004)))
        {
            var held = await ShareCards.MatchFor(f.Services.GetRequiredService<Database>(), "2004", now);
            Assert.Null(held!.Value.Card.Probs);
        }
    }

    [Fact]
    public async Task A_match_page_points_its_share_picture_at_its_own_card()
    {
        using var f = Factory(Upcoming(2005));
        var body = await (await Get(f, "/match/2005")).Content.ReadAsStringAsync();
        Assert.Contains("<meta property=\"og:image\" content=\"https://thecornerfc.com/share/match/2005.png\" />", body);
    }

    [Fact]
    public void Long_names_and_a_played_match_still_draw()
    {
        var bytes = ShareCards.Draw(new ShareCards.MatchCard("Wolverhampton Wanderers", "Brighton & Hove Albion", "Premier League · Sat 26 Oct", 3, 2, [40, 30, 30], true));
        using var image = SKBitmap.Decode(bytes);
        Assert.Equal(1200, image.Width);
        Assert.NotNull(SKBitmap.Decode(ShareCards.Draw(new ShareCards.ClubCard("Barcelona", "La Liga", 1, 900, 1135, -22))));
    }
}
