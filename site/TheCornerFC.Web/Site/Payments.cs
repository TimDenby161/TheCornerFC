using System.Globalization;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TheCornerFC.Web.Site;

// Subscriptions are paid through Stripe (web/src/lib/server/payments.ts): its hosted checkout takes
// the card (no card detail ever reaches this site), and its webhook tells this server who has paid,
// which is written to the `subscriptions` table the database's paywall reads. Nothing here is
// switched on until the server has all five secrets (the app's settings in Azure, never the code):
//   STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET   Stripe's API key and the webhook's signing secret
//   STRIPE_PRICE_MONTHLY, STRIPE_PRICE_YEARLY  the two prices' ids in Stripe
//   SUPABASE_SERVICE_KEY                       the database key that may write `subscriptions`
public sealed record Payments(string Key, string Hook, string Monthly, string Yearly, string Db)
{
    // Only the live site takes real money: anywhere else a live Stripe key is treated as no key at
    // all, so staging can be given test keys and nothing else.
    public static Payments? From(IConfiguration settings, SiteEnvironment env)
    {
        string? Get(string k) => settings[k] is { Length: > 0 } v ? v : null;
        var key = Get("STRIPE_SECRET_KEY");
        if (!env.IsProduction && key is not null && !key.StartsWith("sk_test_", StringComparison.Ordinal)) return null;
        return key is not null && Get("STRIPE_WEBHOOK_SECRET") is { } hook && Get("STRIPE_PRICE_MONTHLY") is { } m && Get("STRIPE_PRICE_YEARLY") is { } y && Get("SUPABASE_SERVICE_KEY") is { } db
            ? new(key, hook, m, y, db) : null;
    }

    // Stripe takes a form, with nested names in brackets: { a: { b: [1] } } is a[b][0]=1
    public static List<KeyValuePair<string, string>> FormBody(JsonElement value, string under = "")
    {
        var into = new List<KeyValuePair<string, string>>();
        void Add(JsonElement v, string name)
        {
            switch (v.ValueKind)
            {
                case JsonValueKind.Null or JsonValueKind.Undefined: break;
                case JsonValueKind.Object: foreach (var p in v.EnumerateObject()) Add(p.Value, name == "" ? p.Name : $"{name}[{p.Name}]"); break;
                case JsonValueKind.Array: var i = 0; foreach (var e in v.EnumerateArray()) Add(e, $"{name}[{i++}]"); break;
                case JsonValueKind.String: into.Add(new(name, v.GetString()!)); break;
                default: into.Add(new(name, v.GetRawText())); break; // numbers as written, true and false
            }
        }
        Add(value, under);
        return into;
    }

    // A webhook is Stripe's only if its signature matches: "t=<when>,v1=<HMAC-SHA256 of 't.body' with
    // the signing secret>", and recent (a copied one can't be sent again later).
    public static bool SignedByStripe(string body, string? header, string secret, DateTimeOffset now, int withinSeconds = 300)
    {
        var parts = (header ?? "").Split(',').Select(p => p.Split('=', 2)).Where(p => p.Length == 2).ToList();
        var t = parts.FirstOrDefault(p => p[0] == "t")?[1];
        var given = parts.Where(p => p[0] == "v1").Select(p => p[1]).ToList();
        if (t is null || given.Count == 0 || !long.TryParse(t, NumberStyles.None, CultureInfo.InvariantCulture, out var at)
            || Math.Abs(now.ToUnixTimeSeconds() - at) > withinSeconds) return false;
        var mac = Convert.ToHexStringLower(HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret), Encoding.UTF8.GetBytes($"{t}.{body}")));
        // compared without stopping at the first difference
        return given.Any(g => CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(g), Encoding.ASCII.GetBytes(mac)));
    }

    // What Stripe says of a subscription, as the `subscriptions` table's row. null: nothing to record
    // (no account named on it, or a checkout that hasn't been paid).
    public sealed record SubscriptionRow(
        [property: JsonPropertyName("user_id")] string UserId, [property: JsonPropertyName("status")] string Status,
        [property: JsonPropertyName("plan")] string? Plan, [property: JsonPropertyName("current_period_end")] string? CurrentPeriodEnd,
        [property: JsonPropertyName("cancel_at_period_end")] bool CancelAtPeriodEnd, [property: JsonPropertyName("provider")] string Provider,
        [property: JsonPropertyName("provider_customer")] string ProviderCustomer, [property: JsonPropertyName("provider_subscription")] string ProviderSubscription,
        [property: JsonPropertyName("updated_at")] string UpdatedAt);
    static readonly Dictionary<string, string> Statuses = new()
    {
        ["active"] = "active", ["trialing"] = "trialing", ["past_due"] = "past_due",
        ["canceled"] = "canceled", ["unpaid"] = "canceled", ["incomplete_expired"] = "canceled", ["paused"] = "canceled",
    };
    static string IsoTime(DateTimeOffset t) => t.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture);
    public SubscriptionRow? RowOf(JsonElement s, DateTimeOffset now)
    {
        string? Str(JsonElement e, string k) => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
        JsonElement? Obj(JsonElement e, string k) => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(k, out var v) && v.ValueKind != JsonValueKind.Null ? v : null;
        long? Num(JsonElement? e, string k) => e is { ValueKind: JsonValueKind.Object } o && o.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt64() : null;
        var userId = Obj(s, "metadata") is { } meta ? Str(meta, "user_id") : null;
        if (userId is not { Length: > 0 } || Str(s, "status") is not { } st || !Statuses.TryGetValue(st, out var status)) return null;
        var item = Obj(s, "items") is { } items && Obj(items, "data") is { ValueKind: JsonValueKind.Array } data && data.GetArrayLength() > 0 ? data[0] : (JsonElement?)null;
        var price = item is { } it ? Obj(it, "price") : null;
        var end = Num(item, "current_period_end") ?? Num(s, "current_period_end");
        var interval = price is { } pr && Obj(pr, "recurring") is { } rec ? Str(rec, "interval") : null;
        var priceId = price is { } p2 ? Str(p2, "id") : null;
        var customer = Obj(s, "customer") is { } c ? c.ValueKind == JsonValueKind.String ? c.GetString()! : Str(c, "id") ?? "" : "";
        return new(userId, status,
            priceId == Yearly || interval == "year" ? "yearly" : priceId == Monthly || interval == "month" ? "monthly" : null,
            end is { } e ? IsoTime(DateTimeOffset.FromUnixTimeSeconds(e)) : null,
            (s.TryGetProperty("cancel_at_period_end", out var cape) && cape.ValueKind == JsonValueKind.True) || (Obj(s, "cancel_at") is not null),
            "stripe", customer, Str(s, "id") ?? "", IsoTime(now));
    }
}

// Stripe's API and the `subscriptions` table, asked from here with the server's own keys
public sealed class PaymentsClient(HttpClient http, SiteEnvironment env)
{
    public async Task<JsonElement> Stripe(Payments p, HttpMethod method, string path, object? form = null)
    {
        using var m = new HttpRequestMessage(method, $"https://api.stripe.com/v1/{path}");
        m.Headers.Authorization = new AuthenticationHeaderValue("Bearer", p.Key);
        if (form is not null) m.Content = new FormUrlEncodedContent(Payments.FormBody(JsonSerializer.SerializeToElement(form)));
        using var r = await http.SendAsync(m);
        if (!r.IsSuccessStatusCode) throw new HttpRequestException($"Stripe {path}: {(int)r.StatusCode}");
        return JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement.Clone();
    }

    // The table itself: no visitor's key can read or write it, only the server's
    HttpRequestMessage Table(Payments p, HttpMethod method, string query)
    {
        var m = new HttpRequestMessage(method, $"{env.Url}/rest/v1/subscriptions?{query}");
        m.Headers.Add("apikey", p.Db);
        m.Headers.Authorization = new AuthenticationHeaderValue("Bearer", p.Db);
        return m;
    }
    public async Task Save(Payments p, Payments.SubscriptionRow row)
    {
        using var m = Table(p, HttpMethod.Post, "on_conflict=user_id");
        m.Headers.Add("Prefer", "resolution=merge-duplicates,return=minimal");
        m.Content = new StringContent(JsonSerializer.Serialize(row), Encoding.UTF8, "application/json");
        using var r = await http.SendAsync(m);
        if (!r.IsSuccessStatusCode) throw new HttpRequestException($"subscriptions: {(int)r.StatusCode}");
    }
    public sealed record Kept([property: JsonPropertyName("status")] string Status, [property: JsonPropertyName("provider_customer")] string? ProviderCustomer,
        [property: JsonPropertyName("provider_subscription")] string? ProviderSubscription);
    public async Task<Kept?> KeptFor(Payments p, string userId)
    {
        using var m = Table(p, HttpMethod.Get, $"user_id=eq.{Uri.EscapeDataString(userId)}&select=status,provider_customer,provider_subscription");
        using var r = await http.SendAsync(m);
        if (!r.IsSuccessStatusCode) throw new HttpRequestException($"subscriptions: {(int)r.StatusCode}");
        return JsonSerializer.Deserialize<List<Kept>>(await r.Content.ReadAsStringAsync())?.FirstOrDefault();
    }
}

// Stripe calls this when a subscription starts, renews, fails to renew, is cancelled or ends
// (web/src/routes/stripe/webhook). Each call is checked to be Stripe's, then what Stripe now says of
// that subscription is written to the `subscriptions` table: the database's paywall reads nothing
// else. Always from Stripe's own current record (asked for afresh), so calls arriving out of order
// can't leave an old state. Switched off (not found) until the server has payments' secrets.
public static class StripeWebhook
{
    static readonly HashSet<string> Events = ["checkout.session.completed", "customer.subscription.created", "customer.subscription.updated",
        "customer.subscription.deleted", "customer.subscription.paused", "customer.subscription.resumed"];

    public static void Map(WebApplication app) => app.MapPost("/stripe/webhook", async (HttpContext c, PaymentsClient client, IConfiguration settings, SiteEnvironment env, TimeProvider clock) =>
    {
        if (Payments.From(settings, env) is not { } p) return Results.NotFound();
        using var reader = new StreamReader(c.Request.Body, Encoding.UTF8);
        var body = await reader.ReadToEndAsync();
        if (!Payments.SignedByStripe(body, c.Request.Headers["Stripe-Signature"].ToString(), p.Hook, clock.GetUtcNow())) return Results.BadRequest();
        using var doc = JsonDocument.Parse(body);
        var type = doc.RootElement.GetProperty("type").GetString() ?? "";
        if (!Events.Contains(type)) return Results.Json(new { received = true });
        var obj = doc.RootElement.GetProperty("data").GetProperty("object");
        var id = type == "checkout.session.completed"
            ? obj.TryGetProperty("subscription", out var s) && s.ValueKind == JsonValueKind.String ? s.GetString() : null
            : obj.TryGetProperty("id", out var i) ? i.GetString() : null;
        if (string.IsNullOrEmpty(id)) return Results.Json(new { received = true });
        // a failure here answers 500, and Stripe sends the event again later
        var sub = await client.Stripe(p, HttpMethod.Get, $"subscriptions/{Uri.EscapeDataString(id)}");
        if (p.RowOf(sub, clock.GetUtcNow()) is { } row) await client.Save(p, row);
        return Results.Json(new { received = true });
    });
}
