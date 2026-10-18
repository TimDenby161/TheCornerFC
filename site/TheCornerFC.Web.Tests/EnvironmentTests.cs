using System.Text.RegularExpressions;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

public class EnvironmentTests
{
    static string Repo(params string[] parts) => Path.Combine([AppContext.BaseDirectory, "..", "..", "..", "..", "..", .. parts]);

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("prod")]
    public void Has_no_default_a_server_that_names_neither_fails(string? name) =>
        Assert.Throws<InvalidOperationException>(() => SiteEnvironment.Named(name));

    [Fact]
    public void Reads_the_switchs_file_when_the_settings_name_none()
    {
        var root = Directory.CreateTempSubdirectory();
        var web = Directory.CreateDirectory(Path.Combine(root.FullName, "Web"));
        File.WriteAllText(Path.Combine(root.FullName, "environment.local"), "# Written by scripts/environment.py.\nSITE_ENV=staging\n");
        Assert.Equal("staging", SiteEnvironment.Choose(null, web.FullName).Name);
        Assert.Equal("production", SiteEnvironment.Choose("production", web.FullName).Name);
        File.Delete(Path.Combine(root.FullName, "environment.local"));
        Assert.Throws<InvalidOperationException>(() => SiteEnvironment.Choose(null, web.FullName));
    }

    // The two sites and the Python jobs name the same projects and keys: held together here
    [Fact]
    public void Names_the_same_projects_as_the_svelte_site_and_the_jobs()
    {
        var ts = File.ReadAllText(Repo("web", "src", "lib", "environments.ts"));
        var py = File.ReadAllText(Repo("thecornerfc", "config.py"));
        foreach (var env in SiteEnvironment.All.Values)
        {
            Assert.Matches(new Regex($@"{env.Name}: \{{\s*project: '{env.Project}',\s*key: '{Regex.Escape(env.Key)}',\s*host: '{Regex.Escape(env.Host)}'"), ts);
            Assert.Contains(env.Project, py);
        }
    }
}
