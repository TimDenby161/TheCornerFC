using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Pages.ClubTabs;

// A club's Overview: the next match and injured and suspended players beside the whole squad on a
// pitch, then the next 5 fixtures and recent results (web/src/routes/(app)/club/[id]/+page)
public sealed class IndexModel(Database db) : ClubPageModel(db)
{
    static readonly HashSet<string> BanReasons = ["Red Card", "Yellow Cards", "Suspended"];

    public sealed record Side(bool Home, int Opp, string OppName, double? Gf, double? Ga, int? Win);
    // Link: he has a page (he is among the club's listed players); a long-term absentee who has
    // dropped out of the ranks has none, so his name isn't a link (found by the site sweep, 2026-10-22)
    public sealed record InjuredPlayer(int Id, string Name, int Missed, double? Rank, string? Note, string? Ban, bool Link = true);
    public sealed record InjuryCard(bool Upcoming, DateTimeOffset Kickoff, string? Latest, List<InjuredPlayer> Players);
    public sealed record PitchRow(int Id, string Name, int? Pct, int Rank, int XMin, string Tip);
    public sealed record PitchBox(string Label, int N, string Row, int Col, int Total, List<PitchRow> Rows);
    public sealed record FixtureRow(int Id, DateTimeOffset Kickoff, Side S, int League, string Comp, string CompFull, int? Cs);
    public sealed record ResultRow(string Date, int Gf, int Ga, int Opp, string OppName, string Where, int League, string Comp,
        double? Xgf, double? Xga, bool Est, double? Move, string Title);

    public NextMatch? Next { get; private set; }
    public InjuryCard? InjuryList { get; private set; }
    public string[]? Kit { get; private set; }
    public List<PitchBox>? Boxes { get; private set; }
    public List<FixtureRow> FixtureRows { get; private set; } = [];
    public List<ResultRow> Results { get; private set; } = [];

    protected override async Task<IActionResult?> Load()
    {
        var site = C.Site;
        var squad = await C.SquadFor(Db, Visitor.Token);
        var byId = squad.List.GroupBy(p => p.Id).ToDictionary(g => g.Key, g => g.First());
        var next = ClubData.Upcoming(squad.Matches);
        Side SideOf(Match m)
        {
            var home = m.Home == C.Id;
            var opp = home ? m.Away : m.Home;
            var both = m.HomeXg is not null && m.AwayXg is not null;
            return new(home, opp, site.TeamName(opp), both ? (home ? m.HomeXg : m.AwayXg) : null, both ? (home ? m.AwayXg : m.HomeXg) : null,
                m.PHome is { } ph && m.PAway is { } pa ? Js.RoundInt(100 * (home ? ph : pa)) : null);
        }
        var m0 = next.FirstOrDefault();
        var nextLabel = m0 is null ? "" : site.LeagueShort(m0.League);
        var inj = squad.Inj;
        var past = inj is not null && !inj.Upcoming ? C.Rows.FirstOrDefault(r => r.Date == inj.Kickoff[..10]) : null;
        if (m0 is not null)
        {
            var s = SideOf(m0);
            Next = new(DateTimeOffset.Parse(m0.Kickoff), ClubData.Live.Contains(m0.Status), s.Home, s.Opp, s.OppName, site.CompLabel(m0.League), s.Win,
                s.Gf, s.Ga, Xi: m0.Home == C.Id ? m0.HomeXi : m0.AwayXi, Missing: (m0.Home == C.Id ? m0.HomeMissing : m0.AwayMissing) ?? 0);
        }
        if (inj is not null)
            InjuryList = new(inj.Upcoming, DateTimeOffset.Parse(inj.Kickoff),
                past is not null ? $"{(past.Home != 0 ? "v" : "@")} {C.Opponent(past.Opponent)}" : null,
                // best first by rank
                inj.Players.Select(row =>
                {
                    var pid = row[0].GetInt32();
                    double? rank = byId.TryGetValue(pid, out var p) && p.Rank is not null ? p.Rank : row.Length > 5 && row[5].ValueKind == System.Text.Json.JsonValueKind.Number ? row[5].GetDouble() : null;
                    return (Row: row, Rank: rank);
                }).OrderByDescending(x => x.Rank ?? -1).Select(x =>
                {
                    var type = x.Row[2].GetString();
                    var ban = x.Row[3].ValueKind == System.Text.Json.JsonValueKind.String ? x.Row[3].GetString() : null;
                    var banned = ban is not null && BanReasons.Contains(ban);
                    return new InjuredPlayer(x.Row[0].GetInt32(), x.Row[1].GetString() ?? "", x.Row[4].GetInt32(), x.Rank,
                        type == "Questionable" ? "doubt" : type == "Suspended" || banned ? "susp" : null, banned && ban != "Suspended" ? ban : null,
                        byId.ContainsKey(x.Row[0].GetInt32()));
                }).ToList());
        // the squad by position: each box's players, best first, with the chance each starts there
        // in the next match and the minutes he is expected to play
        if (squad.Depth is { } depth)
        {
            Kit = squad.Kit;
            Boxes = depth.Shown.Select(b => new PitchBox(b.Label, b.N, b.Row == "3 / span 2" ? "3s2" : b.Row, b.Col, (int)depth.BoxMins.GetValueOrDefault(b.Label),
                b.Ps.Select(d =>
                {
                    var p = d.P;
                    var got = Js.RoundInt(depth.StartChance.GetValueOrDefault($"{b.Label}:{p.Id}"));
                    var xmin = (int)depth.XMins.GetValueOrDefault($"{b.Label}:{p.Id}");
                    var bench = depth.BenchRate(p);
                    return new PitchRow(p.Id, ClubPage.ShortName(p.Name), got != 0 ? got : null, Js.RoundInt(d.Rank ?? 0), xmin,
                        $"{p.Name}: {got}% chance of starting at {b.Label} in the next match{(nextLabel != "" ? $" ({nextLabel})" : "")} (started {depth.StartPct(p, b.Roles) ?? 0}% of this season's matches there{(b.Proj?.Changed == true ? "; allowing for the injured or departed" : "")})"
                        + ((depth.Picks.GetValueOrDefault(b.Label) ?? []).Contains(p.Id) ? " · in the best XI by rating" : "")
                        + $" · xMins {xmin}: lasts {Js.RoundInt(depth.Lasts(p))}′ when he starts{(bench != 0 ? $", {Js.RoundInt(bench)}′ a match off the bench" : "")}");
                }).ToList())).ToList();
        }
        // the fixtures after it
        FixtureRows = next.Take(5).Select(f =>
        {
            var s = SideOf(f);
            return new FixtureRow(f.Id, DateTimeOffset.Parse(f.Kickoff), s, f.League, site.LeagueShort(f.League), site.CompLabel(f.League),
                s.Ga is { } ga ? Js.RoundInt(100 * Math.Exp(-ga)) : null);
        }).ToList();
        // the last ten results, newest first
        var rows = C.Rows;
        var last = rows.TakeLast(10).ToList();
        Results = last.Select((r, k) => new ResultRow(r.Date, r.Gf, r.Ga, r.Opponent, C.Opponent(r.Opponent), r.Home == 2 ? "N" : r.Home != 0 ? "H" : "A",
            r.League, site.CompLabel(r.League), r.Xgf, r.Xga, r.XgEst is not null and not 0, ClubPage.Move(rows, rows.Count - last.Count + k, C.Doc?.Start),
            $"{ClubPage.ShortDate(r.Date)} {(r.Home != 0 ? "v" : "@")} {C.Opponent(r.Opponent)}{(r.Home == 2 ? " (neutral)" : "")} · {site.CompLabel(r.League)}")).Reverse().ToList();
        return null;
    }
}
