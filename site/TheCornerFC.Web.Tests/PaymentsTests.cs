using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
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
    };
    static readonly Payments P = new("sk", "wh", "price_m", "price_y", "db");
    const string Known = "6624ddd652ee78d27211f2d32373bb1b7277e4d2b5af8aff64cac0580f3e651f";

    [Fact]
    public void Payments_are_off_until_every_secret_is_set_and_staging_takes_test_keys_only()
    {
        var staging = SiteEnvironment.Named("staging");
        var production = SiteEnvironment.Named("production");
        Assert.Null(Payments.From(Settings([]), production));
        Assert.Null(Payments.From(Settings(All.Where(kv => kv.Key != "SUPABASE_SERVICE_KEY").ToDictionary(kv => kv.Key, kv => (string?)kv.Value)), production));
        Assert.Equal(new Payments("sk_test_1", "whsec_test", "price_m", "price_y", "service"), Payments.From(Settings(All.ToDictionary(kv => kv.Key, kv => (string?)kv.Value)), staging));
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
        Assert.Contains("\"user_id\":\"u1\"", site.Handler.Bodies[saved]);
        Assert.Contains("\"plan\":\"yearly\"", site.Handler.Bodies[saved]);
        // one not signed by Stripe goes no further
        var forged = new HttpRequestMessage(HttpMethod.Post, "/stripe/webhook") { Content = new StringContent(body, Encoding.UTF8, "application/json") };
        forged.Headers.Add("Stripe-Signature", $"t={t},v1={Sign(body, "someone-else", t)}");
        Assert.Equal(HttpStatusCode.BadRequest, (await Client(site).SendAsync(forged)).StatusCode);
        Assert.Single(site.Handler.Sent, x => x.RequestUri!.Host == "api.stripe.com");
    }

    [Fact]
    public async Task Subscribing_opens_Stripes_checkout_for_this_account()
    {
        var cookie = $"{Sessions.Cookie}={Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(new Session("access-1", "refresh-1", DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), "user-1", "fan@example.com")))}";
        using var site = new SiteFactory("staging", r =>
            r.RequestUri!.Host == "api.stripe.com" ? StubHandler.Json("""{"url":"https://checkout.stripe.com/c/pay/cs_1"}""")
            : r.RequestUri.AbsolutePath == "/rest/v1/subscriptions" ? StubHandler.Json("[]") : StubHandler.Json("null"), All);
        var m = new HttpRequestMessage(HttpMethod.Post, "/account?/subscribe") { Content = new FormUrlEncodedContent(new Dictionary<string, string> { ["plan"] = "yearly" }) };
        m.Headers.Add("Origin", "https://staging.thecornerfc.com");
        m.Headers.Add("Accept", "application/json");
        m.Headers.Add("Cookie", cookie);
        var r = await Client(site).SendAsync(m);
        Assert.Contains("\"location\":\"https://checkout.stripe.com/c/pay/cs_1\"", await r.Content.ReadAsStringAsync());
        var form = site.Handler.Bodies[site.Handler.Sent.Single(x => x.RequestUri!.Host == "api.stripe.com")];
        Assert.Contains("line_items%5B0%5D%5Bprice%5D=price_y", form);
        Assert.Contains("subscription_data%5Bmetadata%5D%5Buser_id%5D=user-1", form);
        Assert.Contains("customer_email=fan%40example.com", form);
        Assert.Contains("success_url=https%3A%2F%2Fstaging.thecornerfc.com%2Faccount%3Fpaid%3D1", form);
    }
}
