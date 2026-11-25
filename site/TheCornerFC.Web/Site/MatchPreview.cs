using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// A few plain sentences about a match for its own page (T-091): who is playing, how the two clubs
// are rated, and the model's chances, so a search engine has words to read beside the card. Built
// only from what this visitor's card holds: chances the paywall held back stay out, and so does the
// projected score where it is locked.
public static class MatchPreview
{
    // Where a club stands by Current Strength: among its league's clubs, else among every club
    public sealed record Standing(int Current, int Place, int Of, string Among);

    public static Standing? StandingOf(int team, IReadOnlyList<Club> all, Func<int, string> leagueName)
    {
        var me = all.FirstOrDefault(c => c.Team == team);
        if (me is null) return null;
        var current = Js.RoundInt(me.Current);
        if (me.InLeague && me.League > 0)
        {
            var league = all.Where(c => c.League == me.League && c.InLeague).ToList();
            var name = leagueName(me.League);
            if (league.Count >= 4 && !string.IsNullOrEmpty(name))
                return new(current, league.Count(c => c.Current > me.Current) + 1, league.Count, $"in {The(name)}");
        }
        return new(current, all.Count(c => c.Current > me.Current) + 1, all.Count, "in the world");
    }

    // "the Premier League", but "La Liga", "Serie A", "Ligue 1"
    static string The(string league) =>
        System.Text.RegularExpressions.Regex.IsMatch(league, "^(La |LaLiga|Serie |Ligue |Liga )") ? league : $"the {league}";

    static string Nth(int n) => (n % 100) is 11 or 12 or 13 ? $"{n}th" : (n % 10) switch { 1 => $"{n}st", 2 => $"{n}nd", 3 => $"{n}rd", _ => $"{n}th" };
    static string Strongest(Standing s) => s.Place == 1 ? $"the strongest side {s.Among}" : $"the {Nth(s.Place)}-strongest side {s.Among}";

    public static List<string> Lines(Cards.View v, string competition, string dayUk, string timeUk, Standing? home, Standing? away)
    {
        string h = v.Home.Name, a = v.Away.Name;
        var lines = new List<string>();
        var played = v.Finished && v.Hg is not null && v.Ag is not null;

        if (played)
        {
            var (hg2, ag2) = (v.Hg!.Value, v.Ag!.Value);
            lines.Add(hg2 == ag2 ? $"{h} and {a} drew {hg2}–{ag2} in {The(competition)} on {dayUk}."
                : hg2 > ag2 ? $"{h} beat {a} {hg2}–{ag2} at home in {The(competition)} on {dayUk}."
                : $"{a} won {ag2}–{hg2} away at {h} in {The(competition)} on {dayUk}.");
        }
        else lines.Add($"{h} play {a} in {The(competition)} on {dayUk}, kick-off {timeUk} UK time.");

        if (home is not null && away is not null)
        {
            var gap = home.Current - away.Current;
            var lead = Math.Abs(gap) < 15 ? "barely anything between them" : gap > 0 ? $"{gap} points in {h}'s favour" : $"{-gap} points in {a}'s favour";
            var second = home.Among == away.Among ? $"{a} {(away.Place == 1 ? "the strongest" : Nth(away.Place))} (rated {away.Current:N0})"
                : $"{a} {Strongest(away)} (rated {away.Current:N0})";
            lines.Add($"On current strength, {h} are {Strongest(home)} (rated {home.Current:N0}) and {second}: {lead}.");
        }

        if (v.Probs is { Length: 3 } p)
        {
            var chances = $"{h} {p[0]}%, the draw {p[1]}% and {a} {p[2]}%";
            if (played)
            {
                var outcome = v.Hg > v.Ag ? 0 : v.Hg == v.Ag ? 1 : 2;
                var called = Array.IndexOf(p, p.Max()) == outcome;
                lines.Add($"Before kick-off the model gave {chances}, so the result was {(called ? "the one it rated most likely" : "not the one it rated most likely")}.");
            }
            else
            {
                var top = Array.IndexOf(p, p.Max());
                var verdict = p.Max() < 42 && p.Max() - p.OrderByDescending(x => x).Skip(1).First() < 8 ? "a close call"
                    : top == 1 ? "the draw the most likely single result"
                    : $"{(top == 0 ? h : a)} {(p.Max() >= 60 ? "clear favourites" : "favourites")}";
                lines.Add($"The model gives {chances}, which makes it {verdict}.");
                if (v.Lock is null && v.HomeXg is { } hx && v.AwayXg is { } ax)
                    lines.Add($"Its projected score is {Cards.GoalsText(hx)}–{Cards.GoalsText(ax)}{(v.Likely is { Length: > 0 } l ? $", and the single most likely score {l.Replace('-', '–')}" : "")}.");
            }
        }
        else if (!played && !ClubData.NoGame.Contains(v.Status))
            lines.Add("The model's win, draw and loss chances for this match appear here free 7 days before kick-off, or sooner when it is in its league's next round.");

        return lines;
    }
}
