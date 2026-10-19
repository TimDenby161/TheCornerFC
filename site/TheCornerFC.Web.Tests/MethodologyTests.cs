using System.Net;
using TheCornerFC.Web.Pages;

namespace TheCornerFC.Web.Tests;

// How the models work, with its boxes of live figures filled from the `methodology` document
public class MethodologyTests
{
    const string Doc = """
        {"generated_at":"2026-10-18T01:40:00+00:00",
         "freshness":{"predictions":"2026-10-18T01:30:00+00:00","model":{"name":"match-prediction","code":"9afa9ed","registered":"2026-10-14T09:00:00+00:00"}},
         "matches":{"n":1234,"period":{"from":"2026-10-03T12:00:00+00:00","to":"2026-10-17T19:00:00+00:00"},"versions":[{"name":"match-prediction","n":1234}],
                    "accuracy":0.5234,"log_loss":0.98141,"brier":0.5812,"exact_score":{"n":1234,"accuracy":0.111},
                    "calibration":[["0.4-0.5",210,0.452,0.471]],"excluded_no_regulation_score":12},
         "lineups":null}
        """;

    static async Task<string> Page(string? doc)
    {
        using var site = new SiteFactory("production", r => StubHandler.Json(r.RequestUri!.Query.Contains("p_key=methodology") && doc is not null ? doc : "null"));
        var r = await site.CreateClient(new() { BaseAddress = new Uri("https://thecornerfc.com") }).GetAsync("/methodology");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        return await r.Content.ReadAsStringAsync();
    }

    [Fact]
    public async Task Fills_each_box_with_the_live_figures_in_the_visitors_time()
    {
        var html = await Page(Doc);
        Assert.Contains("<li><strong>Site data exported: </strong>18 Oct 2026, 02:40</li>", html);
        Assert.Contains("1,234 finished matches, each predicted before kick-off. Kick-offs from 3 Oct 2026 to 17 Oct 2026.", html);
        Assert.Contains("Still a small sample (1,234 matches).", html);
        Assert.Contains("<span class=\"stat-v\">52.3%</span>", html);
        Assert.Contains("<span class=\"stat-v\">0.981</span>", html);
        Assert.Contains("<tr><td>40–50%</td><td>45%</td><td>47%</td><td>210</td></tr>", html);
        Assert.Contains("All predictions are from model version match-prediction (1,234).", html);
        Assert.Contains("12 matches without a 90-minute score on record are left out.", html);
        Assert.Contains("No live predicted line-ups have been scored yet.", html);
        Assert.Contains("The match model in use is <strong>match-prediction</strong> (code 9afa9ed), registered 14 Oct 2026.", html);
        Assert.DoesNotContain("Loading…", html);
    }

    [Fact]
    public async Task Says_so_when_the_figures_cant_be_loaded_and_keeps_the_words()
    {
        var html = await Page(null);
        Assert.Contains("<p class=\"warn\">Couldn't load the live figures. Try reloading the page.</p>", html);
        Assert.Contains("How fresh is the data?", html);
    }

    [Theory]
    [InlineData(400, "Very early: 400 matches is far too few to judge the model.")]
    [InlineData(1999, "Still a small sample (1,999 matches).")]
    [InlineData(2000, "")]
    public void Says_how_much_weight_a_sample_can_bear(int n, string starts) =>
        Assert.StartsWith(starts, MethodologyModel.SampleNote(n, "matches"));
}
