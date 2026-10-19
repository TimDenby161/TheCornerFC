using System.Text.Json;

namespace TheCornerFC.Web.Site;

// Names, short forms and groupings the pages share (web/src/lib/names.json, read by both sites;
// web/src/lib/names.ts has the same).
public static class Names
{
    sealed record File(
        Dictionary<int, string> SHORT_NAMES, Dictionary<int, string> CLUB_SHORT, Dictionary<string, string> FLAG_CODES,
        string[] COUNTRY_FIRST, string[] REGIONS, int[] EURO_CUPS, int[] DOMESTIC_CUPS, string[] CONTINENTS,
        Dictionary<string, string> CLUB_ALIASES, Dictionary<int, string> LEAGUE_ALIASES, Dictionary<string, string> COUNTRY_ALIASES,
        Comp[] PRIMARY_COMPS, Comp[] TABLE_COMPS, Dictionary<string, string[]> REGION_LISTS, int[] GROUP_ORDER,
        JsonElement[][] PITCH_SPOTS, Dictionary<string, string> GROUP_OF, string[] SEO_BOTS, Dictionary<string, string> GROUP_SINGLE);
    public sealed record Comp(string Id, string Label, int[]? Ids);

    static readonly File Read = Load();
    static File Load()
    {
        using var s = typeof(Names).Assembly.GetManifestResourceStream("names.json") ?? throw new InvalidOperationException("names.json is not built in");
        return JsonSerializer.Deserialize<File>(s)!;
    }

    public static IReadOnlyDictionary<int, string> ShortNames => Read.SHORT_NAMES;
    public static IReadOnlyDictionary<int, string> ClubShort => Read.CLUB_SHORT;
    public static IReadOnlyDictionary<string, string> FlagCodes => Read.FLAG_CODES;
    public static IReadOnlyList<string> CountryFirst => Read.COUNTRY_FIRST;
    public static IReadOnlyList<string> Regions => Read.REGIONS;
    public static IReadOnlyList<int> EuroCups => Read.EURO_CUPS;
    public static IReadOnlyList<int> DomesticCups => Read.DOMESTIC_CUPS;
    public static IReadOnlyList<string> Continents => Read.CONTINENTS;
    public static IReadOnlyDictionary<string, string> ClubAliases => Read.CLUB_ALIASES;
    public static IReadOnlyDictionary<int, string> LeagueAliases => Read.LEAGUE_ALIASES;
    public static IReadOnlyDictionary<string, string> CountryAliases => Read.COUNTRY_ALIASES;
    public static IReadOnlyList<Comp> PrimaryComps => Read.PRIMARY_COMPS;
    public static IReadOnlyList<Comp> TableComps => Read.TABLE_COMPS;
    // the order competitions are listed in where several are shown together
    public static IReadOnlyList<int> GroupOrder => Read.GROUP_ORDER;
    // a pitch of positions, attacking upwards: [position, x %, y %]
    public static readonly IReadOnlyList<(string Role, double X, double Y)> PitchSpots =
        Read.PITCH_SPOTS.Select(s => (s[0].GetString()!, s[1].GetDouble(), s[2].GetDouble())).ToList();
    // the role group each position is rated in (as positions.py)
    public static IReadOnlyDictionary<string, string> GroupOf => Read.GROUP_OF;
    // a role group in words ("centre-back")
    public static IReadOnlyDictionary<string, string> GroupSingle => Read.GROUP_SINGLE;
    // SEO tools' crawlers, asked by robots.txt to stay away (task T-039): they send no visitors
    public static IReadOnlyList<string> SeoBots => Read.SEO_BOTS;

    static readonly Dictionary<string, string> RegionOfCountry =
        Read.REGION_LISTS.SelectMany(kv => kv.Value.Select(c => (c, kv.Key))).GroupBy(x => x.c).ToDictionary(g => g.Key, g => g.Last().Key);

    // Every country outside the big five goes under a region; anything not listed is "Rest of Europe"
    public static string RegionOf(string country) => RegionOfCountry.GetValueOrDefault(country, "Rest of Europe");
    // chip labels: "N. America", "S. America"
    public static string RegionLabel(string r) => r is "North America" or "South America" ? $"{r[0]}. America" : r;
    public static string ContinentOf(string country)
    {
        var region = CountryFirst.Contains(country) ? "Europe" : RegionOf(country);
        return Continents.Contains(region) ? region : "Europe";
    }
}
