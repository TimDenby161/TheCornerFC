using System.Net;
using System.Text;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// A stand-in for the database's web address: answers each request from `answer`, and keeps
// every request it was sent. No network.
public sealed class StubHandler(Func<HttpRequestMessage, HttpResponseMessage> answer) : HttpMessageHandler
{
    public List<HttpRequestMessage> Sent { get; } = [];

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken stop)
    {
        Sent.Add(request);
        return Task.FromResult(answer(request));
    }

    public static HttpResponseMessage Json(string body, HttpStatusCode status = HttpStatusCode.OK) =>
        new(status) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
}

// The whole site, started in memory as one environment, reading a stand-in database.
public sealed class SiteFactory(string environment, Func<HttpRequestMessage, HttpResponseMessage>? answer = null)
    : WebApplicationFactory<Program>
{
    public StubHandler Handler { get; } = new(answer ?? (_ => StubHandler.Json("null")));

    protected override void ConfigureWebHost(Microsoft.AspNetCore.Hosting.IWebHostBuilder builder)
    {
        builder.UseSetting("SITE_ENV", environment);
        builder.ConfigureTestServices(services => services.AddSingleton(sp =>
            new Database(new HttpClient(Handler), SiteEnvironment.Named(environment), TimeProvider.System)));
    }
}
