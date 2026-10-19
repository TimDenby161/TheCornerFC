using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// A player's page, worked out from his row in the Players list and his own file
// (web/src/lib/player.ts)
public static class PlayerPage
{
    // ---- A season's lines added up, all his clubs (null where no line has the stat)
    public sealed record SeasonSum(int? Apps, int? Starts, int? Minutes, int? Goals, int? Assists, int? Yellow, int? Red)
    {
        public int? this[string k] => k switch { "apps" => Apps, "starts" => Starts, "minutes" => Minutes, "goals" => Goals, "assists" => Assists, "yellow" => Yellow, _ => Red };
    }
    public static SeasonSum? Sum(List<SeasonLine> rows)
    {
        if (rows.Count == 0) return null;
        static int? S(IEnumerable<int?> vs) { var known = vs.Where(v => v is not null).ToList(); return known.Count > 0 ? known.Sum() : null; }
        return new(S(rows.Select(r => (int?)r.Apps)), S(rows.Select(r => r.Starts)), S(rows.Select(r => (int?)r.Minutes)), S(rows.Select(r => r.Goals)),
            S(rows.Select(r => r.Assists)), S(rows.Select(r => r.Yellow)), S(rows.Select(r => r.Red)));
    }
    // a stat as the Stats tab shows it: the total, or per 90 minutes
    public static string StatText(SeasonSum s, string k, bool per90) =>
        s[k] is not { } v ? "–" : per90 && s.Minutes is > 0 ? Js.ToFixed(v * 90.0 / s.Minutes.Value, 2) : Js.Num(v);

    // ---- Positions
    static readonly HashSet<string> NoRole = ["G", "D", "M", "F", "SUB"]; // a start without a line-up position, or off the bench
    public static readonly IReadOnlyDictionary<string, string> PosWord = new Dictionary<string, string> { ["G"] = "GK", ["D"] = "DEF", ["M"] = "MID", ["F"] = "FWD", ["SUB"] = "Sub" };

    // The group a season is rated as: the role group with most starting minutes that season (as
    // the model does); starts without a line-up position only if there's nothing else
    public static string? SeasonGroup(List<(string Role, double Minutes)>? list)
    {
        var by = new List<(string G, double M)>();
        void Add(string g, double m) { var k = by.FindIndex(x => x.G == g); if (k < 0) by.Add((g, m)); else by[k] = (g, by[k].M + m); }
        foreach (var (r, m) in list ?? []) if (!NoRole.Contains(r) && Names.GroupOf.TryGetValue(r, out var g)) Add(g, m);
        if (by.Count == 0) foreach (var (r, m) in list ?? []) if (Names.GroupOf.TryGetValue(r, out var g)) Add(g, m);
        return by.Count > 0 ? by.Select((x, i) => (x, i)).OrderByDescending(t => t.x.M).ThenBy(t => t.i).First().x.G : null;
    }

    // shares of his starting minutes (minutes off the bench have no position and aren't counted;
    // positions under 3% grouped as "other")
    public sealed record Share(string Label, int Pct, bool Other);
    public static List<Share> PositionShares(List<(string Role, double Minutes)> list)
    {
        list = list.Where(x => x.Role != "SUB").ToList();
        var total = list.Sum(x => x.Minutes);
        if (total == 0) return [];
        var shown = list.Where(x => x.Minutes / total >= 0.03).ToList();
        var other = total - shown.Sum(x => x.Minutes);
        var o = shown.Select(x => new Share(PosWord.GetValueOrDefault(x.Role) ?? x.Role, Js.RoundInt(100 * x.Minutes / total), false)).ToList();
        if (other > 0) o.Add(new Share("other", Js.RoundInt(100 * other / total), true));
        return o;
    }

    // His positions in a row, most played first (his share of starting minutes over 12 months,
    // else all time; then best rank): his rank in each role group he has one in, and his share
    // there. Keepers have no position ranks: their keeper rank is their rank.
    static readonly string[] Groups = ["GK", "CB", "FB", "WB", "DM", "CM", "AM", "W", "ST"];
    public sealed record Chip(string Group, string Name, double Rank, int Pct, bool Main);
    public static List<Chip> PositionChips(string? position, double? rank, IReadOnlyDictionary<string, double>? ranks, Dictionary<string, System.Text.Json.JsonElement[][]>? positions)
    {
        var group = position is not null ? Names.GroupOf.GetValueOrDefault(position) : null;
        double? RankIn(string g) => ranks?.TryGetValue(g, out var r) == true ? r : g == group ? rank : null;
        var ranked = Groups.Where(g => RankIn(g) is not null).ToList();
        var rows = PlayerFiles.Roles(positions?.GetValueOrDefault("12m") ?? positions?.GetValueOrDefault("all")).Where(x => x.Role != "SUB").ToList();
        var total = rows.Sum(x => x.Minutes);
        var mins = new Dictionary<string, double>();
        foreach (var (r, m) in rows) if (Names.GroupOf.TryGetValue(r, out var g)) mins[g] = mins.GetValueOrDefault(g) + m;
        return ranked.OrderByDescending(g => mins.GetValueOrDefault(g)).ThenByDescending(g => RankIn(g)!.Value)
            .Select(g => new Chip(g, Names.GroupSingle[g], RankIn(g)!.Value, total != 0 ? Js.RoundInt(100 * mins.GetValueOrDefault(g) / total) : 0, g == group)).ToList();
    }

    // ---- The season rank chart (RankChart.svelte): points oldest first, laid out in a box of the
    // given width. The server draws it 640 wide; the page's React chart redraws it at its real width.
    public sealed record ChartPoint(string Label, string Season, double V, bool Est);
    public static List<double> NiceTicks(double lo, double hi, int count)
    {
        var step0 = (hi - lo) / count;
        var mag = Math.Pow(10, Math.Floor(Math.Log10(step0)));
        var step = new[] { 1, 2, 2.5, 5, 10 }.Select(m => m * mag).FirstOrDefault(s => s >= step0, step0);
        var o = new List<double>();
        for (var v = Math.Ceiling(lo / step) * step; v <= hi; v += step) o.Add(v);
        return o;
    }
    public sealed record Chart(double W, double H, double L, double R, double T, double B, Func<int, double> X, Func<double, double> Y,
        List<double> Ticks, Func<int, bool> ShowLabel, string Path);
    public static Chart Layout(List<ChartPoint> pts, double width)
    {
        double W = Math.Max(260, width), H = 180, L = 30, R = 14, T = 20, B = 22, IN = 12;
        double lo = pts.Min(d => d.V), hi = pts.Max(d => d.V);
        var pad = Math.Max(3, (hi - lo) * 0.15);
        lo = Math.Max(0, lo - pad);
        hi = Math.Min(100, hi + pad);
        double X(int i) => L + IN + (pts.Count == 1 ? 0.5 : (double)i / (pts.Count - 1)) * (W - L - R - 2 * IN);
        double Y(double v) => T + (1 - (v - lo) / (hi - lo is var span && span != 0 ? span : 1)) * (H - T - B);
        var every = Math.Max(1, (int)Math.Ceiling(pts.Count * 46 / (W - L - R))); // x labels that fit
        return new(W, H, L, R, T, B, X, Y, NiceTicks(lo, hi, 4),
            i => i == pts.Count - 1 || (i % every == 0 && pts.Count - 1 - i >= every),
            string.Concat(pts.Select((d, i) => $"{(i > 0 ? "L" : "M")}{Js.ToFixed(X(i), 1)},{Js.ToFixed(Y(d.V), 1)}")));
    }

    // The chart as SVG, `width` wide (RankChart.svelte's markup without the hover parts)
    public static string ChartSvg(List<ChartPoint> pts, string name, double width)
    {
        static string E(string t) => System.Net.WebUtility.HtmlEncode(t);
        var c = Layout(pts, width);
        var sb = new System.Text.StringBuilder();
        sb.Append($"<svg viewBox=\"0 0 {c.W} {c.H}\" height=\"{c.H}\" role=\"img\" aria-label=\"{E(name)} rank, {Js.RoundInt(pts[0].V)} to {Js.RoundInt(pts[^1].V)}\">");
        sb.Append("<g class=\"chart-grid\">");
        foreach (var v in c.Ticks) sb.Append($"<line x1=\"{c.L}\" x2=\"{c.W - c.R}\" y1=\"{Js.ToFixed(c.Y(v), 1)}\" y2=\"{Js.ToFixed(c.Y(v), 1)}\"></line>");
        sb.Append("</g><g class=\"chart-axis\">");
        foreach (var v in c.Ticks) sb.Append($"<text x=\"{c.L - 6}\" y=\"{Js.ToFixed(c.Y(v) + 3, 1)}\" text-anchor=\"end\">{Js.RoundInt(v)}</text>");
        for (var i = 0; i < pts.Count; i++)
            if (c.ShowLabel(i)) sb.Append($"<text x=\"{Js.ToFixed(c.X(i), 1)}\" y=\"{c.H - 6}\" text-anchor=\"middle\">{E(pts[i].Label)}</text>");
        sb.Append($"</g><path class=\"chart-line\" d=\"{c.Path}\"></path>");
        if (pts.Count <= 8)
            for (var i = 0; i < pts.Count; i++)
                sb.Append($"<circle class=\"season-dot{(pts[i].Est ? " est" : "")}\" cx=\"{Js.ToFixed(c.X(i), 1)}\" cy=\"{Js.ToFixed(c.Y(pts[i].V), 1)}\" r=\"4.5\"></circle>")
                  .Append($"<text class=\"season-label\" x=\"{Js.ToFixed(c.X(i), 1)}\" y=\"{Js.ToFixed(c.Y(pts[i].V) - 9, 1)}\" text-anchor=\"middle\">{Js.RoundInt(pts[i].V)}</text>");
        return sb.Append("</svg>").ToString();
    }
}
