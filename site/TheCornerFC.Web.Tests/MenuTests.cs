using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/menu.test.ts, for the C# site
public class MenuTests
{
    [Theory]
    [InlineData("/", "home")]
    [InlineData("/clubs", "table")]
    [InlineData("/players", "table")]
    [InlineData("/club/42/history", "club")]
    [InlineData("/nation/England", "club")]
    [InlineData("/admin/simulation", "bets")]
    [InlineData("/admin/model-vs-market", "tips")]
    [InlineData("/admin/changes/MC-0007", "changes")]
    [InlineData("/simulation", "home")]
    public void Names_the_section_a_page_belongs_to_for_the_stylesheet(string path, string tab) =>
        Assert.Equal(tab, Menu.TabFor(path));

    [Fact]
    public void Keeps_every_admin_page_out_of_the_menus_anyone_else_is_shown()
    {
        var shown = Menu.Main.Append(Menu.Owner).SelectMany(g => g.Sections);
        Assert.DoesNotContain(shown, s => s.Path.StartsWith("/admin") || s.Label is "Paper Simulation" or "Model vs Market" or "Model Change Tracker");
        Assert.Equal(["Model Change Tracker", "Model vs Market", "Paper Simulation"], Menu.Admin.Sections.Select(s => s.Label));
        Assert.All(Menu.Admin.Sections, s => Assert.StartsWith("/admin/", s.Path));
    }

    [Fact]
    public void Links_every_kind_of_page()
    {
        Assert.Equal("/club/42", Menu.PageHref("club", "42"));
        Assert.Equal("/nation/C%C3%B4te%20d'Ivoire", Menu.PageHref("nation", "Côte d'Ivoire"));
    }

    [Theory]
    [InlineData("/index.html", "/")]
    [InlineData("/terms.html", "/terms")]
    [InlineData("/methodology.html", "/methodology")]
    [InlineData("/privacy.html", "/privacy")]
    [InlineData("/terms", null)]
    [InlineData("/other.html", null)]
    public void Sends_the_old_sites_files_to_the_same_page(string path, string? to) => Assert.Equal(to, Menu.OldFile(path));
}
