namespace TheCornerFC.Web.Site;

// A line-up on a pitch (web/src/lib/lineups.ts): where each starter stands and what his spot says.
// `ranks`: whether ranks are shown at all (national sides have none).
public static class Lineups
{
    public sealed record Starter(int Id, string Name, string Label, double? Rank, double? Chance = null, double? Mins = null,
        bool? Predicted = null, (int Id, string Name, string? Role, double? Rank)? Instead = null);
    public sealed record Spot(int Id, string Name, string Label, int X, double Y, double? Rank, int? Chance, double? Mins,
        bool? Predicted, (string Name, double? Rank)? Instead, string Tip);

    // what an eleven's pitch (_XiPitch) is drawn from
    public sealed record Pitch(List<Spot> Spots, string[]? Kit, bool Ranks = true);

    public static List<Spot> Spots(List<Starter> xi, bool ranks = true) =>
        Depth.XiSpots(xi, s => s.Label).Select(p =>
        {
            var c = p.C;
            bool hasChance = c.Chance is not null, hasMins = c.Mins is not null, marked = c.Predicted is not null;
            var verdict = !marked ? "" : c.Predicted == true ? " · predicted to start"
                : $" · not predicted{(c.Instead is { } i ? $"; the model picked {i.Name} (rank {(i.Rank is { } r ? Js.ToFixed(r, 1) : "–")})" : "")}";
            return new Spot(c.Id, ClubPage.ShortName(c.Name), c.Label, Js.RoundInt(p.X), p.Y, c.Rank,
                hasChance ? Js.RoundInt(c.Chance!.Value) : null, hasMins ? c.Mins : null,
                marked ? c.Predicted == true : null,
                c.Instead is { } ins ? (ClubPage.ShortName(ins.Name), ins.Rank) : null,
                $"{c.Name} · {c.Label}{(ranks ? $" · rank {(c.Rank is { } rk ? Js.ToFixed(rk, 1) : "–")}" : "")}{(hasChance ? $" · {Js.RoundInt(c.Chance!.Value)}% to start" : "")}{(hasMins ? $" · {c.Mins}′ expected" : "")}{verdict}");
        }).ToList();

    // a line-up row from the database: [player, name, role, rank (null where it is for subscribers)]
    public sealed record XiRow(int Pid, string Name, string? Role, double? Rank);
    public static XiRow ReadRow(System.Text.Json.JsonElement[] r) => new(r[0].GetInt32(), Data.ClubData.Decode(r[1].GetString() ?? ""),
        r.Length > 2 && r[2].ValueKind == System.Text.Json.JsonValueKind.String ? r[2].GetString() : null,
        r.Length > 3 && r[3].ValueKind == System.Text.Json.JsonValueKind.Number ? r[3].GetDouble() : null);

    static readonly Dictionary<string, string> LineOfRole = new()
    {
        ["GK"] = "GK", ["CB"] = "D", ["LB"] = "D", ["RB"] = "D", ["LWB"] = "D", ["RWB"] = "D", ["DM"] = "M", ["CM"] = "M",
        ["LM"] = "M", ["RM"] = "M", ["AM"] = "M", ["LW"] = "F", ["RW"] = "F", ["ST"] = "F",
    };
    // Marks each starter of an actual XI as predicted or not, against the model's pre-match XI. Each
    // starter it missed is paired with a predicted player who didn't start: same position first, then
    // the same position group, then the same line, then anyone. Gives back the marked eleven and how
    // many it got right.
    public static (List<Starter> Xi, int Hits) MarkPredicted(List<Starter> xi, List<XiRow> predicted)
    {
        var started = xi.Select(c => c.Id).ToHashSet();
        var picked = predicted.Select(p => p.Pid).ToHashSet();
        var spare = predicted.Where(p => !started.Contains(p.Pid)).ToList();
        var marked = xi.Select(c => c with { Predicted = picked.Contains(c.Id) }).ToList();
        string? Group(string? r) => r is null ? null : Names.GroupOf.GetValueOrDefault(r);
        string? Line(string? r) => r is null ? null : LineOfRole.GetValueOrDefault(r);
        Func<string, string?, bool>[] tests =
        [
            (a, b) => a == b,
            (a, b) => !string.IsNullOrEmpty(b) && Group(a) == Group(b),
            (a, b) => !string.IsNullOrEmpty(b) && Line(a) == Line(b),
            (_, _) => true,
        ];
        foreach (var same in tests)
            for (var k = 0; k < marked.Count; k++)
            {
                var c = marked[k];
                if (picked.Contains(c.Id) || c.Instead is not null) continue;
                var i = spare.FindIndex(p => same(c.Label, p.Role));
                if (i == -1) continue;
                var p = spare[i];
                spare.RemoveAt(i);
                marked[k] = c with { Instead = (p.Pid, p.Name, p.Role, p.Rank) };
            }
        return (marked, xi.Count - xi.Count(c => !picked.Contains(c.Id)));
    }

    // A match to come: each predicted starter with his rank in the position he is picked in, the
    // number his own page shows for it. His Ability where he has no rank there; none where he has no
    // ranks or they are for subscribers
    public static double? RankIn(Data.Player? p, string? role)
    {
        var group = Names.GroupOf.GetValueOrDefault(role ?? "") ?? "";
        if (p?.PositionRanks is { } pr)
        {
            if (pr.TryGetValue(group, out var r)) return r;
            if (Depth.NearGroup.TryGetValue(group, out var near) && pr.TryGetValue(near, out var n)) return n;
        }
        return p?.Rank;
    }
    public static List<XiRow> WithSlotRank(List<XiRow> rows, IReadOnlyDictionary<int, Data.Player> players) =>
        rows.Select(r => r with { Rank = RankIn(players.GetValueOrDefault(r.Pid), r.Role) }).ToList();
    // The average of an eleven's ranks to a whole number, those without one left out
    public static int? AverageRank(IEnumerable<double?> ranks)
    {
        double total = 0;
        var n = 0;
        // (added up in order, one at a time, as JavaScript's reduce does)
        foreach (var r in ranks) if (r is { } v) { total += v; n++; }
        return n > 0 ? Js.RoundInt(total / n) : null;
    }
}
