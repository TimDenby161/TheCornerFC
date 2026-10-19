using System.Text.Json.Serialization;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Data;

// The "site" row: names for every competition and club (web/src/lib/site.ts)
public sealed record Competition(string Name, string Country, string Type);
public sealed record SiteDoc(
    [property: JsonPropertyName("generated_at")] string GeneratedAt,
    Dictionary<string, Competition> Competitions,
    Dictionary<string, string> Teams,
    [property: JsonPropertyName("nation_pages")] Dictionary<string, string>? NationPages,
    // when each source of the data was last fetched, and the match model it was made by
    Freshness.Sources? Freshness,
    // the order of a match's row and of a player's, as site_matches and site_players give them
    [property: JsonPropertyName("match_fields")] string[]? MatchFields = null,
    [property: JsonPropertyName("player_fields")] string[]? PlayerFields = null,
    [property: JsonPropertyName("player_season_fields")] string[]? PlayerSeasonFields = null)
{
    public Competition? Comp(int id) => Competitions.GetValueOrDefault(id.ToString());
    public string TeamName(int id) => Teams.GetValueOrDefault(id.ToString()) ?? $"Team {id}";
    public string LeagueShort(int id) => Names.ShortNames.GetValueOrDefault(id) ?? Comp(id)?.Name ?? "";
    public string LeagueName(int id) => Names.ShortNames.GetValueOrDefault(id) ?? Comp(id)?.Name ?? $"Competition {id}";
    public static string CountryName(Competition c) => c.Country.Replace('-', ' ');
}
