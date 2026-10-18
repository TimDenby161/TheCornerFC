namespace TheCornerFC.Web.Site;

// The two copies of the site, and which database each reads (guide/environments.md), as
// web/src/lib/environments.ts has them. Nothing here is secret: a project's id and its
// publishable key only identify it, and the database decides what the key may do. The Python
// jobs name the same projects (PROJECTS in thecornerfc/config.py); a test holds the lists together.
public sealed record SiteEnvironment(string Name, string Project, string Key, string Host, string BotCheck)
{
    public string Url => $"https://{Project}.supabase.co";
    public bool IsProduction => Name == "production";

    public static readonly IReadOnlyDictionary<string, SiteEnvironment> All = new Dictionary<string, SiteEnvironment>
    {
        ["production"] = new("production", "bookkurhdabdeccckjbn", "sb_publishable_JZ_oJVHIO75SFbFc95LQew_3wmKuvM7",
            "thecornerfc.com", "0x4AAAAAAFQgIiqxiuE9dqIM"),
        // Turnstile's published test key, which always passes: staging has no widget of its own
        ["staging"] = new("staging", "sjvzmlbdowebylnzvisa", "sb_publishable_eLnEE_9Qx_BLV4kWpSQACA_-xn1YXNj",
            "staging.thecornerfc.com", "1x00000000000000000000AA"),
    };

    // A server must say which it is. There is no default: one that names neither fails to start.
    public static SiteEnvironment Named(string? name) =>
        name is not null && All.TryGetValue(name, out var env)
            ? env
            : throw new InvalidOperationException(
                $"SITE_ENV must be \"production\" or \"staging\" (it is {(string.IsNullOrEmpty(name) ? "not set" : $"\"{name}\"")}): " +
                "run python scripts/environment.py on this machine, or set it in the app's settings");

    // Which one this server is: SITE_ENV from the app's settings (Azure), or on this machine the
    // file scripts/environment.py writes beside the solution (site/environment.local). Never named
    // by hand.
    public static SiteEnvironment Choose(string? fromSettings, string contentRoot)
    {
        if (!string.IsNullOrEmpty(fromSettings)) return Named(fromSettings);
        var file = Path.Combine(contentRoot, "..", "environment.local");
        var line = File.Exists(file)
            ? File.ReadLines(file).FirstOrDefault(l => l.StartsWith("SITE_ENV=", StringComparison.Ordinal))
            : null;
        return Named(line?["SITE_ENV=".Length..].Trim());
    }
}
