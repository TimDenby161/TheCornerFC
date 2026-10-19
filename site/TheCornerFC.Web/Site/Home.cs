using System.Text.Json;
using System.Text.Json.Serialization;
using TheCornerFC.Web.Data;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Site;

// The Line-up record's live rows (the "lineups" row) and the reconstructed history's
// (site_lineup_history), as far as Home reads them (web/src/lib/lineupRecord.ts)
public sealed record LiveDoc(string[] Fields, JsonElement[][] Rows);
public sealed record HistoryDoc(JsonElement[][]? Rows);
public sealed record LineupsAnswer(Dictionary<string, JsonElement[][]>? Actual, Dictionary<string, JsonElement[][]>? Prematch);

// Home's slides (web/src/lib/server/home.ts): a sample of the real thing from each part of the
// site. Each is worked out from what its own page reads, as a visitor who isn't signed in sees it;
// one whose sample can't be had is left out (null).
public static class Home
{
    const int Top = 7; // rows in a slide's list
    static async Task<T?> Quiet<T>(Task<T> t) where T : class
    {
        try { return await t; }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { return null; }
    }
    static List<Club> Strongest(List<Club> all) => all.OrderByDescending(x => x.Current).ToList();

    public sealed record ClubRow(int Team, string Name, string Comp, int Current, int? Form);
    public static List<ClubRow> Clubs(SiteDoc site, List<Club> all) => Strongest(all).Take(Top)
        .Select(x => new ClubRow(x.Team, site.TeamName(x.Team), site.CompLabel(x.League), Js.RoundInt(x.Current), x.Form is { } f ? Js.RoundInt(f) : null)).ToList();

    public sealed record LeagueRow(int Lid, string Name, string Sub, int Lt, int Tier);
    public static List<LeagueRow> Leagues(SiteDoc site, List<Club> all)
    {
        var tier = Data.Clubs.Tiers(all, "lt");
        // (in the competitions' own order, as JavaScript lists a numbered object's keys, before sorting)
        return Site.Leagues.Averages(site, all).OrderBy(c => c.Lid).OrderByDescending(c => c.Lt).Take(Top)
            .Select(c => new LeagueRow(c.Lid, c.Name, $"{ClubTable.CountryDisplay(c.Country)} · {c.Clubs} clubs", Js.RoundInt(c.Lt), tier(c.Lt))).ToList();
    }

    // The first of the Players list, as it opens
    public sealed record PlayerRow(int Id, string Name, int? Team, string? TeamName, string League, string? Nat, string? Flag, string Pos, double Rank);
    static readonly Dictionary<string, string> PosLabel = new() { ["G"] = "GK", ["D"] = "DEF", ["M"] = "MID", ["F"] = "FWD" };
    public static async Task<List<PlayerRow>?> Players(Database db, SiteDoc site)
    {
        var d = await Quiet(db.KeptAsk<PlayersAnswer>("site_players", new { p_limit = Top }));
        var rows = d is null ? [] : ClubData.Players(site, d.Rows ?? []).Where(p => p.Seasons is { Length: > 0 } s && s[0] is not null).ToList();
        return rows.Count == 0 ? null : rows.Select(p => new PlayerRow(p.Id, p.Name, p.Team, p.Team is { } t and not 0 ? site.TeamName(t) : null,
            p.League is { } lg ? site.LeagueShort(lg) : "", p.Nationality, p.Nationality is { Length: > 0 } n ? Names.FlagCodes.GetValueOrDefault(n) : null,
            p.Position is { Length: > 0 } pos ? PosLabel.GetValueOrDefault(pos) ?? pos : "", p.Seasons![0]!.Value)).ToList();
    }

    public sealed record NationRow(string Name, string? Flag, string Confed, int Current, int Tier, int? Change);
    public static async Task<List<NationRow>?> Nations(Database db)
    {
        var d = await Quiet(db.KeptDoc<NationsDoc>("nations", TimeSpan.FromMinutes(5)));
        return d?.Nations.OrderByDescending(n => n.Current).Take(Top).Select(n => new NationRow(n.Name, Names.FlagCodes.GetValueOrDefault(n.Name), n.Confed ?? "",
            Js.RoundInt(n.Current), d.Tier(n.Current), n.YearAgo is { } y ? Js.RoundInt(n.Current - y) : null)).ToList();
    }

    // The last year of the Stats page, by its strongest true figures: how many matches were marked
    // (the headline), how often a result the model gave 70% or more came in, the right-result rate
    // against always picking the home team, the exact scores, the goals it was off by, how far the
    // chances it gave were from how often they happened, and the competitions marked.
    const double Sure = 0.7;
    public sealed record StatsSlide(string Matches, List<(string N, string Unit, string What)> Nums, string Note);
    public static string PctText(double x, int d = 1) => $"{Js.ToFixed(100 * x, d)}%";
    public static async Task<StatsSlide?> Stats(Database db) => StatsOf(await Quiet(db.KeptDoc<StatsDoc>("stats", TimeSpan.FromMinutes(5))));
    public static StatsSlide? StatsOf(StatsDoc? doc)
    {
        var year = doc?.Ranges.GetValueOrDefault("365d");
        if (year?.GetValueOrDefault("all") is not { N: > 0 } s) return null;
        // (a missing figure counts as nothing in these sums, as in JavaScript)
        static double V(double?[] b, int i) => i < b.Length ? b[i] ?? 0 : 0;
        var bands = (s.Calibration ?? []).Where(b => V(b, 0) != 0).ToList();
        var sure = bands.Where(b => b.Length > 1 && b[1] is { } said && said >= Sure).ToList();
        double calls = 0, came = 0, saidTotal = 0, off = 0;
        foreach (var b in sure) { calls += V(b, 0); came += V(b, 0) * V(b, 2); }
        foreach (var b in bands) { saidTotal += V(b, 0); off += V(b, 0) * Math.Abs(V(b, 1) - V(b, 2)); }
        var comps = year.Keys.Count(k => k != "all");
        var nums = new List<(string, string, string)?>
        {
            calls != 0 ? (PctText(came / calls, 0), "", $"of the results the model gave {PctText(Sure, 0)} or more came in") : null,
            (PctText(s.Correct ?? 0, 0), "", $"right result, against {PctText(s.HomeRate ?? 0, 0)} by picking the home team every time"),
            s.Exact is { } ex && ex != 0 ? ($"1 in {Js.RoundInt(1 / ex)}", "", "exact scores right") : null,
            s.GoalError is { } ge ? (Js.ToFixed(ge, 2), "", "goals off per team, on average") : null,
            saidTotal != 0 ? (Js.ToFixed(100 * off / saidTotal, 1), " pts", "between the chance it gave and how often it happened") : null,
            comps != 0 ? (Js.Num(comps), "", "competitions marked") : null,
        };
        return new(Js.Num(s.N), nums.Where(x => x is not null).Select(x => x!.Value).ToList(),
            s.Live < s.N ? $"{Js.Num(s.Live)} recorded before kickoff, the rest reconstructed from pre-match data." : "");
    }

    // a club's matches as a visitor who isn't signed in sees them, oldest first
    static async Task<List<Match>?> Fixtures(Database db, SiteDoc site, int team)
    {
        var answer = await Quiet(db.KeptAsk<MatchesAnswer>("site_matches", new { p_team = team }));
        return answer is null ? null : ClubData.MatchRows(site, answer);
    }

    // A few matches' chances as a taste of the Matches page: the next match of each of the
    // strongest clubs that has the model's chances, soonest first (two of them meeting is one match)
    const int CallClubs = 4, CallCount = 3;
    public sealed record Call(int Id, string HomeName, string AwayName, string Comp, string Kickoff, int H, int D, int A);
    public sealed record Calls(string Day, List<Call> List);
    public static async Task<Calls?> MatchCalls(Database db, SiteDoc site, List<Club> all, string tz, DateTimeOffset now)
    {
        var teams = Strongest(all).Take(CallClubs).Select(x => x.Team).ToList();
        var lists = await Task.WhenAll(teams.Select(t => Fixtures(db, site, t)));
        var next = lists.Select(l => (l ?? []).FirstOrDefault(x => x.Status == "NS" && x.PHome is not null && x.PDraw is not null && DateTimeOffset.Parse(x.Kickoff) > now))
            .Where(m => m is not null).Select(m => m!).ToList();
        var seen = new HashSet<int>();
        var ms = next.Where(m => seen.Add(m.Id)).Take(CallCount).OrderBy(m => m.Kickoff, Js.Compare).ToList();
        if (ms.Count == 0) return null;
        return new(Matchday.LocalDay(DateTimeOffset.Parse(ms[0].Kickoff), tz), ms.Select(m =>
        {
            var p = Cards.ShownProbs(m.PHome!.Value, m.PDraw!.Value);
            return new Call(m.Id, site.TeamName(m.Home), site.TeamName(m.Away), site.CompLabel(m.League), m.Kickoff, p[0], p[1], p[2]);
        }).ToList());
    }

    // The example line-up: the XI that started, on a pitch, marked against the one the model
    // predicted for it. Always a club in the world's top ten, so a name a visitor knows: its latest
    // match where the model named nine or ten of the eleven, not all of them, so the slide shows a
    // miss marked too. From the Line-up record where it has one (the last three weeks); where it
    // doesn't, as while the record is new, from the reconstructed history's last 30 days, and the
    // slide says so. No top-ten club with a nine or a ten there: the latest of theirs with all
    // eleven, then their latest of any. None at all: left out.
    const int XiClubs = 10, XiRight = 9, XiDays = 30;
    static bool Fair(int right) => right >= XiRight && right < 11;
    public sealed record XiSlide(string What, int Hits, int Of, string Cls, bool Bare, List<Lineups.Spot> Spots, string Note);
    public static async Task<XiSlide?> Xi(Database db, SiteDoc site, List<Club> all, string tz, DateTimeOffset now)
    {
        var top = Strongest(all).Take(XiClubs).ToList();
        var known = top.Select(x => x.Team).ToHashSet();
        Task<LineupsAnswer?> LineupsOf(int fixture) => Quiet(db.KeptAsk<LineupsAnswer?>("site_lineups", new { p_fixture = fixture }, TimeSpan.FromMinutes(5)));
        static List<Lineups.Starter> Cells(JsonElement[][] started) => started.Select(Lineups.ReadRow)
            .Select(r => new Lineups.Starter(r.Pid, r.Name, r.Role is { Length: > 0 } role ? role : "CM", r.Rank)).ToList();
        XiSlide Draw(int team, int opponent, bool home, string kickoff, List<Lineups.Starter> xi, string note)
        {
            var hits = xi.Count(c => c.Predicted == true);
            return new($"{site.TeamName(team)} {(home ? "v" : "at")} {site.TeamName(opponent)} · {Matchday.DayName(Matchday.LocalDay(DateTimeOffset.Parse(kickoff), tz))}",
                hits, xi.Count, hits >= 9 ? "good" : hits >= 7 ? "ok" : "poor", !xi.Any(c => c.Rank is not null), Lineups.Spots(xi), note);
        }

        var rec = await Quiet(db.KeptDoc<LiveDoc>("lineups", TimeSpan.FromMinutes(5)));
        var live = (rec?.Rows ?? []).Select(r => new Named(rec!.Fields, r))
            .Select(n => (Fixture: n.I("fixture") ?? 0, Team: n.I("team") ?? 0, Opponent: n.I("opponent") ?? 0, Home: n.I("home") ?? 0,
                Correct: n.I("correct") ?? 0, Kickoff: n.S("kickoff") ?? ""))
            .Where(x => x.Kickoff != "" && known.Contains(x.Team) && Fair(x.Correct) && DateTimeOffset.Parse(x.Kickoff) > now - TimeSpan.FromDays(20))
            .Select((x, i) => (x, i)).OrderByDescending(t => DateTimeOffset.Parse(t.x.Kickoff)).ThenBy(t => t.i).Select(t => t.x).ToList();
        if (live.Count > 0)
        {
            var l = live[0];
            var fx = await LineupsOf(l.Fixture);
            var started = fx?.Actual?.GetValueOrDefault(l.Team.ToString());
            var predicted = fx?.Prematch?.GetValueOrDefault(l.Team.ToString());
            if (started is { Length: > 0 } && predicted is { Length: > 0 })
            {
                var (xi, _) = Lineups.MarkPredicted(Cells(started), predicted.Select(Lineups.ReadRow).ToList());
                // no room here for the model's other pick under each miss
                return Draw(l.Team, l.Opponent, l.Home != 0, l.Kickoff, xi.Select(c => c with { Instead = null }).ToList(), "");
            }
        }
        // the history's rows, newest first: [date, team, opponent, home, competition, right, missed]
        var leagues = top.Select(x => x.League).Distinct().ToArray();
        var hist = await Quiet(db.KeptAsk<HistoryDoc>("site_lineup_history", new { p_days = XiDays, p_limit = 300, p_leagues = leagues }, TimeSpan.FromMinutes(30)));
        var rows = (hist?.Rows ?? []).Where(x => known.Contains(x[1].GetInt32())).ToList();
        var r = rows.FirstOrDefault(x => Fair(x[5].GetInt32())) ?? rows.FirstOrDefault(x => x[5].GetInt32() >= XiRight) ?? rows.FirstOrDefault();
        if (r is null) return null;
        var (day, team, opponent, home) = (r[0].GetString()!, r[1].GetInt32(), r[2].GetInt32(), r[3].GetInt32() != 0);
        var missed = r[6].EnumerateArray().Select(e => e.GetInt32()).ToHashSet();
        var fixtures = await Fixtures(db, site, team);
        var dayAt = DateTimeOffset.Parse(day.Length == 10 ? $"{day}T00:00:00Z" : day);
        var m = fixtures?.FirstOrDefault(x => x.Home == (home ? team : opponent) && x.Away == (home ? opponent : team)
            && (DateTimeOffset.Parse(x.Kickoff) - dayAt).Duration() < TimeSpan.FromDays(2));
        var startedXi = m is null ? null : (await LineupsOf(m.Id))?.Actual?.GetValueOrDefault(team.ToString());
        if (m is null || startedXi is not { Length: > 0 }) return null;
        return Draw(team, opponent, home, m.Kickoff, Cells(startedXi).Select(c => c with { Predicted = !missed.Contains(c.Id) }).ToList(),
            "Reconstructed afterwards from pre-match data.");
    }
}
