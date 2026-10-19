using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.League;

// One round at a time, opening on the round with the next fixture
public sealed class MatchesModel(Database db) : LeaguePage(db)
{
    public sealed record Side(int Id, string Name, bool Won);
    public sealed record Row(int Id, DateTimeOffset Kickoff, bool Live, string? Off, Side Home, Side Away, string? Score, string? Pens, string? Xg, string? Probs);

    public bool Any { get; private set; }
    public string Round { get; private set; } = "";
    public List<(string Key, string Label)> Rounds { get; private set; } = [];
    public string? Prev { get; private set; }
    public string? Next { get; private set; }
    public List<(string Name, List<Row> Matches)> Days { get; private set; } = [];

    protected override Task<IActionResult?> Load()
    {
        var (rounds, open) = Leagues.Rounds(L.Fixtures);
        Any = rounds.Count > 0;
        if (!Any) return Task.FromResult<IActionResult?>(null);
        var asked = Request.Query["round"].FirstOrDefault();
        Round = asked is not null && rounds.Contains(asked) ? asked : open!;
        var i = rounds.IndexOf(Round);
        Rounds = rounds.Select(r => (r, Leagues.RoundLabel(r))).ToList();
        Prev = i > 0 ? rounds[i - 1] : null;
        Next = i < rounds.Count - 1 ? rounds[i + 1] : null;
        var tz = Visitor.Zone.Tz;
        Days = L.Fixtures.Where(f => (f.Round ?? "") == Round)
            .GroupBy(f => Times.LocalDay(DateTimeOffset.Parse(f.Kickoff), tz))
            .Select(g => (Times.DayName(g.Key), g.Select(f =>
            {
                bool done = f.Hg is not null && (Leagues.Finished.Contains(f.Status) || Leagues.Live.Contains(f.Status)), over = done && Leagues.Finished.Contains(f.Status);
                // before it is played: the model's expected goals and its home, draw and away chances
                return new Row(f.Id, DateTimeOffset.Parse(f.Kickoff), Leagues.Live.Contains(f.Status), Leagues.OffText(f.Status),
                    new(f.Home, L.Club(f.Home), over && f.Hg > f.Ag), new(f.Away, L.Club(f.Away), over && f.Ag > f.Hg),
                    done ? $"{f.Hg}–{f.Ag}" : null, done && f.PenH is not null ? $"{f.PenH}–{f.PenA} pens" : null,
                    !done && f.PHome is not null && f.HomeXg is { } hx && f.AwayXg is { } ax ? $"{Js.ToFixed(hx, 1)}–{Js.ToFixed(ax, 1)}" : null,
                    !done && f.PHome is { } ph && f.PDraw is { } pd && f.PAway is { } pa ? $"{Js.RoundInt(ph * 100)}% · {Js.RoundInt(pd * 100)}% · {Js.RoundInt(pa * 100)}%" : null);
            }).ToList())).ToList();
        return Task.FromResult<IActionResult?>(null);
    }

    // this tab on another round (the round it opens on is left out of the address)
    public string Address(string? round) => round is null ? Request.Path.Value! : "?" + Markup.Query([new("round", round)]);
}
