using System.Net;

namespace TheCornerFC.Web.Tests;

// The Prediction record (/record) drawn from a stand-in site_prediction_record: the month and
// competition from the address, the totals, each locked prediction beside its result, and pages
public class RecordPageTests
{
    const string Site = """{"generated_at":"2026-10-18T01:40:00+00:00","competitions":{"39":{"name":"Premier League","country":"England","type":"League"},"40":{"name":"Championship","country":"England","type":"League"}},"teams":{"42":"Arsenal","63":"Leeds"}}""";
    const string Record = """
        {"any":true,"since":"2026-09-26T14:00:00+00:00","total":250,"right":130,"log_loss":0.9812,
         "first":"2026-10-01T14:00:00+00:00","last":"2026-10-18T19:00:00+00:00",
         "comps":{"39":60,"40":190},
         "rows":[[7,"2026-10-18T14:00:00+00:00",39,42,63,0.62,0.213,0.167,"2-0",1.8,1.07,2,0,0,true,0.478,"2026-10-18T10:24:16+00:00","match-prediction 9afa9ed","abc123"],
                 [8,"2026-10-17T19:00:00+00:00",40,63,42,0.45,0.3,0.25,"1-1",1.4,1.1,0,1,2,false,1.386,"2026-10-15T19:00:00+00:00","match-prediction 9afa9ed","def456"]],
         "teams":{"42":"Arsenal","63":"Leeds"}}
        """;

    static (SiteFactory Site, List<string> Asked) Stand(string record)
    {
        var asked = new List<string>();
        var site = new SiteFactory("production", r =>
        {
            if (r.RequestUri!.AbsolutePath.EndsWith("/site_prediction_record"))
            {
                lock (asked) asked.Add(r.Content!.ReadAsStringAsync().Result);
                return StubHandler.Json(record);
            }
            return StubHandler.Json(r.RequestUri.Query.Contains("p_key=site") ? Site : "null");
        });
        return (site, asked);
    }

    static HttpClient Client(SiteFactory site) => site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com") });

    [Fact]
    public async Task The_record_lists_each_locked_prediction_beside_its_result()
    {
        var (site, asked) = Stand(Record);
        using var _ = site;
        var r = await Client(site).GetAsync("/record");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("public, max-age=300", r.Headers.CacheControl!.ToString());
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains("""{"p_limit":100,"p_offset":0}""", asked[0]);                       // every month and competition
        Assert.Contains("<option value=\"2026-10\">October 2026</option><option value=\"2026-09\">September 2026</option>", html);
        Assert.Contains("<option value=\"40\">Championship (190)</option><option value=\"39\">Premier League (60)</option>", html);
        Assert.Contains("<div class=\"stats-label\">Right results</div><div class=\"stats-value\">52.0%</div>", html);
        Assert.Contains("<div class=\"stats-value\">0.981</div>", html);
        Assert.Contains("<tr id=\"rec-7\">", html);
        Assert.Contains("href=\"/club/42\">Arsenal</a> <b>2–0</b> <a class=\"team-link\" href=\"/club/63\">Leeds</a>", html);
        Assert.Matches("<td class=\"gap-ok\"><b>62%</b></td>\\s*<td>21%</td>\\s*<td>17%</td>", html);    // the call, and it happened
        Assert.Contains("<td class=\"gap-off\"><b>45%</b></td>", html);                          // the call that didn't
        Assert.Contains("<td>Home ✓</td>", html);
        Assert.Contains("title=\"match-prediction 9afa9ed · fingerprint abc123\">3 h before</span>", html);
        Assert.Contains("2 days before", html);
        Assert.Contains("Page 1 of 3", html);
        Assert.Contains("href=\"/record?p=2\">Older</a>", html);
        Assert.DoesNotContain(">Newer</a>", html);
    }

    [Fact]
    public async Task The_month_competition_and_page_come_from_the_address()
    {
        var (site, asked) = Stand(Record);
        using var _ = site;
        var html = await Client(site).GetStringAsync("/record?m=2026-10&c=39&p=2");
        Assert.Contains("\"p_offset\":100", asked[0]);
        Assert.Contains("\"p_from\":\"2026-10-01\",\"p_to\":\"2026-10-31\"", asked[0]);
        Assert.Contains("\"p_leagues\":[39]", asked[0]);
        Assert.Contains("<option value=\"2026-10\" selected=\"selected\">", html);
        Assert.Contains("<option value=\"39\" selected=\"selected\">", html);
        Assert.Contains("href=\"/record?m=2026-10&amp;c=39\">Newer</a>", html);
        Assert.Contains("href=\"/record?m=2026-10&amp;c=39&amp;p=3\">Older</a>", html);
        // anything else in the address is the first page of everything
        var odd = await Client(site).GetStringAsync("/record?m=nope&c=x&p=-4");
        Assert.Contains("""{"p_limit":100,"p_offset":0}""", asked[^1]);
        Assert.Contains("<option value=\"all\" selected=\"selected\">All months</option>", odd);
    }

    [Fact]
    public async Task Before_the_migration_or_the_first_run_the_page_says_it_is_being_prepared()
    {
        var (site, _) = Stand("null");
        using var s = site;
        var html = await Client(site).GetStringAsync("/record");
        Assert.Contains("id=\"record-empty\"", html);
        var (none, _) = Stand("""{"any":false,"total":0,"right":0,"rows":[],"comps":{},"teams":{}}""");
        using var n = none;
        Assert.Contains("id=\"record-empty\"", await Client(none).GetStringAsync("/record"));
    }

    [Fact]
    public void The_stored_time_reads_in_minutes_hours_or_days_before_kick_off()
    {
        var k = DateTimeOffset.Parse("2026-10-18T14:00:00Z");
        Assert.Equal("45 min", TheCornerFC.Web.Site.PredictionRecord.Before(k.AddMinutes(-45), k));
        Assert.Equal("26 h", TheCornerFC.Web.Site.PredictionRecord.Before(k.AddHours(-26.5), k));
        Assert.Equal("3 days", TheCornerFC.Web.Site.PredictionRecord.Before(k.AddDays(-3.2), k));
    }
}
