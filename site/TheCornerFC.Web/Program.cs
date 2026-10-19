using System.Text.Encodings.Web;
using System.Text.Unicode;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.Extensions.WebEncoders;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

// Numbers and dates are written the British way whatever the server's own setting (1,234.5, not
// 1.234,5): the pages say what the current site says
System.Globalization.CultureInfo.DefaultThreadCurrentCulture = System.Globalization.CultureInfo.GetCultureInfo("en-GB");
System.Globalization.CultureInfo.DefaultThreadCurrentUICulture = System.Globalization.CultureInfo.GetCultureInfo("en-GB");

var builder = WebApplication.CreateBuilder(args);

// Which copy of the site this server is, production or staging: from the app's settings, or the
// file scripts/environment.py writes on this machine. None named: the server doesn't start.
var env = SiteEnvironment.Choose(builder.Configuration["SITE_ENV"], builder.Environment.ContentRootPath);
builder.Services.AddSingleton(env);
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddHttpClient<Database>(c => c.Timeout = TimeSpan.FromSeconds(10));
// one Database for the server, so the kept documents are shared between requests
builder.Services.AddSingleton(sp => new Database(
    sp.GetRequiredService<IHttpClientFactory>().CreateClient(nameof(Database)), env, sp.GetRequiredService<TimeProvider>()));
builder.Services.AddRazorPages();
// pages written in UTF-8 as they read (·, é, ’), not as character codes: only <, >, &, quotes are escaped
builder.Services.Configure<WebEncoderOptions>(o => o.TextEncoderSettings = new TextEncoderSettings(UnicodeRanges.All));
// Azure's front door and Cloudflare say which address and scheme the visitor used
builder.Services.Configure<ForwardedHeadersOptions>(o =>
{
    o.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto | ForwardedHeaders.XForwardedHost;
    o.KnownIPNetworks.Clear();
    o.KnownProxies.Clear();
});

var app = builder.Build();

app.UseForwardedHeaders();
app.UseGate(env);
// A page that fails: the fault goes to the server's log, never onto the page
app.UseExceptionHandler("/error/500");
app.UseStatusCodePagesWithReExecute("/error/{0}");
app.UseRouting();
app.MapStaticAssets();
app.MapRazorPages().WithStaticAssets();

// Which copy of the site answered, the commit it was built from and the database it reads: what
// the staging check and a promotion read to know what is really deployed (guide/environments.md).
app.MapGet("/version", (HttpContext c) =>
{
    c.Response.Headers.CacheControl = "no-store";
    return Results.Json(new { environment = env.Name, commit = builder.Configuration["COMMIT"] ?? "local", project = env.Project, site = "csharp" });
});
app.MapGet("/robots.txt", (HttpContext c) =>
{
    c.Response.Headers.CacheControl = "public, max-age=3600";
    return Results.Text(Crawlers.Robots(env, c.Request.Host.Host), "text/plain; charset=utf-8");
});
// The live site's sitemap. Anywhere else there is none.
app.MapGet("/sitemap.xml", async (HttpContext c, Database db) =>
{
    if (!env.IsProduction || c.Request.Host.Host != env.Host) return Results.NotFound();
    var doc = await db.KeptDoc<Rankings>("rankings");
    c.Response.Headers.CacheControl = "public, max-age=86400";
    return Results.Text(Crawlers.Sitemap($"https://{env.Host}", doc.Clubs()), "application/xml; charset=utf-8");
});

app.Run();

// so the tests can start the site (WebApplicationFactory)
public partial class Program;
