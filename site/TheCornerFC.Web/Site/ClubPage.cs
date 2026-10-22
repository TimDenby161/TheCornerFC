using System.Text.RegularExpressions;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// A club's page, worked out from its own file (web/src/lib/club.ts and formations.ts)
public static partial class ClubPage
{
    public static char Result(int gf, int ga) => gf > ga ? 'W' : gf == ga ? 'D' : 'L';
    // W-D-L of a list of matches
    public static string Wdl(IReadOnlyCollection<ClubMatch> list)
    {
        int w = list.Count(m => m.Gf > m.Ga), d = list.Count(m => m.Gf == m.Ga);
        return $"{w}W {d}D {list.Count - w - d}L";
    }
    // a result's rating change: the rating after less the one before (the club file's start for the first)
    public static double? Move(List<ClubMatch> rows, int i, double? start)
    {
        var before = i > 0 ? rows[i - 1].Rank : start;
        return before is { } b ? rows[i].Rank - b : null;
    }

    // ---- Dates. A match day ("2026-09-19") is the same day for every visitor, so the server can write it
    public static string ShortDate(string day) => NationsDoc.ShortDate(day);
    public static string LongDate(string day) => $"{ShortDate(day)} {day[..4]}";
    public static string SeasonShort(int y) => $"{y.ToString()[2..]}/{(y + 1).ToString()[2..]}";

    // A club's seasons: July to June, or the calendar year for clubs that play through the summer
    // (more matches in June/July than in December/January: MLS, Norway ...)
    public sealed record Seasons(bool Calendar)
    {
        public int Of(ClubMatch m) { var y = int.Parse(m.Date[..4]); return Calendar ? y : Month(m) >= 7 ? y : y - 1; }
        public string Label(int y) => Calendar ? y.ToString() : SeasonShort(y);
    }
    static int Month(ClubMatch m) => int.Parse(m.Date[5..7]);
    public static Seasons SeasonsOf(List<ClubMatch> rows) =>
        new(rows.Count(m => Month(m) is 6 or 7) > rows.Count(m => Month(m) is 12 or 1));

    // ---- History: season by season, newest first. `League`: the league most of its non-cup matches were in
    public sealed record Season(int Y, string Label, int Played, int W, int D, int L, int Gf, int Ga, double? Start, double End, double Peak, int? League);
    public static List<Season> History(List<ClubMatch> rows, double? start, Func<int, bool> isCup)
    {
        var seasons = SeasonsOf(rows);
        var by = new List<(int Y, double? Start, List<ClubMatch> List)>();
        for (var i = 0; i < rows.Count; i++)
        {
            var y = seasons.Of(rows[i]);
            if (by.Count == 0 || by.All(b => b.Y != y)) by.Add((y, i > 0 ? rows[i - 1].Rank : start, []));
            by.First(b => b.Y == y).List.Add(rows[i]);
        }
        return Enumerable.Reverse(by).Select(s =>
        {
            int w = s.List.Count(m => m.Gf > m.Ga), d = s.List.Count(m => m.Gf == m.Ga);
            var counts = new List<(int League, int N)>();
            foreach (var m in s.List.Where(m => !isCup(m.League)))
            {
                var k = counts.FindIndex(c => c.League == m.League);
                if (k < 0) counts.Add((m.League, 1)); else counts[k] = (m.League, counts[k].N + 1);
            }
            return new Season(s.Y, seasons.Label(s.Y), s.List.Count, w, d, s.List.Count - w - d, s.List.Sum(m => m.Gf), s.List.Sum(m => m.Ga),
                s.Start, s.List[^1].Rank, s.List.Max(m => m.Rank), counts.OrderByDescending(c => c.N).Select(c => (int?)c.League).FirstOrDefault());
        }).ToList();
    }

    // ---- Formations: one entry per formation in a list of matches that have one (oldest first):
    // most used first, with its share, record and goals, and when it was last used
    public sealed record FormationUse(string Formation, int Matches, double Share, string Record, int Gf, int Ga, string Last);
    public static List<FormationUse> Formations(List<ClubMatch> known)
    {
        var by = new List<(string F, List<ClubMatch> Ms)>();
        foreach (var m in known)
        {
            var k = by.FindIndex(b => b.F == m.Formation);
            if (k < 0) by.Add((m.Formation!, [m])); else by[k].Ms.Add(m);
        }
        return by.OrderByDescending(b => b.Ms.Count).ThenByDescending(b => b.Ms[^1].Date, Js.Compare)
            .Select(b => new FormationUse(b.F, b.Ms.Count, 100.0 * b.Ms.Count / known.Count, Wdl(b.Ms), b.Ms.Sum(m => m.Gf), b.Ms.Sum(m => m.Ga), b.Ms[^1].Date)).ToList();
    }

    // A formation ("4-2-3-1") as dots on a 60 x 80 pitch: keeper at the top, attacking down
    public static List<(double X, double Y)> FormationDots(string f)
    {
        var lines = f.Split('-').Select(x => double.TryParse(x, out var n) ? n : 0).Where(n => n > 0).Select(n => (int)n).ToList();
        if (lines.Count == 0) return [];
        const double W = 60, y0 = 25, y1 = 70;
        var dots = new List<(double, double)> { (W / 2, 9) };
        for (var k = 0; k < lines.Count; k++)
        {
            var y = lines.Count == 1 ? (y0 + y1) / 2 : y0 + k * (y1 - y0) / (lines.Count - 1);
            for (var i = 0; i < lines[k]; i++) dots.Add((W * (i + 1) / (lines[k] + 1), y));
        }
        return dots;
    }

    // The roles in a formation ("4-2-3-1" -> GK LB CB RB DM LW AM RW ST), as positions.py role()
    public static List<string> FormationRoles(string f)
    {
        var parts = f.Split('-');
        var lines = parts.Select(x => double.TryParse(x, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var n) ? n : double.NaN).ToList();
        if (lines.Count == 0 || lines.Any(n => !(n > 0))) return [];
        static string Wide(int n, int col, string l, string m, string r) => col == 1 ? l : col == n ? r : m;
        int last = lines.Count - 1, middles = last - 1;
        var backThree = lines[0] == 3;
        var o = new List<string> { "GK" };
        for (var idx = 0; idx < lines.Count; idx++)
        {
            var n = (int)lines[idx];
            for (var col = 1; col <= n; col++)
            {
                string r;
                if (idx == 0) r = n == 4 ? Wide(n, col, "LB", "CB", "RB") : n == 5 ? Wide(n, col, "LWB", "CB", "RWB") : "CB";
                else if (idx == last) r = n >= 3 ? Wide(n, col, "LW", "ST", "RW") : "ST";
                else if (middles == 1 || idx == 1)
                {
                    if (middles != 1 && n <= 2) r = "DM";
                    else if (n == 4) r = backThree ? Wide(n, col, "LWB", "CM", "RWB") : Wide(n, col, "LM", "CM", "RM");
                    else if (n == 5) r = Wide(n, col, "LWB", "CM", "RWB");
                    else r = "CM";
                }
                else if (n <= 2) r = idx == last - 1 ? "AM" : "CM";
                else if (n == 4) r = Wide(n, col, "LM", "CM", "RM");
                else r = Wide(n, col, "LW", "AM", "RW");
                if (!o.Contains(r)) o.Add(r);
            }
        }
        return o;
    }

    // a 0 to 100 player rank's colour band
    public static int RankTier(double r) => r >= 80 ? 4 : r >= 60 ? 3 : r >= 35 ? 2 : 1;
    // a share of 100 as a class from placed.css
    public static int Pct(double v) => Js.RoundInt(Math.Max(0, Math.Min(100, v)));

    // Surname for tight spaces, keeping lower-case particles ("M. de Ligt" -> "de Ligt"), or the
    // name a player is known by where that isn't his surname
    static readonly Dictionary<string, string> KnownAs = new() { ["Gabriel Magalhães"] = "Gabriel", ["Pau Cubarsí Paredes"] = "Cubarsí" };
    public static string ShortName(string name)
    {
        if (KnownAs.TryGetValue(name, out var known)) return known;
        var parts = name.Split(' ');
        var i = parts.Length - 1;
        while (i > 1 && Particle().IsMatch(parts[i - 1])) i--;
        if (i == 1 && parts[0].Length > 0 && char.IsAsciiLetterLower(parts[0][0])) i = 0;
        return string.Join(' ', parts[i..]);
    }
    // his first and last initials: "E. Haaland" -> "EH", "Rodri" -> "R"
    public static string PersonInitials(string name)
    {
        var w = Regex.Split((name ?? "").Replace('.', ' '), @"\s+").Where(x => x.Length > 0).ToList();
        if (w.Count == 0) return "?";
        static string First(string s) => s.EnumerateRunes().First().ToString();
        return (First(w[0]) + (w.Count > 1 ? First(w[^1]) : "")).ToUpperInvariant();
    }

    [GeneratedRegex("^(de|da|do|dos|das|di|del|della|van|von|der|den|ten|ter|la|le|el|al|bin|ben)$", RegexOptions.IgnoreCase)]
    private static partial Regex Particle();
}
