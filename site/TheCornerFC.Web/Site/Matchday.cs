using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using TheCornerFC.Web.Data;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Site;

// Which days have matches (site_match_days): [day on the visitor's calendar, competition, matches],
// the competitions with matches, and the national team competitions [id, matches]
public sealed record MatchDays(JsonElement[][] Days, int[] Leagues, int[][] Intl)
{
    public IEnumerable<(string Day, int League)> Each() => Days.Select(d => (d[0].GetString()!, d[1].GetInt32()));
}

// The Matches page (web/src/lib/matchday.ts): a day at a time on the visitor's own calendar, or,
// for one competition, a round at a time. The days are worked out in the visitor's time zone.
public static partial class Matchday
{
    // ---- Days in a time zone. A day in the address as JavaScript reads one: any month's 29th to
    // 31st is taken, running on into the next month (30 Feb is 2 Mar)
    public static bool IsDay(string? d)
    {
        if (d is null || !DayRe().IsMatch(d)) return false;
        int y = int.Parse(d[..4]), m = int.Parse(d[5..7]), day = int.Parse(d[8..10]);
        return y >= 1 && m is >= 1 and <= 12 && day is >= 1 and <= 31;
    }
    static DateTime Parse(string day) =>
        new DateTime(int.Parse(day[..4]), int.Parse(day[5..7]), 1, 0, 0, 0, DateTimeKind.Utc).AddDays(int.Parse(day[8..10]) - 1);
    static string Text(DateTime d) => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    public static string AddDays(string day, int n) => Text(Parse(day).AddDays(n));

    static readonly string[] Weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], Months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    // "Sat 10 Oct" for a calendar day
    public static string DayName(string day) { var d = Parse(day); return $"{Weekdays[(int)d.DayOfWeek]} {d.Day} {Months[d.Month - 1]}"; }
    static string ShortDay(string day) { var d = Parse(day); return $"{d.Day} {Months[d.Month - 1]}"; }

    // the instant that day starts there (midnight on its clocks): found as the Svelte site finds it,
    // stepping back by the zone's offset, again in case the offset changes that night
    public static DateTimeOffset DayStart(string day, string tz)
    {
        var zone = TimeZoneInfo.FindSystemTimeZoneById(tz);
        var want = new DateTimeOffset(Parse(day));
        var at = want;
        for (var i = 0; i < 3; i++) at = want - zone.GetUtcOffset(at);
        return at;
    }
    public static string LocalDay(DateTimeOffset at, string tz) => Times.LocalDay(at, tz);
    static DateTimeOffset At(string iso) => DateTimeOffset.Parse(iso, CultureInfo.InvariantCulture);

    public static List<string> DaysWith(MatchDays md, IReadOnlyCollection<int>? ids) =>
        md.Each().Where(x => ids is null || ids.Contains(x.League)).Select(x => x.Day).Distinct().OrderBy(d => d, StringComparer.Ordinal).ToList();
    // Today if anything is on, otherwise the nearest upcoming day with matches
    public static string DefaultDay(MatchDays md, string today)
    {
        var days = DaysWith(md, null);
        if (days.Contains(today)) return today;
        return days.FirstOrDefault(d => string.CompareOrdinal(d, today) > 0) ?? days.LastOrDefault() ?? today;
    }

    // ---- The competition menu over the competitions with matches (cups under their country, the
    // European cups and the national team competitions in groups of their own)
    static int OrderOf(int id) { var i = Names.GroupOrder.ToList().IndexOf(id); return i == -1 ? 999 : i; }
    public static int GroupOrderOf(int id) => OrderOf(id);
    public static List<Country> CompCountries(SiteDoc site, IEnumerable<int> ids)
    {
        var byCountry = new List<(string Name, List<int> Ids)>();
        foreach (var id in ids.Distinct())
        {
            if (site.Comp(id) is not { } c || c.Country == "World") continue;
            var name = c.Country.Replace('-', ' ');
            var k = byCountry.FindIndex(x => x.Name == name);
            if (k < 0) byCountry.Add((name, [id])); else byCountry[k].Ids.Add(id);
        }
        int Rank(string n) { var i = Names.CountryFirst.ToList().IndexOf(n); return i == -1 ? 99 : i; }
        // leagues before cups, then the page's usual order
        int ByOrder(int a, int b)
        {
            var la = site.Comp(a)!.Type != "League" ? 1 : 0;
            var lb = site.Comp(b)!.Type != "League" ? 1 : 0;
            return la != lb ? la - lb : OrderOf(a) != OrderOf(b) ? OrderOf(a) - OrderOf(b) : a - b;
        }
        return byCountry.Select(x => new Country(x.Name, x.Ids.OrderBy(i => i, Comparer<int>.Create(ByOrder)).ToList(),
                Names.CountryFirst.Contains(x.Name) ? null : Names.RegionOf(x.Name)))
            .OrderBy(c => Rank(c.Name)).ThenBy(c => c.Name, Js.Compare).ToList();
    }

    // a menu choice this page knows: a competition, country or region it has, or a cup group
    public static bool KnownFilter(string? f, SiteDoc site, List<Country> countries)
    {
        if (string.IsNullOrEmpty(f)) return false;
        if (f == "all") return true;
        if (Digits(f)) return site.Competitions.ContainsKey(f);
        var rest = f.Length >= 2 ? f[2..] : "";
        if (f.StartsWith("c:")) return countries.Any(c => c.Name == rest);
        if (f.StartsWith("r:")) return Names.Regions.Contains(rest);
        return (f.StartsWith("e:") || f.StartsWith("i:")) && (rest == "all" || (Digits(rest) && site.Competitions.ContainsKey(rest)));
    }
    static bool Digits(string s) => s.Length > 0 && s.All(char.IsAsciiDigit);
    static int Num(string s) => int.TryParse(s, NumberStyles.None, CultureInfo.InvariantCulture, out var n) ? n : -1;

    // Competition ids for a choice: null = all
    public static List<int>? FilterComps(string f, List<Country> countries, List<int> intl)
    {
        if (f == "all") return null;
        if (f == "e:all") return [.. Names.EuroCups];
        if (f == "k:all") return [.. Names.DomesticCups];
        if (f == "i:all") return intl;
        if (f.StartsWith("e:") || f.StartsWith("k:") || f.StartsWith("i:")) return [Num(f[2..])];
        if (f.StartsWith("c:")) return countries.FirstOrDefault(c => c.Name == f[2..])?.Leagues.ToList() ?? [];
        if (f.StartsWith("r:")) return countries.Where(c => c.Region == f[2..]).SelectMany(c => c.Leagues).ToList();
        return [Num(f)];
    }
    // The competition a choice picks on its own (a league, one European cup, one international
    // competition), or null: such a page goes a round at a time
    public static int? SingleComp(string f) =>
        Digits(f) ? Num(f) : SingleCupRe().IsMatch(f) ? Num(f[2..]) : null;

    // ---- Rounds: a competition's rounds in date order. Group stages (cup rounds named after the
    // group) go by week instead, one "Group stage" entry per week.
    static readonly TimeSpan RoundWindow = TimeSpan.FromDays(4); // a match more than 4 days from its round's middle was rearranged
    public sealed record Round(string Key, string Label, List<Match> Matches, DateTimeOffset Mid, DateTimeOffset First, DateTimeOffset Last, bool Pending);
    public static List<Round> MatchRounds(List<Match> matches, string tz)
    {
        var byKey = new List<(string Key, string Label, List<Match> Ms)>();
        foreach (var m in matches)
        {
            if (m.Status == "PST") continue; // back under its new date once rescheduled
            var key = m.Round ?? "";
            var label = Cards.RoundName(key);
            if (key == "" || key.StartsWith("Group "))
            {
                var day = LocalDay(At(m.Kickoff), tz);
                var dow = ((int)Parse(day).DayOfWeek + 6) % 7;
                key = $"w:{AddDays(day, -dow)}"; // that week's Monday
                label = "Group stage";
            }
            var k = byKey.FindIndex(x => x.Key == key);
            if (k < 0) byKey.Add((key, label, [m])); else byKey[k].Ms.Add(m);
        }
        return byKey.Select(r =>
        {
            var ms = r.Ms.Select((m, i) => (m, i)).OrderBy(t => t.m.Kickoff, Js.Compare).ThenBy(t => t.i).Select(t => t.m).ToList();
            var times = ms.Select(m => At(m.Kickoff)).ToList();
            var mid = times[times.Count / 2];
            var own = times.Where(t => (t - mid).Duration() <= RoundWindow).ToList(); // its scheduled dates
            // still to come: a match in its own window that hasn't been played (or called off)
            var pending = ms.Any(m => !ClubData.Finished.Contains(m.Status) && !ClubData.NoGame.Contains(m.Status) && (At(m.Kickoff) - mid).Duration() <= RoundWindow);
            return new Round(r.Key, r.Label, ms, mid, own.Min(), own.Max(), pending);
        }).Select((r, i) => (r, i)).OrderBy(t => t.r.Mid).ThenBy(t => t.i).Select(t => t.r).ToList();
    }
    // The round to show: the one on a day asked for (or the next after it), else the one on now or
    // next up (the first with matches still to play, else the last)
    public static Round? PickRound(List<Round> rounds, string? day, string tz)
    {
        if (rounds.Count == 0) return null;
        var asked = day is not null ? rounds.FirstOrDefault(r => string.CompareOrdinal(LocalDay(r.Last, tz), day) >= 0) : null;
        return asked ?? rounds.FirstOrDefault(r => r.Pending) ?? rounds[^1];
    }
    public static string RoundDates(Round r, string tz)
    {
        string a = ShortDay(LocalDay(r.First, tz)), b = ShortDay(LocalDay(r.Last, tz));
        return a == b ? a : $"{a} – {b}";
    }

    [GeneratedRegex(@"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")] private static partial Regex DayRe();
    [GeneratedRegex(@"^[ei]:[0-9]+$")] private static partial Regex SingleCupRe();
}
