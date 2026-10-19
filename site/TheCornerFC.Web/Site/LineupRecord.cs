using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// The reconstructed history, added up in the database (site_lineup_history): the model re-run on
// every past match, in the same shape as the live record's summary
// (a range with no line-ups comes back with its sums empty: read as nothing)
public sealed record HistorySummaryDoc(bool? Available, bool? Any, int[]? Leagues, Dictionary<string, int?>? Scope,
    int? Total, int? Correct, int? Perfect, [property: JsonPropertyName("roles_right")] int? RolesRight, [property: JsonPropertyName("roles_known")] int? RolesKnown,
    int? Matches, string? First, string? Last, Dictionary<string, int?>? Counts, string? Step, JsonElement[][]? Trend, int?[]? Lines,
    double?[][]? Comps, double?[][]? Clubs, int[][]? Missed, int[][]? Wrong, [property: JsonPropertyName("missed_total")] int? MissedTotal,
    JsonElement[][]? Rows, Dictionary<string, string>? Teams, Dictionary<string, string>? Players);

// The line-up record (web/src/lib/lineupRecord.ts): every XI the model predicted before the team
// sheet came out, checked against the one that started ("lineups": one row per team line-up,
// totalled here), or the reconstructed history (totalled in the database). Both end up as the same
// summary, which is all the page draws from.
public static class LineupRecord
{
    public static readonly string[] Lines = ["Goalkeeper", "Defence", "Midfield", "Attack"];
    static readonly (string Label, double From, double To)[] Horizons = [("Under 1 hour", 0, 1), ("1–6 hours", 1, 6), ("6–24 hours", 6, 24), ("24 hours or more", 24, double.PositiveInfinity)];
    public const int Page = 50;     // line-ups listed per "Show more"
    public const int ClubMin = 3;   // line-ups a club needs for the easiest/hardest lists

    public sealed record LiveRow(int Fixture, string Kickoff, int League, int Team, int Opponent, int Home, int Correct, int RolesRight, int RolesKnown,
        double[] LineCounts, double HoursBefore, int Version, int[] Missed, int[] Wrong, DateTimeOffset Time);
    // [key, line-ups, starters named, perfect XIs, right position, positions known]
    public sealed record Group(int Key, int N, int Correct, int Perfect, int? Right, int? Known);
    public sealed record TrendPoint(string Day, int N, int Correct, int Perfect);
    public sealed record Tally(int Player, int Team, int Times);
    public sealed record Row(string Day, int Team, int Opponent, bool Home, int League, int Correct, int[] Missed);
    public sealed class Summary
    {
        public bool Any; public int N, Correct, Perfect, RolesRight, Matches; public int? RolesKnown; public int Excluded;
        public string? First, Last;
        public int[] Counts = [];
        public string Step = "day";
        public List<TrendPoint> Trend = [];
        public double[] Lines = [];
        public List<(string Label, int N, int Correct, int Perfect)>? Timing;
        public List<Group> Comps = [], Clubs = [];
        public List<Tally> Missed = [], Wrong = [];
        public int MissedTotal;
        public List<Group>? Versions;
        public List<Row> Rows = [];
    }

    public static List<LiveRow> LiveRows(LiveDoc d) => d.Rows.Select(r =>
    {
        var n = new Named(d.Fields, r);
        JsonElement? At(string f) => Array.IndexOf(d.Fields, f) is var i and >= 0 && i < r.Length ? r[i] : null;
        int[] Ints(string f) => At(f) is { ValueKind: JsonValueKind.Array } a ? a.EnumerateArray().Select(e => e.GetInt32()).ToArray() : [];
        double[] Doubles(string f) => At(f) is { ValueKind: JsonValueKind.Array } a ? a.EnumerateArray().Select(e => e.ValueKind == JsonValueKind.Number ? e.GetDouble() : 0).ToArray() : [];
        var kickoff = n.S("kickoff") ?? "";
        return new LiveRow(n.I("fixture") ?? 0, kickoff, n.I("league") ?? 0, n.I("team") ?? 0, n.I("opponent") ?? 0, n.I("home") ?? 0, n.I("correct") ?? 0,
            n.I("roles_right") ?? 0, n.I("roles_known") ?? 0, Doubles("lines"), n.D("hours_before") ?? 0, n.I("version") ?? 0, Ints("missed"), Ints("wrong"),
            DateTimeOffset.Parse(kickoff, CultureInfo.InvariantCulture));
    }).ToList();

    // the line-ups by a key, in the order the keys first come: [key, line-ups, named, perfect, right position, positions known]
    static List<(T Key, int N, int Correct, int Perfect, int Right, int Known)> Groups<T>(IEnumerable<LiveRow> list, Func<LiveRow, T> key) where T : notnull
    {
        var order = new List<T>();
        var by = new Dictionary<T, (int N, int Correct, int Perfect, int Right, int Known)>();
        foreach (var r in list)
        {
            var k = key(r);
            if (!by.TryGetValue(k, out var g)) { order.Add(k); g = default; }
            by[k] = (g.N + 1, g.Correct + r.Correct, g.Perfect + (r.Correct == 11 ? 1 : 0), g.Right + r.RolesRight, g.Known + r.RolesKnown);
        }
        return order.Select(k => (k, by[k].N, by[k].Correct, by[k].Perfect, by[k].Right, by[k].Known)).ToList();
    }
    static Group AsGroup((int Key, int N, int Correct, int Perfect, int Right, int Known) g) => new(g.Key, g.N, g.Correct, g.Perfect, g.Right, g.Known);

    // The live record's summary for a range and some competitions. tz: the visitor's time zone, for
    // which day a line-up falls on; shown: how many line-ups to list.
    public static Summary LiveSummary(LiveDoc d, List<LiveRow> all, int? days, List<int>? ids, string tz, double shown, DateTimeOffset now)
    {
        var since = days is { } dd ? now - TimeSpan.FromDays(dd) : DateTimeOffset.MinValue;
        var list = all.Where(r => r.Time >= since && (ids is null || ids.Contains(r.League))).ToList();
        var totals = Groups(list, _ => 0).FirstOrDefault();
        var s = new Summary
        {
            Any = all.Count > 0, N = totals.N, Correct = totals.Correct, Perfect = totals.Perfect, RolesRight = totals.Right, RolesKnown = totals.Known,
            Matches = list.Select(r => r.Fixture).Distinct().Count(), Excluded = d.ExcludedNoOfficialXi ?? 0,
        };
        if (s.N == 0) return s;
        string Day(DateTimeOffset t) => Matchday.LocalDay(t, tz);
        s.First = Day(list[0].Time);
        s.Last = Day(list[^1].Time);
        s.Counts = new int[12];
        foreach (var r in list) s.Counts[r.Correct] += 1;
        // average per day; per week past four weeks, per month past six months
        var span = list[^1].Time - list[0].Time;
        var step = s.Step = span > TimeSpan.FromDays(183) ? "month" : span > TimeSpan.FromDays(28) ? "week" : "day";
        s.Trend = Groups(list, r =>
        {
            var day = Day(r.Time);
            if (step == "week") return Matchday.AddDays(day, -(((int)DateTime.ParseExact(day, "yyyy-MM-dd", CultureInfo.InvariantCulture).DayOfWeek + 6) % 7));
            return step == "month" ? $"{day[..7]}-01" : day;
        }).OrderByDescending(g => g.Key, StringComparer.Ordinal).Select(g => new TrendPoint(g.Key, g.N, g.Correct, g.Perfect)).ToList();
        s.Lines = Enumerable.Range(0, 8).Select(i => { double t = 0; foreach (var r in list) t += i < r.LineCounts.Length ? r.LineCounts[i] : double.NaN; return t; }).ToArray();
        s.Timing = Horizons.Select(h =>
        {
            var g = Groups(list.Where(r => r.HoursBefore >= h.From && r.HoursBefore < h.To), _ => 0).FirstOrDefault();
            return (h.Label, g.N, g.Correct, g.Perfect);
        }).ToList();
        s.Comps = Groups(list, r => r.League).Select(AsGroup).ToList();
        s.Clubs = Groups(list, r => r.Team).Select(AsGroup).ToList();
        List<Tally> Tallies(Func<LiveRow, int[]> field)
        {
            var order = new List<int>();
            var c = new Dictionary<int, (int Team, int Times)>();
            foreach (var r in list)
                foreach (var p in field(r))
                {
                    if (!c.TryGetValue(p, out var x)) { order.Add(p); x = (r.Team, 0); }
                    c[p] = (x.Team, x.Times + 1);
                }
            return order.Where(p => c[p].Times >= 2).Select(p => new Tally(p, c[p].Team, c[p].Times)).ToList();
        }
        s.Missed = Tallies(r => r.Missed);
        s.Wrong = Tallies(r => r.Wrong);
        s.MissedTotal = list.Sum(r => r.Missed.Length);
        s.Versions = Groups(list, r => r.Version).Select(AsGroup).OrderBy(g => g.Key).ToList();
        s.Rows = Enumerable.Reverse(list).Take((int)Math.Max(0, Math.Truncate(shown))).Select(r => new Row(Day(r.Time), r.Team, r.Opponent, r.Home != 0, r.League, r.Correct, r.Missed)).ToList();
        return s;
    }

    // The history's summary: the database's answer, in the same shape
    public static Summary HistorySummary(HistorySummaryDoc d)
    {
        static Group G(double?[] g) => new((int)(g[0] ?? 0), (int)(g[1] ?? 0), (int)(g[2] ?? 0), (int)(g[3] ?? 0),
            g.Length > 4 && g[4] is { } r ? (int)r : null, g.Length > 5 && g[5] is { } k ? (int)k : null);
        return new()
        {
            Any = d.Any == true, N = d.Total ?? 0, Correct = d.Correct ?? 0, Perfect = d.Perfect ?? 0, RolesRight = d.RolesRight ?? 0, RolesKnown = d.RolesKnown, Matches = d.Matches ?? 0,
            First = d.First, Last = d.Last,
            Counts = Enumerable.Range(0, 12).Select(k => d.Counts?.GetValueOrDefault(k.ToString()) ?? 0).ToArray(), Step = d.Step ?? "day",
            Trend = (d.Trend ?? []).Select(t => new TrendPoint(t[0].GetString()!, t[1].GetInt32(), t[2].GetInt32(), t[3].GetInt32())).ToList(),
            Lines = (d.Lines ?? []).Select(x => (double)(x ?? 0)).ToArray(), Comps = (d.Comps ?? []).Select(G).ToList(), Clubs = (d.Clubs ?? []).Select(G).ToList(),
            Missed = (d.Missed ?? []).Select(x => new Tally(x[0], x[1], x[2])).ToList(), Wrong = (d.Wrong ?? []).Select(x => new Tally(x[0], x[1], x[2])).ToList(),
            MissedTotal = d.MissedTotal ?? 0,
            Rows = (d.Rows ?? []).Select(r => new Row(r[0].GetString()!, r[1].GetInt32(), r[2].GetInt32(), r[3].GetInt32() != 0, r[4].GetInt32(), r[5].GetInt32(),
                r[6].EnumerateArray().Select(e => e.GetInt32()).ToArray())).ToList(),
        };
    }

    // the clubs easiest and hardest to predict, among those with enough line-ups scored
    public static (List<Group> Easiest, List<Group> Hardest)? ClubExtremes(List<Group> clubs)
    {
        var ranked = clubs.Where(c => c.N >= ClubMin).Select((c, i) => (c, i))
            .OrderBy(t => t.c, Comparer<Group>.Create((a, b) =>
            {
                var d = (double)b.Correct / b.N - (double)a.Correct / a.N;
                return d != 0 ? Math.Sign(d) : b.N - a.N;
            })).ThenBy(t => t.i).Select(t => t.c).ToList();
        var k = Math.Min(10, ranked.Count / 2);
        return k >= 3 ? (ranked.Take(k).ToList(), Enumerable.Reverse(ranked.TakeLast(k)).ToList()) : null;
    }
    public static string Of11(double x) => $"{Js.ToFixed(x, 1)} of 11";
    public static string ShareText(double a, double? b) => b is { } d && d != 0 ? $"{Js.ToFixed(100 * a / d, 1)}%" : "–";
}
