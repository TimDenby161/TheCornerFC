using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Pages;

// Matches: a day at a time on the visitor's own calendar, by competition; or, for one competition,
// a round at a time, that round's matches by day (web/src/routes/(app)/matches)
public sealed class MatchesModel(Database db, TimeProvider clock) : PageModel
{
    public sealed record Group(string Key, string Name, List<Cards.View> Cards);
    public sealed record RoundOption(string Day, string Label);

    public string Mode { get; private set; } = "days"; // days or rounds
    public string Filter { get; private set; } = "all";
    public FilterMenuModel Menu { get; private set; } = null!;
    public string? Title { get; private set; }
    public string Day { get; private set; } = "";
    public string DayName { get; private set; } = "";
    public string? Prev { get; private set; }
    public string? Next { get; private set; }
    public (string Day, string Name)? Upcoming { get; private set; }
    public List<RoundOption> Rounds { get; private set; } = [];
    public List<Group> Groups { get; private set; } = [];

    static readonly MenuTitles Titles = new(
        "All competitions", c => $"All {c} matches", r => $"All matches in {r}",
        "Champions League, Europa League and Conference League matches", n => $"{n} matches",
        Intl: "National team matches: World Cup, qualifiers, Nations League, friendlies and others");

    public async Task OnGet()
    {
        var visitor = Visitor.Of(HttpContext);
        var tz = visitor.Zone.Tz;
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var rankingsTask = db.KeptDoc<Rankings>("rankings");
        // which days and competitions have matches, on this visitor's calendar
        var mdTask = db.KeptAsk<MatchDays>("site_match_days", new { p_tz = tz }, TimeSpan.FromMinutes(5));
        await Task.WhenAll(siteTask, rankingsTask, mdTask);
        var (site, md) = (siteTask.Result, mdTask.Result);
        var ranks = Clubs.From(rankingsTask.Result).GroupBy(c => c.Team).ToDictionary(g => g.Key, g => g.Last());
        var countries = Matchday.CompCountries(site, md.Leagues);
        var intl = md.Intl.Select(x => x[0]).ToList();
        var c = Request.Query["c"].ToString();
        Filter = Matchday.KnownFilter(c, site, countries) ? c : "all";
        var d = Request.Query["d"].ToString();
        var asked = Matchday.IsDay(d) ? d : null;
        var now = clock.GetUtcNow();
        var today = Matchday.LocalDay(now, tz);
        Menu = ClubTable.Menu(site, countries, Filter, null, Titles, intl);
        if (!visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        ViewData["TabHead"] = TabHead.For("Matches", "matches");
        List<Cards.View> CardsOf(IEnumerable<Match> list, bool paywall) => list.Select(m => Cards.Of(site, ranks, m, paywall, now)).ToList();

        // One competition: a round at a time, that round's matches by day
        if (Matchday.SingleComp(Filter) is { } lid)
        {
            var answer = await db.AskAs<MatchesAnswer>(visitor.Token, "site_matches", new { p_leagues = new[] { lid } });
            var rounds = Matchday.MatchRounds(ClubData.MatchRows(site, answer), tz);
            if (Matchday.PickRound(rounds, asked, tz) is { } round)
            {
                var i = rounds.IndexOf(round);
                string? DayOf(int k) => k >= 0 && k < rounds.Count ? Matchday.LocalDay(rounds[k].First, tz) : null;
                Mode = "rounds";
                Title = Menu.Name;
                Day = Matchday.LocalDay(round.First, tz);
                Rounds = rounds.Select(r => new RoundOption(Matchday.LocalDay(r.First, tz), $"{r.Label} · {Matchday.RoundDates(r, tz)}")).ToList();
                Prev = i > 0 ? DayOf(i - 1) : null;
                Next = i < rounds.Count - 1 ? DayOf(i + 1) : null;
                var days = new List<(string Day, List<Match> Ms)>();
                foreach (var m in round.Matches)
                {
                    var day = Matchday.LocalDay(DateTimeOffset.Parse(m.Kickoff), tz);
                    var k = days.FindIndex(x => x.Day == day);
                    if (k < 0) days.Add((day, [m])); else days[k].Ms.Add(m);
                }
                Groups = days.Select(x => new Group($"d:{x.Day}", Matchday.DayName(x.Day), CardsOf(x.Ms, answer.Paywall == true))).ToList();
                return;
            }
        }

        // Otherwise: the day's matches, by competition
        var ids = Matchday.FilterComps(Filter, countries, intl);
        Day = asked ?? Matchday.DefaultDay(md, today);
        DateTimeOffset from = Matchday.DayStart(Day, tz), to = Matchday.DayStart(Matchday.AddDays(Day, 1), tz);
        var dayAnswer = await db.AskAs<MatchesAnswer>(visitor.Token, "site_matches",
            new { p_from = Iso(from), p_to = Iso(to) });
        var shown = ClubData.MatchRows(site, dayAnswer).Where(m => m.Status != "PST" && (ids is null || ids.Contains(m.League))
            && Matchday.LocalDay(DateTimeOffset.Parse(m.Kickoff), tz) == Day).ToList();
        var groups = new List<(int League, List<Match> Ms)>();
        foreach (var m in shown)
        {
            var k = groups.FindIndex(x => x.League == m.League);
            if (k < 0) groups.Add((m.League, [m])); else groups[k].Ms.Add(m);
        }
        Mode = "days";
        Title = Filter == "all" ? null : Menu.Name;
        DayName = $"{Matchday.DayName(Day)}{(Day[..4] == today[..4] ? "" : $" {Day[..4]}")}";
        Prev = Matchday.AddDays(Day, -1);
        Next = Matchday.AddDays(Day, 1);
        // nothing on that day: the next day that has matches in these competitions
        if (shown.Count == 0 && Matchday.DaysWith(md, ids).FirstOrDefault(x => string.CompareOrdinal(x, Day) > 0) is { } up)
            Upcoming = (up, Matchday.DayName(up));
        Groups = groups.OrderBy(g => Matchday.GroupOrderOf(g.League)).ThenBy(g => site.CompLabel(g.League), Js.Compare)
            .Select(g => new Group(g.League.ToString(), site.CompLabel(g.League), CardsOf(g.Ms, dayAnswer.Paywall == true))).ToList();
    }

    // as JavaScript's toISOString writes an instant
    static string Iso(DateTimeOffset t) => t.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", System.Globalization.CultureInfo.InvariantCulture);

    // this page with another day (or round: a round goes by its first day) and the same menu choice
    public string Address(string? day)
    {
        var q = new Dictionary<string, string>();
        if (Filter != "all") q["c"] = Filter;
        if (day is not null) q["d"] = day;
        return q.Count > 0 ? "?" + Markup.Query(q) : Request.Path.Value!;
    }
}
