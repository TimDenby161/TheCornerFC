using System.Text.RegularExpressions;

namespace TheCornerFC.Web.Site;

// The menu, in the old site's groups (web/src/lib/menu.ts). `Tab` is the name the stylesheet
// knows the section by (body[data-tab]).
public sealed record Section(string Tab, string Label, string Path);
public sealed record MenuGroup(string Label, IReadOnlyList<Section> Sections);

public static partial class Menu
{
    public static readonly IReadOnlyList<MenuGroup> Main =
    [
        new("Ratings", [
            new("table", "Clubs", "/clubs"),
            new("table", "Players", "/players"),
            new("leagues", "Leagues", "/leagues"),
            new("nations", "Nations", "/nations"),
        ]),
        new("Predictions", [
            new("matches", "Matches", "/matches"),
            new("stats", "Stats", "/stats"),
            new("lineups", "Line-up record", "/lineups"),
            new("model", "The Model", "/model"),
        ]),
    ];

    // The Admin area is the site administrator's: in the menu for them only, and every address
    // under /admin is refused to anyone else by the server and by the database.
    public static readonly MenuGroup Admin = new("Admin", [
        new("changes", "Model Change Tracker", "/admin/changes"),
        new("tips", "Model vs Market", "/admin/model-vs-market"),
        new("bets", "Paper Simulation", "/admin/simulation"),
    ]);

    // The fantasy pages are the site owner's: in the menu for the owner only.
    public static readonly MenuGroup Owner = new("Fantasy", [
        new("fpl", "FPL", "/fpl"),
        new("myteam", "My FPL team", "/my-fpl-team"),
        new("efl", "EFL Fantasy", "/efl-fantasy"),
    ]);

    static IEnumerable<Section> Every => Main.Append(Owner).Append(Admin).SelectMany(g => g.Sections);

    // The section a page belongs to: its menu entry, or for a club's, player's, competition's,
    // country's or nation's page "club"; anything else is "home".
    public static string TabFor(string path)
    {
        foreach (var s in Every)
            if (path == s.Path || path.StartsWith(s.Path + "/", StringComparison.Ordinal)) return s.Tab;
        return OwnPage().IsMatch(path) ? "club" : "home";
    }

    public static Section? Current(string path) =>
        Every.FirstOrDefault(s => path.StartsWith(s.Path, StringComparison.Ordinal));

    // A link to a club's, competition's, country's, player's or nation's page.
    public static string PageHref(string kind, string id) => $"/{kind}/{Uri.EscapeDataString(id)}";
    public static string MethodologyHref(string section) => $"/methodology#{section}";

    // The old site's files by their own names (/terms.html, /index.html): where each is here, or
    // null for any other path.
    public static string? OldFile(string path)
    {
        var m = OldFiles().Match(path);
        return !m.Success ? null : m.Groups[1].Value == "index" ? "/" : $"/{m.Groups[1].Value}";
    }

    [GeneratedRegex(@"^/(club|player|league|country|nation)/")]
    private static partial Regex OwnPage();

    [GeneratedRegex(@"^/(index|methodology|terms|privacy)\.html$")]
    private static partial Regex OldFiles();
}
