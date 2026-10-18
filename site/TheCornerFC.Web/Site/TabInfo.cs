using System.Text.Json;

namespace TheCornerFC.Web.Site;

// Each section's line of introduction and what its figures mean (web/src/lib/tabInfo.json, read
// by both sites). `More`: the part of the methodology page that explains it.
public sealed record TabInfo(string Intro, string More, IReadOnlyList<string[]> Key)
{
    public static readonly IReadOnlyDictionary<string, TabInfo> All = Load();

    static Dictionary<string, TabInfo> Load()
    {
        using var file = typeof(TabInfo).Assembly.GetManifestResourceStream("tabInfo.json")
            ?? throw new InvalidOperationException("tabInfo.json is not built in");
        return JsonSerializer.Deserialize<Dictionary<string, TabInfo>>(file, Data.Database.Json)!;
    }
}

// A page's name over it, with its section's intro and key (the Svelte site's tabHead)
public sealed record TabHead(string Title, TabInfo Info)
{
    public static TabHead For(string title, string tab) => new(title, TabInfo.All[tab]);
}
