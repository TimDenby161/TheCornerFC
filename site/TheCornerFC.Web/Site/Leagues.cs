using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// Leagues and the clubs tables on league and country pages (web/src/lib/league.ts and
// web/src/lib/server/league.ts).
public static class Leagues
{
    // clubs playing their league football in this competition this season, best rated first
    public static List<Club> LeagueClubs(List<Club> all, int lid) => all.Where(r => r.InLeague && r.League == lid).OrderByDescending(r => r.Lt).ToList();
    public static double? AvgRating(List<Club> rows) => rows.Count > 0 ? rows.Sum(r => r.Lt) / rows.Count : null;

    public sealed record Average(int Lid, string Name, string Country, int Clubs, double Lt, double Current, int Trend);

    // Every league with rated clubs this season, with the averages of their ratings
    public static List<Average> Averages(SiteDoc site, List<Club> all) =>
        site.Competitions.Where(kv => kv.Value.Type == "League").SelectMany(kv =>
        {
            var clubs = LeagueClubs(all, int.Parse(kv.Key));
            if (clubs.Count == 0) return [];
            double lt = clubs.Sum(c => c.Lt) / clubs.Count, current = clubs.Sum(c => c.Current) / clubs.Count;
            return new[] { new Average(int.Parse(kv.Key), kv.Value.Name, kv.Value.Country, clubs.Count, lt, current, Js.RoundInt(current) - Js.RoundInt(lt)) };
        }).ToList();

    // ---- Sortable tables: a column's first click sorts it best first (dir 1 = ascending), a
    // second reverses. Blanks last; ties keep the table's own order.
    public sealed record Col<T>(int Dir, Func<T, IComparable?> Val);
    public sealed record Sort(string Key, int Dir);

    public static Sort PickSort<T>(IReadOnlyDictionary<string, Col<T>> cols, string def, string? key, bool reversed)
    {
        var k = key is not null && cols.ContainsKey(key) ? key : def;
        return new(k, reversed ? -cols[k].Dir : cols[k].Dir);
    }

    public static List<T> SortRows<T>(IEnumerable<T> rows, Sort s, IReadOnlyDictionary<string, Col<T>> cols)
    {
        var val = cols[s.Key].Val;
        return rows.Select((r, i) => (r, i)).OrderBy(x => x, Comparer<(T r, int i)>.Create((a, b) =>
        {
            IComparable? x = val(a.r), y = val(b.r);
            if (x is null || y is null) return x is null && y is null ? a.i - b.i : x is null ? 1 : -1;
            var c = x is string xs ? Js.Compare.Compare(xs, (string)y) : x.CompareTo(y);
            return c * s.Dir is var d and not 0 ? Math.Sign(d) : a.i - b.i;
        })).Select(x => x.r).ToList();
    }

    // A row of the clubs table on league and country pages: a club's ratings with its Baseline rank
    // in the list (which stays whatever the table is sorted by)
    public sealed record RatingRow(int I, int Team, string Name, int? Pos, int Played, (int League, string Name)? Meta,
        double Lt, int LtTier, double Current, int CurrentTier, int Trend, double? Form);

    public static Func<List<Club>, Func<Club, int?>?, Func<Club, (int, string)?>?, List<RatingRow>> RatingRows(List<Club> all, Func<int, string> name)
    {
        var ltTier = Clubs.Tiers(all, "lt");
        var currentTier = Clubs.Tiers(all, "current");
        return (rows, pos, meta) => rows.Select((r, i) => new RatingRow(i + 1, r.Team, name(r.Team), pos?.Invoke(r), r.Played, meta?.Invoke(r),
            r.Lt, ltTier(r.Lt), r.Current, currentTier(r.Current), r.Trend, r.Form)).ToList();
    }

    public static readonly IReadOnlyDictionary<string, Col<RatingRow>> StrengthCols = new Dictionary<string, Col<RatingRow>>
    {
        ["rank"] = new(1, r => r.I), ["club"] = new(1, r => r.Name), ["pos"] = new(1, r => r.Pos),
        ["played"] = new(-1, r => r.Played), ["lt"] = new(-1, r => r.Lt), ["trend"] = new(-1, r => r.Trend),
        ["current"] = new(-1, r => r.Current), ["form"] = new(-1, r => r.Form),
    };

    // The clubs in a competition that have a rating: this season's league members plus anyone in
    // its table (or, with no table yet, its fixtures), strongest first by Baseline Strength
    public static List<Club> LeagueRanked(List<Club> all, int lid, List<TableRow> table, List<Fixture> fixtures)
    {
        var ids = new List<int>();
        void Add(int t) { if (!ids.Contains(t)) ids.Add(t); }
        foreach (var r in table) Add(r.Team);
        foreach (var c in LeagueClubs(all, lid)) Add(c.Team);
        if (table.Count == 0) foreach (var f in fixtures) { Add(f.Home); Add(f.Away); }
        var byTeam = all.ToDictionary(c => c.Team);
        return ids.Where(byTeam.ContainsKey).Select(t => byTeam[t]).OrderByDescending(c => c.Lt).ToList();
    }

    // ---- A league table's zones (promotion, Europe, relegation ...), from the notes on its rows:
    // each note's class, in the order the notes first appear
    public static List<(string Text, string Cls)> Zones(IEnumerable<string?> descriptions)
    {
        var zones = new List<(string, string)>();
        int next = 0, releg = 0;
        foreach (var d in descriptions)
        {
            if (string.IsNullOrEmpty(d) || zones.Any(z => z.Item1 == d)) continue;
            zones.Add((d, d.Contains("relegation", StringComparison.OrdinalIgnoreCase) ? (releg++ > 0 ? "zone-down2" : "zone-down") : $"zone-{Math.Min(next++, 4)}"));
        }
        return zones;
    }
    public static string ZoneOf(List<(string Text, string Cls)> zones, string? description) =>
        description is null ? "" : zones.FirstOrDefault(z => z.Text == description).Cls ?? "";

    // points from a form string, newest first ("WDL" = 4)
    public static int? FormPoints(string? form) => string.IsNullOrEmpty(form) ? null : form.Sum(c => c switch { 'W' => 3, 'D' => 1, _ => 0 });

    // "Round 6" for "Regular Season - 6"
    public static string RoundLabel(string? r) => System.Text.RegularExpressions.Regex.Replace(r ?? "", @"^Regular Season - (\d+)$", "Round $1");

    // ---- A league's own matches tab: its rounds in the order they are first played, and the one
    // to open on (the round with the next fixture, else the last)
    public static readonly HashSet<string> Finished = ["FT", "AET", "PEN", "AWD", "WO"];
    public static readonly HashSet<string> Live = ["1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"];
    static readonly HashSet<string> Off = ["CANC", "PST", "ABD"];

    public static (List<string> Rounds, string? Open) Rounds(List<Fixture> fixtures)
    {
        var rounds = fixtures.Select(f => f.Round ?? "").Distinct().ToList();
        var next = fixtures.FirstOrDefault(f => !Finished.Contains(f.Status) && !Off.Contains(f.Status));
        return (rounds, next is not null ? next.Round ?? "" : rounds.LastOrDefault());
    }
    public static string? OffText(string status) => status switch { "PST" => "Postponed", "CANC" => "Cancelled", "ABD" => "Abandoned", _ => null };

    // a chance as the projected table shows it
    public static string ChanceText(double p) => p <= 0 ? "–" : p < 0.005 ? "<1%" : p > 0.995 && p < 1 ? ">99%" : $"{Js.RoundInt(p * 100)}%";
}
