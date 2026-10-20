using System.Globalization;
using System.Net;
using System.Text;

namespace TheCornerFC.Web.Site;

// One or more lines over the same run of labels (ChangeLines.svelte and web/src/lib/changes.ts's
// scale and ticks): drawn 640 wide and scaled to its box; every position is an SVG attribute (the
// security policy allows no inline styles)
public static class ChangeLines
{
    public sealed record Point(string X, double Value, string? Note = null);
    public sealed record Series(string Name, string Cls, List<Point> Points);

    public static Func<double, double> Scale((double Lo, double Hi) domain, (double From, double To) range)
    {
        var span = domain.Hi - domain.Lo is var s && s != 0 ? s : 1;
        return v => range.From + (v - domain.Lo) / span * (range.To - range.From);
    }

    // round steps for an axis, about `about` of them
    public static List<double> Ticks(double lo, double hi, int about = 4)
    {
        var span = hi - lo;
        if (!(span > 0)) return [lo];
        var raw = span / about;
        var mag = Math.Pow(10, Math.Floor(Math.Log10(raw)));
        var step = new[] { 1, 2, 5, 10 }.Select(m => m * mag).First(s => s >= raw);
        var list = new List<double>();
        for (var v = Math.Ceiling(lo / step) * step; v <= hi + step * 1e-9; v += step)
            list.Add(double.Parse(Js.ToFixed(v, 10), CultureInfo.InvariantCulture));
        return list;
    }

    static string F1(double v) => Js.ToFixed(v, 1);
    static string E(string s) => WebUtility.HtmlEncode(s);

    public static string Svg(List<Series> series, string label, int places = 3, bool zero = false)
    {
        const int W = 640, H = 240, L = 58, R = 14, T = 12, B = 30;
        var xs = series.SelectMany(s => s.Points.Select(p => p.X)).Distinct().OrderBy(x => x, StringComparer.Ordinal).ToList();
        var values = series.SelectMany(s => s.Points.Select(p => p.Value)).Concat(zero ? [0.0] : []).ToList();
        double lo = values.Min(), hi = values.Max();
        var pad = (hi - lo is var d && d != 0 ? d : Math.Abs(hi) is var a && a != 0 ? a : 1) * 0.08;
        var y = Scale((lo - pad, hi + pad), (H - B, T));
        var toX = Scale((0, xs.Count - 1), (L, W - R));
        double X(string labelX) => xs.Count < 2 ? (L + W - R) / 2.0 : toX(xs.IndexOf(labelX));
        var marks = Ticks(lo - pad, hi + pad);
        // about six labels along the foot, however many points there are
        var every = Math.Max(1, (int)Math.Ceiling(xs.Count / 6.0));
        var svg = new StringBuilder();
        svg.Append($"<figure class=\"mc-chart\"><svg viewBox=\"0 0 {W} {H}\" role=\"img\" aria-label=\"{E(label)}\">");
        svg.Append("<g class=\"chart-grid\">");
        foreach (var v in marks) svg.Append($"<line x1=\"{L}\" x2=\"{W - R}\" y1=\"{F1(y(v))}\" y2=\"{F1(y(v))}\" />");
        svg.Append("</g><g class=\"chart-axis\">");
        foreach (var v in marks) svg.Append($"<text x=\"{L - 6}\" y=\"{F1(y(v) + 3)}\" text-anchor=\"end\">{Js.ToFixed(v, places)}</text>");
        for (var i = 0; i < xs.Count; i++) if (i % every == 0) svg.Append($"<text x=\"{F1(X(xs[i]))}\" y=\"{H - 8}\" text-anchor=\"middle\">{E(xs[i])}</text>");
        svg.Append("</g>");
        if (zero) svg.Append($"<line class=\"mc-zero\" x1=\"{L}\" x2=\"{W - R}\" y1=\"{F1(y(0))}\" y2=\"{F1(y(0))}\" />");
        foreach (var s in series)
        {
            var path = string.Concat(s.Points.Select((p, i) => $"{(i > 0 ? "L" : "M")}{F1(X(p.X))},{F1(y(p.Value))}"));
            svg.Append($"<path class=\"mc-line {E(s.Cls)}\" d=\"{path}\" />");
            if (s.Points.Count <= 24)
                foreach (var p in s.Points)
                    svg.Append($"<circle class=\"mc-dot {E(s.Cls)}\" cx=\"{F1(X(p.X))}\" cy=\"{F1(y(p.Value))}\" r=\"3.5\"><title>{E(p.X)}: {Js.ToFixed(p.Value, places + 1)}{(p.Note is { } n ? $" · {E(n)}" : "")}</title></circle>");
        }
        svg.Append("</svg><figcaption class=\"mc-legend\">");
        foreach (var s in series) svg.Append($"<span><i class=\"mc-key {E(s.Cls)}\" aria-hidden=\"true\"></i>{E(s.Name)}</span>");
        svg.Append("</figcaption></figure>");
        return svg.ToString();
    }
}
