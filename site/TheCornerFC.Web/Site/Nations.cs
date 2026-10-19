using System.Text.Json.Serialization;

namespace TheCornerFC.Web.Site;

// The national team ranking ("nations": the club Elo run over every men's international since
// 1872; web/src/lib/nation.ts)
public sealed record NationsDoc(
    [property: JsonPropertyName("latest_match")] string LatestMatch, int Matches,
    [property: JsonPropertyName("from_api")] int? FromApi,
    Dictionary<string, string[]>? Aliases, List<NationsDoc.Nation> Nations)
{
    public sealed record Nation(string Name, string Flag, string? Confed, double Current,
        [property: JsonPropertyName("year_ago")] double? YearAgo, int Played, int W, int D, int L, Last Last,
        // the national team's own file (nations/<id>), where the feed has its internationals
        [property: JsonPropertyName("team_id")] int? TeamId = null);
    public sealed record Last(string Date, string Opp, int Gf, int Ga, string Comp);

    public static readonly IReadOnlyList<string> Confeds = ["UEFA", "CONMEBOL", "CONCACAF", "CAF", "AFC", "OFC"];

    // A rating's place among the nations, as the badge colours: top 5% green, 20% amber, half orange
    public int Tier(double v)
    {
        var share = (double)(Nations.Count(n => n.Current > v) + 1) / Nations.Count;
        return share <= 0.05 ? 4 : share <= 0.2 ? 3 : share <= 0.5 ? 2 : 1;
    }

    static readonly string[] Months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    // "19 Sep" for "2026-09-19" (a day is the same for every visitor; web/src/lib/club.ts)
    public static string ShortDate(string day) => $"{int.Parse(day[8..10])} {Months[int.Parse(day[5..7]) - 1]}";
}
