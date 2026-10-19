using System.Collections.Concurrent;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Data;

public sealed class DatabaseException(string what, int status, bool missing = false) : Exception($"{what}: {status}")
{
    public int Status { get; } = status;
    // the row isn't there: this site's "not found"
    public bool Missing { get; } = missing;
}

// Every read of the database goes through here (web/src/lib/server/database.ts). It asks the
// database's own functions over HTTPS with the public key, or with a signed-in visitor's token so
// the database decides what they may see. The server holds no database password.
public sealed class Database(HttpClient http, SiteEnvironment env, TimeProvider clock)
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    public TimeSpan RetryWait { get; init; } = TimeSpan.FromMilliseconds(400);

    // A request that fails outright or with a server error (a dropped connection, a busy moment)
    // is sent once more after a moment before the page gives up.
    async Task<HttpResponseMessage> Ask(Func<HttpRequestMessage> request, CancellationToken stop)
    {
        for (var again = false; ; again = true)
        {
            try
            {
                var r = await http.SendAsync(request(), stop);
                if ((int)r.StatusCode < 500 || again) return r;
                r.Dispose();
            }
            catch (HttpRequestException) when (!again) { }
            await Task.Delay(RetryWait, clock, stop);
        }
    }

    // One row of site.docs by its key ("rankings", "clubs/42"). A key with no row is "not found".
    public async Task<T> SiteDoc<T>(string key, CancellationToken stop = default)
    {
        var q = $"p_key={Uri.EscapeDataString(key)}&apikey={Uri.EscapeDataString(env.Key)}";
        using var r = await Ask(() => new HttpRequestMessage(HttpMethod.Get, $"{env.Url}/rest/v1/rpc/site_doc?{q}"), stop);
        if (!r.IsSuccessStatusCode) throw new DatabaseException(key, (int)r.StatusCode);
        var body = await r.Content.ReadAsStringAsync(stop);
        if (body.Trim() == "null") throw new DatabaseException(key, 404, missing: true);
        return JsonSerializer.Deserialize<T>(body, Json)!;
    }

    // A database function that answers one page's question from the tables (site_matches,
    // site_players ...). `token` is a signed-in visitor's, so the database can give a subscriber
    // the paid rows.
    public async Task<T> SiteAsk<T>(string fn, object parameters, string? token = null, CancellationToken stop = default)
    {
        var json = JsonSerializer.Serialize(parameters, Json);
        using var r = await Ask(() =>
        {
            var m = new HttpRequestMessage(HttpMethod.Post, $"{env.Url}/rest/v1/rpc/{fn}")
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            };
            m.Headers.Add("apikey", env.Key);
            if (token is not null) m.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            return m;
        }, stop);
        if (!r.IsSuccessStatusCode) throw new DatabaseException(fn, (int)r.StatusCode);
        return JsonSerializer.Deserialize<T>(await r.Content.ReadAsStringAsync(stop), Json)!;
    }

    // Rows every page needs that change a few times a day at most are kept for a minute, so a
    // busy moment is one read of the database and not one per visitor. A failed read isn't kept.
    readonly ConcurrentDictionary<string, (DateTimeOffset At, Task<object> Doc)> kept = new();

    Task<T> Kept<T>(string key, TimeSpan keepFor, Func<Task<T>> read)
    {
        var now = clock.GetUtcNow();
        // (a read that failed or timed out is never handed on: it is asked again)
        if (kept.TryGetValue(key, out var have) && now - have.At < keepFor && !have.Doc.IsFaulted && !have.Doc.IsCanceled)
            return Cast<T>(have.Doc);
        var doc = Box(read());
        kept[key] = (now, doc);
        doc.ContinueWith(_ => kept.TryRemove(new(key, (now, doc))), TaskContinuationOptions.NotOnRanToCompletion);
        // a server runs for weeks: don't let the answers to one-off questions pile up
        if (kept.Count > 500)
            foreach (var (k, v) in kept)
                if (now - v.At > keepFor) kept.TryRemove(k, out _);
        return Cast<T>(doc);
    }

    static async Task<object> Box<T>(Task<T> t) => (await t)!;
    static async Task<T> Cast<T>(Task<object> t) => (T)await t;

    // (kept by type as well as by key, so two readers of one document never share a copy of the wrong type)
    public Task<T> KeptDoc<T>(string key, TimeSpan? keepFor = null) =>
        Kept($"doc:{typeof(T).FullName}:{key}", keepFor ?? TimeSpan.FromMinutes(1), () => SiteDoc<T>(key));

    // The same for a question every signed-out visitor gets the same answer to (a club's matches,
    // say). Never for a signed-in visitor's: theirs may hold paid rows.
    public Task<T> KeptAsk<T>(string fn, object parameters, TimeSpan? keepFor = null) =>
        Kept($"ask:{typeof(T).FullName}:{fn}?{JsonSerializer.Serialize(parameters, Json)}", keepFor ?? TimeSpan.FromMinutes(1),
            () => SiteAsk<T>(fn, parameters));

    // A row that may not be there (a club with no file of its own): null in place of "not found".
    public async Task<T?> KeptDocOrNull<T>(string key, TimeSpan? keepFor = null) where T : class
    {
        try { return await KeptDoc<T>(key, keepFor); }
        catch (DatabaseException e) when (e.Missing) { return null; }
    }

    // A question whose answer depends on who asks (the paid rows): with a signed-in visitor's
    // token, asked afresh for them; without one, the kept answer every signed-out visitor shares.
    public Task<T> AskAs<T>(string? token, string fn, object parameters) =>
        token is not null ? SiteAsk<T>(fn, parameters, token) : KeptAsk<T>(fn, parameters);
}
