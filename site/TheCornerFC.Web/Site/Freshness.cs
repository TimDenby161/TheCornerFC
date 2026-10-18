using System.Text.Json.Serialization;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// At the foot of every page: when each source of its data was last fetched, and the match model
// it was made by (web/src/routes/(app)/+layout.server.ts). From the shared `site` document.
public sealed record Freshness(IReadOnlyList<(string Label, DateTimeOffset At, string Tip)> Items, Freshness.ModelVersion? Model)
{
    public static readonly Freshness None = new([], null);

    public static async Task<Freshness> Read(Database db)
    {
        SiteDoc site;
        try { site = await db.KeptDoc<SiteDoc>("site"); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException) { return None; }
        var f = site.Freshness ?? new Sources(null, null, null, null);
        (string, DateTimeOffset?, string)[] all =
        [
            ("Data updated", site.GeneratedAt, "When this site's data was last exported"),
            ("Predictions updated", f.Predictions, "Latest match prediction written"),
            ("Injuries updated", f.Injuries, "Latest injury and suspension list fetched"),
            ("Odds last seen", f.Odds, "Latest bookmaker prices fetched"),
        ];
        return new(all.Where(x => x.Item2 is not null).Select(x => (x.Item1, x.Item2!.Value, x.Item3)).ToList(), f.Model);
    }

    public sealed record SiteDoc([property: JsonPropertyName("generated_at")] DateTimeOffset? GeneratedAt, Sources? Freshness);
    public sealed record Sources(DateTimeOffset? Predictions, DateTimeOffset? Injuries, DateTimeOffset? Odds, ModelVersion? Model);
    public sealed record ModelVersion(string Name, string? Code);
}
