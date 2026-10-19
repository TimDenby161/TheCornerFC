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
}
