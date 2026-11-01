using System.Globalization;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// The posts on the Admin area's X page (/admin/posts): each one's words and card, from the same
// public figures the site shows. The administrator publishes by hand: "Open in X" fills in the
// words through X's share address, which is free and needs no API. Only figures a signed-out
// visitor can see go in: never the Admin area's documents, and never fantasy data. Chances, not
// tips; no prices; the brand is written "TheCorner FC".
public static class XPosts
{
    public const int PremierLeague = 39;
    const string UkTime = "Europe/London";

    public sealed record Stat(string Value, string Label);
    public sealed record Chances(string When, string Home, string Away, int H, int D, int A);
    public sealed record Mover(string Name, int Change);
    public sealed record Ranked(string Name, string Comp, int Rating);
    // What the page's script draws, by Kind: stats, chances, movers or ranked
    public sealed record Card(string Kind, string Kicker, string Title, string Foot, List<Stat>? Stats = null, string? Note = null,
        List<Chances>? Matches = null, List<Mover>? Movers = null, List<Ranked>? Clubs = null);
    public sealed record Post(string Key, string Name, string Text, Card Card)
    {
        public string ShareUrl => "https://x.com/intent/post?text=" + Uri.EscapeDataString(Text);
    }

    static string Signed(int v) => v > 0 ? $"+{v}" : v < 0 ? $"−{-v}" : "0";

    // gap: the model's log loss less the bookmakers'; the post never claims more than it shows
    public static Post? Record(PredictionRecordDoc? d, double? gap)
    {
        if (d is not { Total: > 0 and { } total, Right: { } right }) return null;
        var pct = Js.ToFixed(100.0 * right / total, 1);
        var behind = gap is > 0;
        var line = behind ? " Still behind the bookmakers, and the site says so." : "";
        var stats = new List<Stat>
        {
            new(Js.Num(total), "finished matches, each predicted before kick-off"),
            new($"{pct}%", "the result the model made most likely happened"),
        };
        if (d.LogLoss is { } ll) stats.Add(new(Js.ToFixed(ll, 3), "log loss: lower is better"));
        return new("record", "The record",
            $"Every prediction is locked before kick-off and kept. {Js.Num(total)} matches so far, {pct}% right.{line} thecornerfc.com/record",
            new("stats", "The record", "Every prediction locked before kick-off", "Source: thecornerfc.com/record", Stats: stats,
                Note: behind ? $"Still behind the bookmakers, by {Js.ToFixed(gap!.Value, 3)} in log loss. The site says so." : null));
    }

    // The next Premier League round's chances: the first round with most of its matches to come
    public static Post? Round(SiteDoc site, IEnumerable<Match> matches, DateTimeOffset now)
    {
        var ahead = matches.Where(m => m.League == PremierLeague && m.PHome is not null && m.PDraw is not null
            && !ClubData.NoGame.Contains(m.Status) && DateTimeOffset.Parse(m.Kickoff, CultureInfo.InvariantCulture) > now).ToList();
        var rounds = Matchday.MatchRounds(ahead, UkTime);
        if ((rounds.FirstOrDefault(r => r.Matches.Count >= 5) ?? rounds.FirstOrDefault()) is not { } round) return null;
        var rows = round.Matches.OrderBy(m => m.Kickoff, StringComparer.Ordinal).Take(10).Select(m =>
        {
            var p = Cards.ShownProbs(m.PHome!.Value, m.PDraw!.Value);
            return new Chances(UkWhen(m.Kickoff), site.TeamName(m.Home), site.TeamName(m.Away), p[0], p[1], p[2]);
        }).ToList();
        var favourite = rows.MaxBy(r => Math.Max(r.H, r.A))!;
        var closest = rows.MinBy(r => Math.Abs(r.H - r.A))!;
        var words = $"{(favourite.H >= favourite.A ? favourite.Home : favourite.Away)} the clearest favourite at {Math.Max(favourite.H, favourite.A)}%";
        if (Math.Abs(closest.H - closest.A) <= 2) words += $"; {closest.Home} v {closest.Away} too close to call";
        return new("round", round.Label, $"The model's chances for Premier League {round.Label}. {words}. thecornerfc.com/matches",
            new("chances", $"Premier League · {round.Label} · UK times", "The model's chances", "Chances, not tips · thecornerfc.com/matches", Matches: rows));
    }

    static string UkWhen(string kickoff) =>
        TimeZoneInfo.ConvertTime(DateTimeOffset.Parse(kickoff, CultureInfo.InvariantCulture), TimeZoneInfo.FindSystemTimeZoneById(UkTime))
            .ToString("ddd HH:mm", CultureInfo.InvariantCulture);

    // Every Premier League club's rating change over its last six matches
    public static Post? Movers(SiteDoc site, IEnumerable<Club> clubs)
    {
        var rows = clubs.Where(c => c.League == PremierLeague && c.InLeague && c.Form is not null).DistinctBy(c => c.Team)
            .Select(c => new Mover(site.TeamName(c.Team), Js.RoundInt(c.Form!.Value))).OrderByDescending(m => m.Change).ToList();
        if (rows.Count < 4 || rows[0].Change <= 0 || rows[^1].Change >= 0) return null;
        var (first, second, last, nextLast) = (rows[0], rows[1], rows[^1], rows[^2]);
        return new("movers", "Premier League movers",
            $"Club ratings move after every match. Over the last six: {first.Name} {Signed(first.Change)}, {second.Name} {Signed(second.Change)}. {last.Name} {Signed(last.Change)}, {nextLast.Name} {Signed(nextLast.Change)}. thecornerfc.com/clubs",
            new("movers", "Premier League · club ratings · last six matches", $"{first.Name} rising, {last.Name} falling",
                "Rating points gained or lost · thecornerfc.com/clubs", Movers: rows));
    }

    // The ten strongest clubs anywhere, on the one scale
    public static Post? Strongest(SiteDoc site, IEnumerable<Club> clubs)
    {
        var all = clubs.Where(c => c.InLeague).DistinctBy(c => c.Team).OrderByDescending(c => c.Current).ToList();
        if (all.Count < 10) return null;
        var top = all.Take(10).Select(c => new Ranked(site.TeamName(c.Team), site.CompLabel(c.League), Js.RoundInt(c.Current))).ToList();
        return new("strongest", "The strongest clubs",
            $"The ten strongest clubs in the world right now, on one scale with {Js.Num(all.Count - 10)} others. {top[0].Name} top, then {top[1].Name} and {top[2].Name}. thecornerfc.com/clubs",
            new("ranked", $"{Js.Num(all.Count)} clubs, one scale", "The ten strongest clubs in the world right now", "Current rating · thecornerfc.com/clubs", Clubs: top));
    }
}
