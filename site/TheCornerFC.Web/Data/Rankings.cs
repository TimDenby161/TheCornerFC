using System.Text.Json;
using System.Text.Json.Serialization;

namespace TheCornerFC.Web.Data;

// The `rankings` document: one row per club, its values in the order `fields` names them
// (web/src/lib/rankings.ts). The rest of what the club lists need comes with step 3 of the rebuild.
public sealed record Rankings(string[] Fields, [property: JsonPropertyName("rankings")] JsonElement[][] Rows)
{
    public IEnumerable<(int Team, int? League)> Clubs()
    {
        int team = Array.IndexOf(Fields, "team"), league = Array.IndexOf(Fields, "league");
        return Rows.Select(r => (r[team].GetInt32(), r[league].ValueKind == JsonValueKind.Number ? r[league].GetInt32() : (int?)null));
    }
}
