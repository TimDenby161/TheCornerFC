using System.Globalization;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// The Line-up record: how often the line-ups the model predicted matched the team sheets, from the
// live record (saved before kick-off) or the reconstructed history (web/src/routes/(app)/lineups)
public sealed class LineupsModel(Database db, TimeProvider clock) : PageModel
{
    public static readonly (string Key, string Label)[] Ranges = [("7", "7 days"), ("30", "30 days"), ("90", "90 days"), ("365", "12 months"), ("all", "All time")];
    static readonly string[] Months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], Weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    static readonly MenuTitles Titles = new(
        "All competitions", c => $"All {c} line-ups", r => $"All line-ups in {r}",
        "Champions League, Europa League and Conference League line-ups", n => $"{n} line-ups", Intl: "National team line-ups");

    public sealed record Bar(string Label, int Share, string Tip, string Text, string Dim = "");
    public sealed record LineView(string Name, double Starters, double Hit, string Rate, int Bar);
    public sealed record TimingView(string Label, int N, string Named, string Perfect);
    public sealed record CompView(int Id, string Name, bool On, int N, string Named, string Perfect, string Position);
    public sealed record ClubRow(int Id, string Name, string Href, int N, string Named, string Perfect);
    public sealed record TallyView(int Id, string Name, string Team, int N);
    public sealed record VersionView(string Label, string Name, string From, int N, string Named, string Perfect);
    public sealed record RowView(string Date, string Team, string Href, bool Home, string Opponent, string Comp, int Correct, string Missed);

    public bool Live { get; private set; }
    public string Range { get; private set; } = "all";
    public double Shown { get; private set; }
    public string Filter { get; private set; } = "all";
    public FilterMenuModel? Menu { get; private set; }
    public string State { get; private set; } = "waiting"; // waiting, none, empty or ok
    public string Step { get; private set; } = "day";
    public List<(string Label, string Value, string Note)> CardsShown { get; private set; } = [];
    public string Sample { get; private set; } = "";
    public List<Bar> Spread { get; private set; } = [];
    public List<Bar> Trend { get; private set; } = [];
    public List<LineView> LinesShown { get; private set; } = [];
    public List<TimingView> Timing { get; private set; } = [];
    public List<CompView> Comps { get; private set; } = [];
    public (List<ClubRow>? Easiest, List<ClubRow>? Hardest, List<ClubRow> All) ClubsShown { get; private set; }
    public List<TallyView> Missed { get; private set; } = [];
    public List<TallyView> Wrong { get; private set; } = [];
    public int MissedTotal { get; private set; }
    public List<VersionView> Versions { get; private set; } = [];
    public List<RowView> Rows { get; private set; } = [];
    public (double Left, double N)? More { get; private set; }
    public int Excluded { get; private set; }

    static async Task<T?> Quiet<T>(Task<T> t) where T : class
    {
        try { return await t; }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or System.Text.Json.JsonException) { return null; }
    }

    public async Task OnGet()
    {
        var visitor = Visitor.Of(HttpContext);
        var tz = visitor.Zone.Tz;
        var site = await db.KeptDoc<SiteDoc>("site");
        var q = Request.Query;
        Live = q["src"].ToString() != "history";
        var r = q["r"].ToString();
        Range = Ranges.Any(x => x.Key == r) ? r : "all";
        int? days = Range == "all" ? null : int.Parse(Range);
        // (as JavaScript's Number reads the address: anything but a number is the first page)
        var n = double.TryParse(q["n"].ToString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var asked) && asked != 0 && !double.IsNaN(asked) ? asked : LineupRecord.Page;
        Shown = Math.Min(1000, Math.Max(LineupRecord.Page, n));
        if (!visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        ViewData["TabHead"] = TabHead.For("Line-up record", "lineups");
        var now = clock.GetUtcNow();

        // the menu over the competitions this record has, with the line-ups each has in the range
        LineupRecord.Summary s;
        Dictionary<string, string> teams, players;
        List<int> menuIds;
        Dictionary<int, int> counts;
        List<LiveDoc.Version> versions = [];
        var intlTeams = new HashSet<int>();
        if (Live)
        {
            var d = await Quiet(db.KeptDoc<LiveDoc>("lineups", TimeSpan.FromMinutes(5)));
            if (d is null || d.Available == false) return;
            var rows = LineupRecord.LiveRows(d);
            menuIds = rows.Select(x => x.League).Distinct().ToList();
            var liveCountries = Matchday.CompCountries(site, menuIds);
            var liveIntl = menuIds.Where(id => site.Comp(id)?.Type == "International").ToList();
            var c = q["c"].ToString();
            Filter = Matchday.KnownFilter(c, site, liveCountries) ? c : "all";
            var since = days is { } dd ? now - TimeSpan.FromDays(dd) : DateTimeOffset.MinValue;
            counts = [];
            foreach (var x in rows) if (x.Time >= since) counts[x.League] = counts.GetValueOrDefault(x.League) + 1;
            s = LineupRecord.LiveSummary(d, rows, days, Matchday.FilterComps(Filter, liveCountries, liveIntl), tz, Shown, now);
            (teams, players) = (d.Teams ?? [], d.Players ?? []);
            versions = d.Versions ?? [];
            // a national team: one with a line-up in a national team competition
            intlTeams = rows.Where(x => site.Comp(x.League)?.Type == "International").Select(x => x.Team).ToHashSet();
        }
        else
        {
            // the history is added up in the database, for the range and competitions chosen
            var all = Matchday.CompCountries(site, site.Competitions.Keys.Select(int.Parse).Order());
            var c = q["c"].ToString();
            var chosen = Matchday.KnownFilter(c, site, all) ? c : "all";
            var ids = Matchday.FilterComps(chosen, all, []);
            var ask = new Dictionary<string, object?> { ["p_limit"] = Shown };
            if (days is { } dd) ask["p_days"] = dd;
            if (ids is not null) ask["p_leagues"] = ids;
            var d = await Quiet(db.KeptAsk<HistorySummaryDoc>("site_lineup_history", ask, TimeSpan.FromMinutes(5)));
            if (d is null || d.Available == false) return;
            menuIds = [.. d.Leagues ?? []];
            Filter = chosen;
            counts = (d.Scope ?? []).ToDictionary(kv => int.Parse(kv.Key), kv => kv.Value ?? 0);
            s = LineupRecord.HistorySummary(d);
            (teams, players) = (d.Teams ?? [], d.Players ?? []);
        }
        var countries = Matchday.CompCountries(site, menuIds);
        var intl = Live ? menuIds.Where(id => site.Comp(id)?.Type == "International").ToList() : [];
        var total = counts.Values.Sum();
        Menu = ClubTable.Menu(site, countries, Filter, value => Matchday.FilterComps(value, countries, intl) is { } ids ? ids.Sum(id => counts.GetValueOrDefault(id)) : total, Titles, intl);
        if (s.N == 0) { State = !Live && !s.Any ? "waiting" : s.Any ? "none" : "empty"; return; }
        State = "ok";
        Step = s.Step;

        string Team(int id) => site.Teams.GetValueOrDefault(id.ToString()) ?? teams.GetValueOrDefault(id.ToString()) ?? $"Team {id}";
        string Player(int id) => players.GetValueOrDefault(id.ToString()) ?? $"Player {id}";
        string TeamHref(int id) => intlTeams.Contains(id) ? TheCornerFC.Web.Site.Menu.PageHref("nation", site.NationPages?.GetValueOrDefault(id.ToString()) ?? Team(id)) : $"/club/{id}";
        var years = s.First![..4] != s.Last![..4];
        string DateOf(string day) => $"{int.Parse(day[8..])} {Months[int.Parse(day[5..7]) - 1]}{(years ? $" {day[..4]}" : "")}";
        var top = s.Counts.Max();
        var firstAny = Array.FindIndex(s.Counts, x => x > 0);
        var lo = Math.Min(6, firstAny);
        ClubRow Club(LineupRecord.Group g) => new(g.Key, Team(g.Key), TeamHref(g.Key), g.N, LineupRecord.Of11((double)g.Correct / g.N), LineupRecord.ShareText(g.Perfect, g.N));

        CardsShown =
        [
            ("Line-ups", Js.Num(s.N), $"From {Js.Num(s.Matches)} matches, {DateOf(s.First)} to {DateOf(s.Last)}"),
            ("Named correctly", LineupRecord.Of11((double)s.Correct / s.N), $"{Js.Num(s.Correct)} of {Js.Num(11L * s.N)} starters ({LineupRecord.ShareText(s.Correct, 11.0 * s.N)})"),
            ("Perfect XIs", Js.Num(s.Perfect), $"All 11 right in {LineupRecord.ShareText(s.Perfect, s.N)} of line-ups"),
            ("Right position", LineupRecord.ShareText(s.RolesRight, s.RolesKnown), "Correct starters also put where they played"),
        ];
        Sample = s.N < 200 ? $"Very early: {Js.Num(s.N)} line-ups is too few to judge the model, so these figures will move a lot."
            : s.N < 1000 ? $"Still a small sample ({Js.Num(s.N)} line-ups): small differences are likely to be luck." : "";
        // how many of the 11 each line-up got
        Spread = Enumerable.Range(0, 11 - lo + 1).Select(i => 11 - i).Select(k => new Bar($"{k} of 11", top != 0 ? Js.RoundInt(100.0 * s.Counts[k] / top) : 0,
            $"{k} of 11 right: {s.Counts[k]} line-ups", $"{s.Counts[k]} · {LineupRecord.ShareText(s.Counts[k], s.N)}")).ToList();
        Trend = s.Trend.Select(t =>
        {
            var d = DateTime.ParseExact(t.Day, "yyyy-MM-dd", CultureInfo.InvariantCulture);
            var label = s.Step == "month" ? $"{Months[d.Month - 1]} {d.Year}"
                : $"{(s.Step == "week" ? "w/c " : "")}{Weekdays[(int)d.DayOfWeek]} {d.Day} {Months[d.Month - 1]}{(years ? $" {d.Year.ToString()[2..]}" : "")}";
            var avg = (double)t.Correct / t.N;
            return new Bar(label, Js.RoundInt(100 * avg / 11), $"{label}: {LineupRecord.Of11(avg)} from {t.N} line-ups, {t.Perfect} perfect", Js.ToFixed(avg, 1), t.N.ToString());
        }).ToList();
        LinesShown = LineupRecord.Lines.Select((name, i) =>
        {
            double starters = s.Lines.ElementAtOrDefault(2 * i), hit = s.Lines.ElementAtOrDefault(2 * i + 1);
            return new LineView(name, starters, hit, LineupRecord.ShareText(hit, starters), Js.RoundInt((starters != 0 ? hit / starters : 0) * 60));
        }).ToList();
        Timing = (s.Timing ?? []).Select(t => new TimingView(t.Label, t.N, t.N != 0 ? LineupRecord.Of11((double)t.Correct / t.N) : "–", LineupRecord.ShareText(t.Perfect, t.N))).ToList();
        Comps = s.Comps.Select((g, i) => (g, i)).OrderBy(t => t.g, Comparer<LineupRecord.Group>.Create((a, b) =>
            {
                if (b.N != a.N) return b.N - a.N;
                var d = (double)b.Correct / b.N - (double)a.Correct / a.N;
                return Math.Sign(d);
            })).ThenBy(t => t.i).Select(t => t.g)
            .Select(g => new CompView(g.Key, site.CompLabel(g.Key), g.Key.ToString() == Filter, g.N, LineupRecord.Of11((double)g.Correct / g.N),
                LineupRecord.ShareText(g.Perfect, g.N), LineupRecord.ShareText(g.Right ?? 0, g.Known))).ToList();
        var extremes = LineupRecord.ClubExtremes(s.Clubs);
        ClubsShown = (extremes?.Easiest.Select(Club).ToList(), extremes?.Hardest.Select(Club).ToList(),
            s.Clubs.Select((g, i) => (g, i)).OrderBy(t => Team(t.g.Key), Js.Compare).ThenBy(t => t.i).Select(t => Club(t.g)).ToList());
        List<TallyView> Tally(List<LineupRecord.Tally> list) => list.Select((x, i) => (x, i))
            .OrderByDescending(t => t.x.Times).ThenBy(t => Player(t.x.Player), Js.Compare).ThenBy(t => t.i).Take(15)
            .Select(t => new TallyView(t.x.Player, Player(t.x.Player), Team(t.x.Team), t.x.Times)).ToList();
        Missed = Tally(s.Missed);
        Wrong = Tally(s.Wrong);
        MissedTotal = s.MissedTotal;
        Versions = (s.Versions ?? []).Select(g =>
        {
            var v = g.Key >= 0 && g.Key < versions.Count ? versions[g.Key] : null;
            var reg = v?.Registered is { } rs ? DateTimeOffset.Parse(rs, CultureInfo.InvariantCulture).UtcDateTime : (DateTime?)null;
            return new VersionView($"v{g.Key + 1}", v?.Name is { Length: > 0 } nm ? nm : "unknown", reg is { } rd ? $"{rd.Day} {Months[rd.Month - 1]} {rd.Year}" : "",
                g.N, LineupRecord.Of11((double)g.Correct / g.N), LineupRecord.ShareText(g.Perfect, g.N));
        }).ToList();
        Rows = s.Rows.Select(x => new RowView(DateOf(x.Day), Team(x.Team), TeamHref(x.Team), x.Home, Team(x.Opponent), site.CompLabel(x.League), x.Correct,
            string.Join(", ", x.Missed.Select(Player)))).ToList();
        // more to list, unless the database has already sent all it will (1,000 at most)
        if (s.N > s.Rows.Count && s.Rows.Count >= Shown && Shown < 1000) More = (s.N - s.Rows.Count, Shown + LineupRecord.Page);
        Excluded = s.Excluded;
    }

    // this page with some of its choices changed (a default is left out; the number listed starts again)
    public string Address(string? src = null, string? r = null, string? c = null, double? n = null)
    {
        src ??= Live ? "live" : "history";
        r ??= Range;
        c ??= Filter;
        var q = new Dictionary<string, string>();
        if (c != "all") q["c"] = c;
        if (src != "live") q["src"] = src;
        if (r != "all") q["r"] = r;
        if (n is { } x && x != 0) q["n"] = x.ToString(CultureInfo.InvariantCulture);
        return q.Count > 0 ? "?" + Markup.Query(q) : Request.Path.Value!;
    }
    public Dictionary<string, string> Keep()
    {
        var k = new Dictionary<string, string>();
        if (!Live) k["src"] = "history";
        if (Range != "all") k["r"] = Range;
        return k;
    }
}
