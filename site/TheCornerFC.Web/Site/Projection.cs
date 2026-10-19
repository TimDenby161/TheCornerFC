using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// ---- Projected table: the rest of the season played out Sims times from the model's
// predictions (web/src/lib/league.ts, projectGroup). Each upcoming match's score is drawn from its
// Poisson grid, scaled to its home / draw / away chances. Each simulated season also gives every
// club a random true strength (StrengthSd, on the log of its expected goals), shared by all its
// matches: the model's ratings are estimates, and a club that is really a little better or worse
// is so every week. Without it the matches are independent coin flips, their luck evens out over a
// season and the leaders' chances come out far too high.
public static class Projection
{
    public const int Sims = 5000;
    const double StrengthSd = 0.15;
    const double ShiftStep = 0.05;
    const int ShiftMax = 16;    // strength gaps rounded to 0.05, capped at ±0.8

    public sealed record Projected(int Team, int Left, double W, double D, double L, double Pts, double Gd, double[] Pos);

    static double[] Pmf(double lam)
    {
        var o = new double[11];
        var m = Math.Max(lam, 0.01);
        var p = Math.Exp(-m);
        for (var k = 0; k <= 10; k++) { o[k] = p; p *= m / (k + 1); }
        return o;
    }

    sealed class Table(double[] cdf, sbyte[] hg, sbyte[] ag, double total)
    {
        public readonly double[] Cdf = cdf;
        public readonly sbyte[] Hg = hg, Ag = ag;
        public readonly double Total = total;
    }

    // one match's scores at a strength gap of `shift` (home minus away), most likely first, as
    // cumulative chances. The model's result chances are kept by reweighting each result by the
    // same factor that matches the unshifted grid to them.
    static Table ScoreTable(Fixture f, double[] fix, double shift)
    {
        var e = Math.Exp(shift);
        double[] ph = Pmf(f.HomeXg!.Value * e), pa = Pmf(f.AwayXg!.Value / e);
        var cells = new List<(int I, int J, double P)>(121);
        for (var i = 0; i <= 10; i++) for (var j = 0; j <= 10; j++) cells.Add((i, j, ph[i] * pa[j] * fix[i > j ? 0 : i == j ? 1 : 2]));
        // (most likely first; equal chances keep their order, as the browser's sort does)
        var sorted = cells.Select((c, n) => (c, n)).OrderByDescending(x => x.c.P).ThenBy(x => x.n).Select(x => x.c).ToList();
        var cdf = new double[sorted.Count];
        var hg = new sbyte[sorted.Count];
        var ag = new sbyte[sorted.Count];
        double acc = 0;
        for (var n = 0; n < sorted.Count; n++) { cdf[n] = acc += sorted[n].P; hg[n] = (sbyte)sorted[n].I; ag[n] = (sbyte)sorted[n].J; }
        return new(cdf, hg, ag, acc);
    }

    static double[] Fix(Fixture f)
    {
        double[] ph = Pmf(f.HomeXg!.Value), pa = Pmf(f.AwayXg!.Value), sums = new double[3];
        for (var i = 0; i <= 10; i++) for (var j = 0; j <= 10; j++) sums[i > j ? 0 : i == j ? 1 : 2] += ph[i] * pa[j];
        double[] w = [f.PHome!.Value, f.PDraw!.Value, f.PAway!.Value];
        return w.Select((x, k) => sums[k] != 0 ? x / sums[k] : 0).ToArray();
    }

    // the fixtures the model has projected: the ones a season can be played out from
    public static List<Fixture> Projectable(IEnumerable<Fixture> fixtures) =>
        fixtures.Where(f => f.PHome is not null && f.HomeXg is not null && f.AwayXg is not null && f.PDraw is not null && f.PAway is not null).ToList();

    // (`random`: the source of chance, so a test can fix it)
    public static List<Projected> Group(List<TableRow> rows, List<Fixture> fixtures, int sims = Sims, Func<double>? random = null)
    {
        random ??= Random.Shared.NextDouble;
        double Gauss() => Math.Sqrt(-2 * Math.Log(1 - random())) * Math.Cos(2 * Math.PI * random());
        var n = rows.Count;
        var idx = rows.Select((r, i) => (r.Team, i)).GroupBy(x => x.Team).ToDictionary(g => g.Key, g => g.First().i);
        var games = fixtures.Where(f => idx.ContainsKey(f.Home) || idx.ContainsKey(f.Away)).Select(f =>
        {
            var fix = Fix(f);
            var tables = new Table?[2 * ShiftMax + 1];
            tables[ShiftMax] = ScoreTable(f, fix, 0);
            return (H: idx.TryGetValue(f.Home, out var h) ? h : -1, A: idx.TryGetValue(f.Away, out var a) ? a : -1, F: f, Fix: fix, Tables: tables, Hs: 0, As: 0);
        }).ToArray();
        // clubs outside this group (other groups' opponents) get their own strength draw too
        var outside = new Dictionary<int, int>();
        var m = n;
        foreach (var f in fixtures) foreach (var t in new[] { f.Home, f.Away }) if (!idx.ContainsKey(t) && !outside.ContainsKey(t)) outside[t] = m++;
        for (var g = 0; g < games.Length; g++)
        {
            games[g].Hs = games[g].H >= 0 ? games[g].H : outside[games[g].F.Home];
            games[g].As = games[g].A >= 0 ? games[g].A : outside[games[g].F.Away];
        }
        var pos = rows.Select(_ => new double[n]).ToArray();
        double[] sumPts = new double[n], sumGd = new double[n], pts = new double[n], gd = new double[n], gf = new double[n], tie = new double[n];
        var strength = new double[m];
        var order = Enumerable.Range(0, n).ToArray();
        for (var s = 0; s < sims; s++)
        {
            for (var i = 0; i < n; i++) { var r = rows[i]; pts[i] = r.Points ?? 0; gd[i] = r.Gd ?? 0; gf[i] = r.Gf ?? 0; tie[i] = random(); }
            for (var i = 0; i < m; i++) strength[i] = StrengthSd * Gauss();
            foreach (var g in games)
            {
                var k = (int)Math.Max(-ShiftMax, Math.Min(ShiftMax, Js.Round((strength[g.Hs] - strength[g.As]) / ShiftStep)));
                var t = g.Tables[k + ShiftMax] ??= ScoreTable(g.F, g.Fix, k * ShiftStep);
                var u = random() * t.Total;
                var c = 0;
                while (c < t.Cdf.Length - 1 && t.Cdf[c] < u) c++;
                int hg = t.Hg[c], ag = t.Ag[c], hp = hg > ag ? 3 : hg == ag ? 1 : 0, ap = hg < ag ? 3 : hg == ag ? 1 : 0;
                if (g.H >= 0) { pts[g.H] += hp; gd[g.H] += hg - ag; gf[g.H] += hg; }
                if (g.A >= 0) { pts[g.A] += ap; gd[g.A] += ag - hg; gf[g.A] += ag; }
            }
            Array.Sort(order, (x, y) => Cmp(pts[y], pts[x]) is not 0 and var a ? a : Cmp(gd[y], gd[x]) is not 0 and var b ? b : Cmp(gf[y], gf[x]) is not 0 and var c2 ? c2 : Cmp(tie[y], tie[x]));
            for (var p = 0; p < n; p++) pos[order[p]][p]++;
            for (var i = 0; i < n; i++) { sumPts[i] += pts[i]; sumGd[i] += gd[i]; }
        }
        double[] left = new double[n], xw = new double[n], xd = new double[n];
        foreach (var g in games)
        {
            if (g.H >= 0) { left[g.H]++; xw[g.H] += g.F.PHome!.Value; xd[g.H] += g.F.PDraw!.Value; }
            if (g.A >= 0) { left[g.A]++; xw[g.A] += g.F.PAway!.Value; xd[g.A] += g.F.PDraw!.Value; }
        }
        return rows.Select((r, i) => new Projected(r.Team, (int)left[i], (r.Win ?? 0) + xw[i], (r.Draw ?? 0) + xd[i],
                (r.Lose ?? 0) + left[i] - xw[i] - xd[i], sumPts[i] / sims, sumGd[i] / sims, pos[i].Select(c => c / sims).ToArray()))
            .OrderByDescending(x => x.Pts).ThenByDescending(x => x.Gd).ToList();
    }

    static int Cmp(double a, double b) => a < b ? -1 : a > b ? 1 : 0;
}
