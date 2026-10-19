using System.Net;
using Microsoft.Extensions.Time.Testing;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/server/database.test.ts, for the C# site
public class DatabaseTests
{
    static readonly SiteEnvironment Live = SiteEnvironment.Named("production");

    static (Database, StubHandler, FakeTimeProvider) With(Func<HttpRequestMessage, HttpResponseMessage> answer)
    {
        var stub = new StubHandler(answer);
        var clock = new FakeTimeProvider(DateTimeOffset.Parse("2026-10-18T12:00:00Z"));
        return (new Database(new HttpClient(stub), Live, clock) { RetryWait = TimeSpan.Zero }, stub, clock);
    }

    [Fact]
    public async Task Asks_for_a_document_with_the_public_key_and_says_when_it_is_not_there()
    {
        var (db, stub, _) = With(r => StubHandler.Json(r.RequestUri!.Query.Contains("p_key=rankings") ? """{"x":1}""" : "null"));
        Assert.Equal(1, (await db.SiteDoc<Dictionary<string, int>>("rankings"))["x"]);
        Assert.StartsWith("https://bookkurhdabdeccckjbn.supabase.co/rest/v1/rpc/site_doc?p_key=rankings&apikey=sb_publishable_", stub.Sent[0].RequestUri!.ToString());
        var missing = await Assert.ThrowsAsync<DatabaseException>(() => db.SiteDoc<object>("clubs/1"));
        Assert.True(missing.Missing);
        Assert.Null(await db.KeptDocOrNull<object>("clubs/1"));
    }

    [Fact]
    public async Task Sends_a_signed_in_visitors_token_so_the_database_decides_what_they_see()
    {
        var (db, stub, _) = With(_ => StubHandler.Json("[]"));
        await db.SiteAsk<object[]>("site_matches", new { p_ids = new[] { 7 } }, "visitor-token");
        var sent = stub.Sent[0];
        Assert.Equal(HttpMethod.Post, sent.Method);
        Assert.Equal("Bearer visitor-token", sent.Headers.Authorization!.ToString());
        Assert.Equal("""{"p_ids":[7]}""", await sent.Content!.ReadAsStringAsync());
        await db.SiteAsk<object[]>("site_matches", new { p_ids = new[] { 7 } });
        Assert.Null(stub.Sent[1].Headers.Authorization);
    }

    [Fact]
    public async Task Tries_once_more_after_a_server_error_or_a_dropped_connection_then_gives_up()
    {
        var calls = 0;
        var (db, _, _) = With(_ => ++calls == 1 ? StubHandler.Json("", HttpStatusCode.BadGateway) : StubHandler.Json("""{"ok":true}"""));
        Assert.True((await db.SiteDoc<Dictionary<string, bool>>("site"))["ok"]);
        Assert.Equal(2, calls);

        calls = 0;
        var (down, _, _) = With(_ => { calls++; throw new HttpRequestException("dropped"); });
        await Assert.ThrowsAsync<HttpRequestException>(() => down.SiteDoc<object>("site"));
        Assert.Equal(2, calls);

        var (refused, stub, _) = With(_ => StubHandler.Json("", HttpStatusCode.Forbidden));
        Assert.Equal(403, (await Assert.ThrowsAsync<DatabaseException>(() => refused.SiteDoc<object>("site"))).Status);
        Assert.Single(stub.Sent);
    }

    [Fact]
    public async Task Keeps_a_shared_document_for_a_minute_but_never_a_failed_read()
    {
        var calls = 0;
        var (db, _, clock) = With(_ => ++calls == 1 ? StubHandler.Json("", HttpStatusCode.Forbidden) : StubHandler.Json($$"""{"n":{{calls}}}"""));
        await Assert.ThrowsAsync<DatabaseException>(() => db.KeptDoc<Dictionary<string, int>>("site"));
        Assert.Equal(2, (await db.KeptDoc<Dictionary<string, int>>("site"))["n"]);
        clock.Advance(TimeSpan.FromSeconds(59));
        Assert.Equal(2, (await db.KeptDoc<Dictionary<string, int>>("site"))["n"]);
        clock.Advance(TimeSpan.FromSeconds(2));
        Assert.Equal(3, (await db.KeptDoc<Dictionary<string, int>>("site"))["n"]);
    }

    [Fact]
    public async Task Never_keeps_a_read_that_timed_out()
    {
        var calls = 0;
        var (db, _, _) = With(_ => ++calls == 1 ? throw new TaskCanceledException("timed out") : StubHandler.Json("""{"n":1}"""));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => db.KeptDoc<Dictionary<string, int>>("nations"));
        Assert.Equal(1, (await db.KeptDoc<Dictionary<string, int>>("nations"))["n"]);
    }

    [Fact]
    public async Task Two_readers_of_one_document_as_different_types_each_get_their_own()
    {
        var (db, _, _) = With(_ => StubHandler.Json("""{"generated_at":"x"}"""));
        Assert.Single(await db.KeptDoc<Dictionary<string, string>>("site"));
        Assert.Equal("x", (await db.KeptDoc<Dictionary<string, object>>("site"))["generated_at"].ToString());
    }

    [Fact]
    public async Task Shares_answers_between_signed_out_visitors_only()
    {
        var calls = 0;
        var (db, _, _) = With(_ => StubHandler.Json($"[{++calls}]"));
        Assert.Equal(new[] { 1 }, await db.AskAs<int[]>(null, "site_matches", new { p_ids = new[] { 1 } }));
        Assert.Equal(new[] { 1 }, await db.AskAs<int[]>(null, "site_matches", new { p_ids = new[] { 1 } }));
        Assert.Equal(new[] { 2 }, await db.AskAs<int[]>("token", "site_matches", new { p_ids = new[] { 1 } }));
        Assert.Equal(new[] { 3 }, await db.AskAs<int[]>("token", "site_matches", new { p_ids = new[] { 1 } }));
    }
}
