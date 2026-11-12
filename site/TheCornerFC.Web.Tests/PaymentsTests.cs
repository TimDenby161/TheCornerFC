using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using TheCornerFC.Web.Pages;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/server/payments.test.ts, for the C# site, with its webhook and the account page's
// payment forms against stand-ins for Stripe and the database (nothing sent anywhere)
public class PaymentsTests
{
    static IConfiguration Settings(Dictionary<string, string?> values) => new ConfigurationBuilder().AddInMemoryCollection(values).Build();
    static readonly Dictionary<string, string> All = new()
    {
        ["STRIPE_SECRET_KEY"] = "sk_test_1", ["STRIPE_WEBHOOK_SECRET"] = "whsec_test", ["STRIPE_PRICE_MONTHLY"] = "price_m",
        ["STRIPE_PRICE_YEARLY"] = "price_y", ["SUPABASE_SERVICE_KEY"] = "service",
        ["STRIPE_PRICE_FOUNDER_MONTHLY"] = "price_fm", ["STRIPE_PRICE_FOUNDER_YEARLY"] = "price_fy",
    };
    static readonly Payments P = new("sk", "wh", "price_m", "price_y", "db", "price_fm", "price_fy");
    const string Known = "6624ddd652ee78d27211f2d32373bb1b7277e4d2b5af8aff64cac0580f3e651f";

    [Fact]
    public void Payments_are_off_until_every_secret_is_set_and_staging_takes_test_keys_only()
    {
        var staging = SiteEnvironment.Named("staging");
        var production = SiteEnvironment.Named("production");
        Assert.Null(Payments.From(Settings([]), production));
        Assert.Null(Payments.From(Settings(All.Where(kv => kv.Key != "SUPABASE_SERVICE_KEY").ToDictionary(kv => kv.Key, kv => (string?)kv.Value)), production));
        Assert.Equal(new Payments("sk_test_1", "whsec_test", "price_m", "price_y", "service", "price_fm", "price_fy"), Payments.From(Settings(All.ToDictionary(kv => kv.Key, kv => (string?)kv.Value)), staging));
        Assert.Null(Payments.From(Settings(All.Where(kv => kv.Key != "STRIPE_PRICE_FOUNDER_YEARLY").ToDictionary(kv => kv.Key, kv => (string?)kv.Value)), staging));
        var live = All.ToDictionary(kv => kv.Key, kv => (string?)kv.Value);
        live["STRIPE_SECRET_KEY"] = "sk_live_1";
        Assert.Null(Payments.From(Settings(live), staging));
        Assert.NotNull(Payments.From(Settings(live), production));
    }

    [Fact]
    public void Stripes_forms_carry_nested_names_in_brackets()
    {
        var form = Payments.FormBody(JsonSerializer.SerializeToElement(new Dictionary<string, object?>
        {
            ["mode"] = "subscription", ["line_items"] = new[] { new { price = "p", quantity = 1 } },
            ["subscription_data"] = new { metadata = new { user_id = "u" } }, ["skip"] = null,
        }));
        Assert.Equal("mode=subscription&line_items%5B0%5D%5Bprice%5D=p&line_items%5B0%5D%5Bquantity%5D=1&subscription_data%5Bmetadata%5D%5Buser_id%5D=u",
            new FormUrlEncodedContent(form).ReadAsStringAsync().Result);
    }

    static string Sign(string body, string secret, long t) =>
        Convert.ToHexStringLower(HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret), Encoding.UTF8.GetBytes($"{t}.{body}")));

    [Fact]
    public void A_webhook_is_taken_only_with_Stripes_signature_and_only_a_recent_one()
    {
        const string body = """{"type":"x"}""", secret = "whsec_test";
        const long t = 1_800_000_000;
        var sig = Sign(body, secret, t);
        // (a known answer, so the check isn't only of the code against itself)
        Assert.Equal(Known, sig);
        var at = DateTimeOffset.FromUnixTimeSeconds(t);
        Assert.True(Payments.SignedByStripe(body, $"t={t},v1={sig}", secret, at.AddSeconds(5)));
        Assert.True(Payments.SignedByStripe(body, $"t={t},v1=bad,v1={sig}", secret, at));
        Assert.False(Payments.SignedByStripe(body + " ", $"t={t},v1={sig}", secret, at));
        Assert.False(Payments.SignedByStripe(body, $"t={t},v1={sig}", "other", at));
        Assert.False(Payments.SignedByStripe(body, $"t={t},v1={sig}", secret, at.AddSeconds(301)));
        Assert.False(Payments.SignedByStripe(body, null, secret, at));
        Assert.False(Payments.SignedByStripe(body, $"v1={sig}", secret, at));
    }

    static JsonElement Sub(string extra = "") => JsonDocument.Parse(
        "{\"id\":\"sub_1\",\"customer\":\"cus_1\",\"status\":\"active\",\"cancel_at_period_end\":false,\"metadata\":{\"user_id\":\"u1\"}," +
        "\"items\":{\"data\":[{\"current_period_end\":1800000000,\"price\":{\"id\":\"price_y\",\"recurring\":{\"interval\":\"year\"}}}]}" + extra + "}").RootElement;

    [Fact]
    public void Stripes_subscription_becomes_the_tables_row()
    {
        var now = DateTimeOffset.Parse("2026-10-08T12:00:00Z");
        Assert.Equal(new Payments.SubscriptionRow("u1", "active", "yearly", "2027-01-15T08:00:00.000Z", false, "stripe", "cus_1", "sub_1", "2026-10-08T12:00:00.000Z"),
            P.RowOf(Sub(), now));
        // older API versions keep the period's end on the subscription; a customer may come whole
        var old = JsonDocument.Parse("""
            {"id":"sub_1","customer":{"id":"cus_2"},"status":"active","current_period_end":1800000000,"metadata":{"user_id":"u1"},"items":{"data":[{"price":{"id":"price_m"}}]}}
            """).RootElement;
        Assert.Equal(("monthly", "2027-01-15T08:00:00.000Z", "cus_2"), P.RowOf(old, now) is { } r ? (r.Plan, r.CurrentPeriodEnd, r.ProviderCustomer) : default);
        Assert.Equal("past_due", P.RowOf(Sub().ToString().Replace("\"active\"", "\"past_due\"") is var j ? JsonDocument.Parse(j).RootElement : default, now)!.Status);
        Assert.Equal("canceled", P.RowOf(JsonDocument.Parse(Sub().ToString().Replace("\"active\"", "\"unpaid\"")).RootElement, now)!.Status);
        Assert.True(P.RowOf(Sub(""","cancel_at":1800000000"""), now)!.CancelAtPeriodEnd);
        // a checkout not yet paid, or a subscription naming no account: nothing to record
        Assert.Null(P.RowOf(JsonDocument.Parse(Sub().ToString().Replace("\"active\"", "\"incomplete\"")).RootElement, now));
        Assert.Null(P.RowOf(JsonDocument.Parse(Sub().ToString().Replace("\"user_id\":\"u1\"", "\"x\":\"y\"")).RootElement, now));
    }

    // ---- the webhook and the account page, end to end against stand-ins
    static HttpClient Client(SiteFactory site) =>
        site.CreateClient(new() { AllowAutoRedirect = false, BaseAddress = new Uri("https://staging.thecornerfc.com"), HandleCookies = false });

    [Fact]
    public async Task Without_its_secrets_the_webhook_isnt_there_and_subscribing_is_coming_soon()
    {
        using var site = new SiteFactory("staging");
        var r = await Client(site).PostAsync("/stripe/webhook", new StringContent("{}", Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
        var m = new HttpRequestMessage(HttpMethod.Post, "/account?/subscribe") { Content = new FormUrlEncodedContent(new Dictionary<string, string> { ["plan"] = "monthly" }) };
        m.Headers.Add("Origin", "https://staging.thecornerfc.com");
        m.Headers.Add("Accept", "application/json");
        Assert.Contains("Subscriptions are coming soon.", await (await Client(site).SendAsync(m)).Content.ReadAsStringAsync());
        Assert.DoesNotContain(site.Handler.Sent, x => x.RequestUri!.Host == "api.stripe.com");
    }

    // Signed out, the Subscribe view gives the price and the way on: Google, which comes back to
    // this view, or an account by email, which does the same
    [Fact]
    public async Task Signed_out_the_subscribe_view_gives_the_price_and_the_way_to_an_account()
    {
        using var site = new SiteFactory("staging", r => StubHandler.Json("null"), All);
        var page = await Client(site).GetStringAsync("/account?view=subscribe");
        Assert.Contains("a month, or", page);
        Assert.Contains("you come straight back here to choose your plan", page);
        Assert.Contains("<input type=\"hidden\" name=\"back\" value=\"/account?view=subscribe\" />", page);
        Assert.Contains("href=\"/account?view=signup&amp;then=subscribe\"", page);
        Assert.Contains("href=\"/account?view=signin&amp;then=subscribe\"", page);
        Assert.Contains("href=\"/match/example\"", page);
        Assert.DoesNotContain("name=\"plan\"", page); // the plans are a signed-in visitor's to pick
    }

    [Fact]
    public async Task The_webhook_records_what_Stripe_now_says_of_the_subscription()
    {
        using var site = new SiteFactory("staging", r =>
            r.RequestUri!.Host == "api.stripe.com" ? StubHandler.Json(Sub().ToString())
            : r.RequestUri.AbsolutePath == "/rest/v1/subscriptions" ? new HttpResponseMessage(HttpStatusCode.Created) : StubHandler.Json("null"), All);
        var body = """{"type":"checkout.session.completed","data":{"object":{"id":"cs_1","subscription":"sub_1"}}}""";
        var t = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var signed = new HttpRequestMessage(HttpMethod.Post, "/stripe/webhook") { Content = new StringContent(body, Encoding.UTF8, "application/json") };
        signed.Headers.Add("Stripe-Signature", $"t={t},v1={Sign(body, "whsec_test", t)}");
        var r = await Client(site).SendAsync(signed);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        // Stripe asked afresh for the subscription, with the server's key; the row written with the service key
        var asked = site.Handler.Sent.Single(x => x.RequestUri!.Host == "api.stripe.com");
        Assert.Equal("/v1/subscriptions/sub_1", asked.RequestUri!.AbsolutePath);
        Assert.Equal("Bearer sk_test_1", asked.Headers.Authorization!.ToString());
        var saved = site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/rest/v1/subscriptions");
        Assert.Equal("?on_conflict=user_id", saved.RequestUri!.Query);
        Assert.Equal("Bearer service", saved.Headers.Authorization!.ToString());
        Assert.Equal("service", saved.Headers.GetValues("apikey").Single());
        Assert.Contains("\"user_id\":\"u1\"", site.Handler.Bodies[saved]);
        Assert.Contains("\"plan\":\"yearly\"", site.Handler.Bodies[saved]);
        // one not signed by Stripe goes no further
        var forged = new HttpRequestMessage(HttpMethod.Post, "/stripe/webhook") { Content = new StringContent(body, Encoding.UTF8, "application/json") };
        forged.Headers.Add("Stripe-Signature", $"t={t},v1={Sign(body, "someone-else", t)}");
        Assert.Equal(HttpStatusCode.BadRequest, (await Client(site).SendAsync(forged)).StatusCode);
        Assert.Single(site.Handler.Sent, x => x.RequestUri!.Host == "api.stripe.com");
    }

    [Fact]
    public async Task A_new_supabase_secret_key_goes_on_apikey_alone()
    {
        using var site = new SiteFactory("staging", r => StubHandler.Json("[]"), All);
        var client = site.Services.GetRequiredService<PaymentsClient>();
        await client.KeptFor(P with { Db = "sb_secret_abc" }, "u1");
        var asked = site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/rest/v1/subscriptions");
        Assert.Equal("sb_secret_abc", asked.Headers.GetValues("apikey").Single());
        Assert.Null(asked.Headers.Authorization);
    }

    [Fact]
    public void The_founders_price_is_offered_until_the_end_of_31_January_2027_then_the_standard_price()
    {
        var lastMinute = new DateTimeOffset(2027, 1, 31, 23, 59, 59, TimeSpan.Zero);
        Assert.Equal("price_fm", P.PriceOf("monthly", lastMinute));
        Assert.Equal("price_fy", P.PriceOf("yearly", lastMinute));
        Assert.Equal("price_m", P.PriceOf("monthly", Payments.FounderEnds));
        Assert.Equal("price_y", P.PriceOf("yearly", Payments.FounderEnds));
        Assert.Equal(new AccountModel.PriceWords("£4.99 a month", "£39 a year",
            "Founder's price until 31 January 2027 (then £5.99 a month or £49 a year), kept for as long as you stay subscribed."), AccountModel.PricesAt(lastMinute));
        Assert.Equal(new AccountModel.PriceWords("£5.99 a month", "£49 a year", null), AccountModel.PricesAt(Payments.FounderEnds));
        // a founder's subscription is recorded under its plan like any other
        var row = P.RowOf(JsonDocument.Parse("""{"id":"sub_1","customer":"cus_1","status":"active","metadata":{"user_id":"u1"},"items":{"data":[{"price":{"id":"price_fy"}}]}}""").RootElement, DateTimeOffset.UtcNow);
        Assert.Equal("yearly", row!.Plan);
    }

    [Fact]
    public async Task Subscribing_opens_Stripes_checkout_for_this_account()
    {
        // (the cookie names another account: the checkout is for the one the token is, as the sign-in service says)
        var cookie = Cookie("someone-else", "other@example.com");
        using var site = new SiteFactory("staging", r =>
            r.RequestUri!.Host == "api.stripe.com" ? StubHandler.Json("""{"url":"https://checkout.stripe.com/c/pay/cs_1"}""")
            : r.RequestUri.AbsolutePath == "/auth/v1/user" ? StubHandler.Json("""{"id":"user-1","email":"fan@example.com"}""")
            : r.RequestUri.AbsolutePath == "/rest/v1/subscriptions" ? StubHandler.Json("[]") : StubHandler.Json("null"), All);
        var m = new HttpRequestMessage(HttpMethod.Post, "/account?/subscribe") { Content = new FormUrlEncodedContent(new Dictionary<string, string> { ["plan"] = "yearly" }) };
        m.Headers.Add("Origin", "https://staging.thecornerfc.com");
        m.Headers.Add("Accept", "application/json");
        m.Headers.Add("Cookie", cookie);
        var r = await Client(site).SendAsync(m);
        Assert.Contains("\"location\":\"https://checkout.stripe.com/c/pay/cs_1\"", await r.Content.ReadAsStringAsync());
        var form = site.Handler.Bodies[site.Handler.Sent.Single(x => x.RequestUri!.Host == "api.stripe.com")];
        // the founder's yearly price until it ends, sold by Stripe as merchant of record, on the API version that allows it
        Assert.Contains(Payments.Founder(DateTimeOffset.UtcNow) ? "line_items%5B0%5D%5Bprice%5D=price_fy" : "line_items%5B0%5D%5Bprice%5D=price_y", form);
        Assert.Contains("managed_payments%5Benabled%5D=true", form);
        Assert.Equal(Payments.ApiVersion, site.Handler.Sent.Single(x => x.RequestUri!.Host == "api.stripe.com").Headers.GetValues("Stripe-Version").Single());
        Assert.Contains("subscription_data%5Bmetadata%5D%5Buser_id%5D=user-1", form);
        Assert.Contains("customer_email=fan%40example.com", form);
        Assert.Contains("success_url=https%3A%2F%2Fstaging.thecornerfc.com%2Faccount%3Fpaid%3D1", form);
        Assert.Equal("Bearer access-1", site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/auth/v1/user").Headers.Authorization!.ToString());
        Assert.Equal("?user_id=eq.user-1&select=status,provider_customer,provider_subscription", site.Handler.Sent.Single(x => x.RequestUri!.AbsolutePath == "/rest/v1/subscriptions").RequestUri!.Query);
    }

    static string Cookie(string userId, string email) =>
        $"{Sessions.Cookie}={Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(new Session("access-1", "refresh-1", DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), userId, email)))}";

    // The cookie is the visitor's to write. One that names somebody else's account, with a token
    // the sign-in service doesn't know, reaches neither the subscriptions table nor Stripe.
    [Theory]
    [InlineData("subscribe")]
    [InlineData("manage")]
    [InlineData("erase")]
    public async Task A_made_up_cookie_naming_another_account_gets_nowhere_near_its_subscription(string action)
    {
        using var site = new SiteFactory("staging", r =>
            r.RequestUri!.AbsolutePath == "/auth/v1/user" ? StubHandler.Json("""{"error_code":"bad_jwt"}""", HttpStatusCode.Forbidden)
            : r.RequestUri.AbsolutePath == "/rest/v1/subscriptions" ? StubHandler.Json("""[{"status":"active","provider_customer":"cus_victim","provider_subscription":"sub_victim"}]""")
            : StubHandler.Json("null"), All);
        var m = new HttpRequestMessage(HttpMethod.Post, $"/account?handler={action}") { Content = new FormUrlEncodedContent(new Dictionary<string, string> { ["plan"] = "monthly" }) };
        m.Headers.Add("Origin", "https://staging.thecornerfc.com");
        m.Headers.Add("Accept", "application/json");
        m.Headers.Add("Cookie", Cookie("victim", "victim@example.com"));
        var r = await Client(site).SendAsync(m);
        Assert.Equal(HttpStatusCode.Unauthorized, r.StatusCode);
        Assert.Contains("Sign in first.", await r.Content.ReadAsStringAsync());
        Assert.DoesNotContain(site.Handler.Sent, x => x.RequestUri!.Host == "api.stripe.com" || x.RequestUri.AbsolutePath == "/rest/v1/subscriptions"
            || x.RequestUri.AbsolutePath == "/rest/v1/rpc/delete_my_account");
    }

    // and a real visitor's own token acts on their own subscription, whatever the cookie says
    [Fact]
    public async Task Managing_and_deleting_act_on_the_account_the_token_is()
    {
        using var site = new SiteFactory("staging", r =>
            r.RequestUri!.Host == "api.stripe.com" ? StubHandler.Json("""{"url":"https://billing.stripe.com/p/session/1"}""")
            : r.RequestUri.AbsolutePath == "/auth/v1/user" ? StubHandler.Json("""{"id":"user-1","email":"fan@example.com"}""")
            : r.RequestUri.AbsolutePath == "/auth/v1/logout" ? new HttpResponseMessage(HttpStatusCode.NoContent)
            : r.RequestUri.AbsolutePath == "/rest/v1/subscriptions" ? StubHandler.Json("""[{"status":"active","provider_customer":"cus_1","provider_subscription":"sub_1"}]""")
            : StubHandler.Json("null"), All);
        foreach (var action in new[] { "manage", "erase" })
        {
            var m = new HttpRequestMessage(HttpMethod.Post, $"/account?handler={action}") { Content = new FormUrlEncodedContent(new Dictionary<string, string>()) };
            m.Headers.Add("Origin", "https://staging.thecornerfc.com");
            m.Headers.Add("Accept", "application/json");
            m.Headers.Add("Cookie", Cookie("victim", "victim@example.com"));
            Assert.Equal(HttpStatusCode.OK, (await Client(site).SendAsync(m)).StatusCode);
        }
        Assert.All(site.Handler.Sent.Where(x => x.RequestUri!.AbsolutePath == "/rest/v1/subscriptions"), x => Assert.StartsWith("?user_id=eq.user-1&", x.RequestUri!.Query));
        Assert.Equal(2, site.Handler.Sent.Count(x => x.RequestUri!.AbsolutePath == "/rest/v1/subscriptions"));
        Assert.Contains(site.Handler.Sent, x => x.Method == HttpMethod.Delete && x.RequestUri!.AbsoluteUri == "https://api.stripe.com/v1/subscriptions/sub_1");
    }
}
