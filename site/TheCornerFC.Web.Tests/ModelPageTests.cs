using System.Net;

namespace TheCornerFC.Web.Tests;

// The Model page (/model) drawn from a stand-in "model" document: its tiles, the changes in the model
// and the ones tried, and one match worked through with each row's explanation written out
public class ModelPageTests
{
    const string Site = """{"generated_at":"2026-10-18T01:40:00+00:00","competitions":{"39":{"name":"Premier League","country":"England","type":"League"}},"teams":{"42":"Arsenal","63":"Leeds"}}""";
    const string Doc = """
        {"generated_at":"2026-10-18T01:40:00+00:00",
         "current":{"version":"match-prediction 9afa9ed","n":3359,"period":{"from":"2025-10-18","to":"2026-10-17"},"log_loss":0.9781,"brier":0.5803,"accuracy":0.512,
           "vs_market":{"n":1200,"model_log_loss":0.99,"market_log_loss":0.97}},
         "series":[],
         "changes":[
           {"id":"MC-0028","title":"Club ranks from line-ups","model":"match","status":"Accepted","stage":"Deployed to production","deployed":true,"deployed_on":"2026-10-14",
            "expected":{"metrics":[]},"results":[{"type":"result","evaluation":"backtest","metric":"log_loss","delta":-0.0021,"n":44383,"baseline":0.99,"after":0.9879,"interval":[-0.003,-0.0012]}]},
           {"id":"MC-0031","title":"Shots in the attack rating","model":"match","status":"Rejected","stage":"Tested and rejected","deployed":false,
            "expected":{"metrics":[]},"results":[{"type":"result","evaluation":"backtest","metric":"log_loss","delta":-0.0011,"n":20000,"baseline":0.99,"after":0.9889,"interval":[-0.002,-0.0002]}]}],
         "tracking":null,
         "example":{"match":{"id":7,"kickoff":"2026-10-04T14:00:00+00:00","league":39,"round":"Regular Season - 7","home":42,"away":63,"status":"FT","hg":2,"ag":0,
             "p_home":0.62,"p_draw":0.213,"home_xg":1.8,"away_xg":1.07},
           "home_name":"Arsenal","away_name":"Leeds","competition":"Premier League",
           "why":{"current":[1094,1025],"baseline":[1096,1017],"match":[1095,1021],"margin":{"strength":0.74,"home_advantage":0.3},"exp_diff":1.04,"league_goals":2.9,
             "missing":[0.4,1.2],"captured_at":"2026-10-04T10:24:16+00:00","source":"prospective",
             "steps":{"now_share":0.6,"record":[[1.67,1.03,17],[1.1,1.5,16]],"league":[1.5,1.2],"shrunk":[1.62,1.39,1.13,1.12],"plain":[1.51,1.13],
               "open_total":null,"base":[1.6,1.2],"scale":1.123,"xg":[1.8,1.07],"poisson":[0.52,0.24,0.24],"boost":1.051,"chances":[0.508,0.252,0.24],"likely":"1-1",
               "weights":{"now":[0.6,0.2],"shrink":6,"open":0.75,"draw":[1.1,1.5],"absence":0.1,"line":0.005}}}}}
        """;

    [Fact]
    public async Task The_Model_shows_its_record_its_changes_and_one_match_worked_through()
    {
        using var site = new SiteFactory("production", r => StubHandler.Json(r.RequestUri!.Query.Contains("p_key=model") ? Doc
            : r.RequestUri.Query.Contains("p_key=site") ? Site : "null"));
        var client = site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com") });
        var r = await client.GetAsync("/model");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains("Live model: match-prediction 9afa9ed", html);
        Assert.Contains("<span class=\"neg\">&#x2B;0.0200</span>", html);                      // behind the market
        Assert.Contains("Improvement</div><div class=\"stats-value mc-value\"><span class=\"pos\">−0.00210</span>", html);
        Assert.Contains("<td class=\"mc-no\">A28</td>", html);
        Assert.Contains("In the model", html);
        Assert.Contains("Proven on this test, but rejected</span>", html);                     // the Admin area's pointer taken off
        Assert.Contains("One match, step by step", html);
        Assert.Contains("Final score: Arsenal 2–0 Leeds", html);
        Assert.Contains("<div class=\"why-row\"><span>Home goals, Arsenal</span><b>(1.62 &#x2B; 1.39) ÷ 2 = 1.51</b></div>", html);
        Assert.Contains("<div class=\"why-tip\">Arsenal&#x27;s scoring at home and Leeds&#x27;s conceding away", html);
    }

    [Fact]
    public async Task Before_the_nightly_run_has_written_it_the_page_says_so()
    {
        using var site = new SiteFactory("production", r => StubHandler.Json(r.RequestUri!.Query.Contains("p_key=site") ? Site : "null"));
        var client = site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com") });
        var html = await client.GetStringAsync("/model");
        Assert.Contains("id=\"model-empty\"", html);
    }
}
