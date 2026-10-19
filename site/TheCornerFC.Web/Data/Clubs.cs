using System.Text.Json;

namespace TheCornerFC.Web.Data;

// One club's row of the `rankings` document (web/src/lib/rankings.ts). Trend: Current Strength
// less Baseline Strength as shown, so the sum adds up.
public sealed record Club(int Team, int League, double Current, double St, double Lt, int Played, double? Form, bool InLeague,
    double? Attack, double? Defence, double? Home, double? Away)
{
    public int Trend => Site.Js.RoundInt(Current) - Site.Js.RoundInt(Lt);

    public double? Value(string key) => key switch
    {
        "lt" => Lt, "current" => Current, "trend" => Trend, "form" => Form, _ => throw new ArgumentException(key),
    };
}

// A club's place by Current Strength among every ranked club, and among the clubs in its league
public sealed record Place(int World, int? Dom, int? DomOf);

public static class Clubs
{
    public static List<Club> From(Rankings doc)
    {
        int At(string f) => Array.IndexOf(doc.Fields, f);
        int team = At("team"), league = At("league"), current = At("current"), st = At("st"), lt = At("lt"), played = At("played"),
            form = At("form"), inLeague = At("in_league"), attack = At("attack"), defence = At("defence"), home = At("home"), away = At("away");
        static double? N(JsonElement[] r, int i) => i >= 0 && r[i].ValueKind == JsonValueKind.Number ? r[i].GetDouble() : null;
        return doc.Rows.Select(r => new Club((int)N(r, team)!, (int)(N(r, league) ?? 0), N(r, current) ?? 0, N(r, st) ?? 0, N(r, lt) ?? 0,
            (int)(N(r, played) ?? 0), N(r, form), N(r, inLeague) is > 0, N(r, attack), N(r, defence), N(r, home), N(r, away))).ToList();
    }

    // 1 + how many values are greater: equal values share a place (`sorted` highest first)
    static int PlaceIn(List<double> sorted, double v)
    {
        int lo = 0, hi = sorted.Count;
        while (lo < hi)
        {
            var m = (lo + hi) >> 1;
            if (sorted[m] > v) lo = m + 1; else hi = m;
        }
        return lo + 1;
    }

    public static Dictionary<int, Place> Places(List<Club> all)
    {
        var world = all.Select(c => c.Current).OrderByDescending(x => x).ToList();
        var by = all.Where(c => c.InLeague).GroupBy(c => c.League).ToDictionary(g => g.Key, g => g.Select(c => c.Current).OrderByDescending(x => x).ToList());
        var places = new Dictionary<int, Place>();
        foreach (var c in all)
        {
            var lg = c.InLeague ? by[c.League] : null;
            places[c.Team] = new(PlaceIn(world, c.Current), lg is null ? null : PlaceIn(lg, c.Current), lg?.Count);
        }
        return places;
    }

    // The badge colour for a value: its place among every ranked club on that measure. Top 5% is 4
    // (green), top 20% 3 (amber), top half 2 (orange), the rest 1 (red).
    public static Func<double, int> Tiers(List<Club> all, string key)
    {
        var sorted = all.Select(c => key == "lt" ? c.Lt : c.Current).OrderByDescending(x => x).ToList();
        return v =>
        {
            var share = (double)PlaceIn(sorted, v) / sorted.Count;
            return share <= 0.05 ? 4 : share <= 0.2 ? 3 : share <= 0.5 ? 2 : 1;
        };
    }
}
