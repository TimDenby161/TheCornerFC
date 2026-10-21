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
        Assert.Contains("<span class=\"mc-no\">A28</span>", html);
        Assert.Contains("<span class=\"mc-pill mark-none\">In the model</span>", html);
        Assert.Contains("How it learns:</b> It is the club rank itself", html);
        Assert.Contains("<b>0.21% better</b>", html);                                          // 0.0021 of 0.99
        Assert.Contains("Proven on this test, but rejected</span>", html);                     // the Admin area's pointer taken off
        Assert.DoesNotContain("see why on its page", html);
        Assert.DoesNotContain("/admin/changes", html);                                         // no links into the Admin area
        Assert.Contains("One match, step by step", html);
        Assert.Contains("Final score: Arsenal 2–0 Leeds", html);
        Assert.Contains("<div class=\"why-row\"><span>Home goals, Arsenal</span><b>(1.62 &#x2B; 1.39) ÷ 2 = 1.51</b></div>", html);
        Assert.Contains("<div class=\"why-tip\">Arsenal&#x27;s scoring at home and Leeds&#x27;s conceding away", html);
    }

    const string Stats = """
        {"generated_at":"2026-10-19T02:00:00+00:00",
         "ranges":{"365d":{
           "all":{"n":900,"correct":0.52,"log_loss":0.98,"market":{"n":600,"model_ll":0.99,"market_ll":0.97,"model_correct":0.51,"market_correct":0.53},
             "calibration":[[100,0.05,0.04],[200,0.15,0.17],[0,null,null],[0,null,null],[0,null,null],[0,null,null],[0,null,null],[0,null,null],[0,null,null],[50,0.95,0.9]]},
           "39":{"n":300,"correct":0.55,"log_loss":0.95,"market":{"n":300,"model_ll":0.96,"market_ll":0.95,"model_correct":0.55,"market_correct":0.56},"calibration":[]}}},
         "month_columns":["month","n","correct","log_loss","brier","market_n","model_ll","market_ll","model_correct","market_correct"],
         "monthly":{"all":[["2026-09",400,0.5,0.99,0.59,250,1.0,0.98,0.5,0.52],["2026-10",500,0.54,0.97,0.58,0,null,null,null,null]]}}
        """;
    const string Tracking = """
        {"protocol":"P17","generated_at":"2026-10-18T04:00:00+00:00","start":"2026-10-14","minimum":{"matches":500,"weeks":8},"n":310,"weeks":1,"to":"2026-10-18",
         "changes":{"MC-0031":{"n":310,"weeks":1,"gain":0.0012,"low":-0.01,"high":0.012,"verdict":null,
           "series":[{"week":202642,"n":120,"gain":0.002,"low":-0.02,"high":0.024},{"week":202643,"n":310,"gain":0.0012,"low":-0.01,"high":0.012}]}},"not_run":{},
         "scores":{"MC-0031":{"n":310,"log_loss":0.97,"right":0.53,"against_log_loss":0.9712,"against_right":0.52}}}
        """;

    [Fact]
    public async Task The_Model_shows_the_accuracy_month_by_month_reliability_the_market_and_each_live_test_in_public()
    {
        var doc = Doc.Replace("\"tracking\":null", "\"tracking\":" + Tracking);
        using var site = new SiteFactory("production", r => StubHandler.Json(r.RequestUri!.Query.Contains("p_key=model") ? doc
            : r.RequestUri.Query.Contains("p_key=stats") ? Stats : r.RequestUri.Query.Contains("p_key=site") ? Site : "null"));
        var client = site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://thecornerfc.com") });
        var r = await client.GetAsync("/model");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("public, max-age=300", r.Headers.CacheControl!.ToString());
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains("<form method=\"get\" action=\"/model#accuracy\"", html);
        Assert.Contains("<option value=\"39\">Premier League (300)</option>", html);
        Assert.Contains("Accuracy month by month: All competitions", html);
        Assert.Contains("<tr><td>2026-09</td><td>400</td><td>50.0%</td><td>0.990</td><td>250</td><td>1.000</td><td>0.980</td>", html);
        Assert.Contains("aria-label=\"Reliability: chance said against how often it happened\"", html);
        Assert.Contains("<a class=\"team-link\" href=\"/model?c=39#accuracy\">Premier League</a>", html);
        // each live test week by week, linked to its card on the page, never into the Admin area
        Assert.Contains("Each live test, week by week", html);
        Assert.Contains("<a class=\"team-link\" href=\"#card-MC-0031\">Shots in the attack rating</a>", html);
        Assert.Contains("Gain <b>&#x2B;0.00120</b> on 310 matches over 1 week", html);
        Assert.DoesNotContain("/admin", html);
        // another competition from the address
        var pl = await client.GetStringAsync("/model?c=39");
        Assert.Contains("<option value=\"39\" selected=\"selected\">", pl);
        Assert.Contains("Reliability: Premier League, last 12 months", pl);
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
