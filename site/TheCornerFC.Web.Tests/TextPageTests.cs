using System.Net;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/textPage.test.ts, for the C# site, and the three text pages served whole
public class TextPageTests
{
    const string File = """
        <!doctype html><html><head><title>Terms of use · The Corner FC</title>
        <meta name="description" content="The terms for using The Corner FC.">
        <link rel="stylesheet" href="assets/page.css"></head><body><main>
        <p class="back"><a href="./">The Corner FC</a></p><h1>Terms</h1>
        <p>See <a href="privacy.html#corrections">report an error</a>, <a href="methodology.html">how it works</a>, the <a href="./#/lineups">line-up record</a>
        and <a href=".well-known/security.txt">security.txt</a>, or <a href="https://example.org/terms.html">elsewhere</a>.</p>
        <div id="fresh-live" class="live" aria-live="polite"><p class="muted">Loading…</p></div>
        <h2 id="more">More</h2><div id="version-live" class="live"><p>Loading…</p></div><p>The end.</p>
        </main><script src="assets/data.js"></script></body></html>
        """;

    [Fact]
    public void Takes_the_title_the_description_and_the_text_and_nothing_outside_it()
    {
        var page = TextPage.From(File);
        Assert.Equal("Terms of use · The Corner FC", page.Title);
        Assert.Equal("The terms for using The Corner FC.", page.Description);
        Assert.Contains("<h1>Terms</h1>", page.Html);
        Assert.DoesNotContain("<script", page.Html);
        Assert.DoesNotContain("page.css", page.Html);
    }

    [Fact]
    public void Points_the_old_sites_links_at_this_one_and_leaves_other_sites_alone()
    {
        var html = TextPage.From(File).Html;
        foreach (var link in new[] { "href=\"/privacy#corrections\"", "href=\"/methodology\"", "href=\"/lineups\"", "href=\"/\"",
                     "href=\"/.well-known/security.txt\"", "href=\"https://example.org/terms.html\"" })
            Assert.Contains(link, html);
    }

    [Fact]
    public void Cuts_the_text_at_each_box_of_live_figures()
    {
        var parts = TextPage.From(File).Parts();
        Assert.Equal(["fresh-live", "version-live", null], parts.Select(p => p.Live));
        Assert.Contains("<h2 id=\"more\">More</h2>", parts[1].Html);
        Assert.Contains("The end.", parts[2].Html);
        Assert.DoesNotContain("Loading…", string.Concat(parts.Select(p => p.Html)));
    }

    [Theory]
    [InlineData("/terms", "Terms of use · The Corner FC")]
    [InlineData("/privacy", "Privacy, corrections and security · The Corner FC")]
    public async Task Serves_each_text_page_from_the_sites_own_file_without_the_menu(string path, string title)
    {
        using var site = new SiteFactory("production");
        var r = await site.CreateClient(new() { BaseAddress = new Uri("https://thecornerfc.com") }).GetAsync(path);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var html = await r.Content.ReadAsStringAsync();
        Assert.Contains($"<title>{title}</title>", html);
        Assert.Contains("href=\"/styles/page.css\"", html);
        Assert.DoesNotContain("class=\"menu-link\"", html);
        Assert.Contains($"<link rel=\"canonical\" href=\"https://thecornerfc.com{path}\" />", html);
    }
}
