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
}
