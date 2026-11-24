namespace TheCornerFC.Web.Site;

// A few plain sentences about a player for his page (T-091), so a search engine has words to read
// beside the figures. Only what his page already shows this visitor: his rank stays out where the
// paywall hides it.
public static class PlayerSummary
{
    static string Nth(int n) => (n % 100) is 11 or 12 or 13 ? $"{n}th" : (n % 10) switch { 1 => $"{n}st", 2 => $"{n}nd", 3 => $"{n}rd", _ => $"{n}th" };
    static string The(string league) =>
        System.Text.RegularExpressions.Regex.IsMatch(league, "^(La |LaLiga|Serie |Ligue |Liga )") ? league : $"the {league}";
    static string Position(string? p) => p switch
    {
        "GK" or "G" or "Goalkeeper" => "goalkeeper", "CB" => "centre-back", "LB" or "RB" => "full-back", "LWB" or "RWB" => "wing-back",
        "DM" => "defensive midfielder", "CM" => "central midfielder", "AM" => "attacking midfielder", "LM" or "RM" => "wide midfielder",
        "LW" or "RW" => "winger", "ST" or "CF" => "striker", "D" or "Defender" => "defender", "M" or "Midfielder" => "midfielder",
        "F" or "Attacker" => "forward", _ => "footballer",
    };

    public static List<string> Lines(string name, string? position, int? age, string? nationality, string? club, string? league,
        string seasonName, int? minutes, int? apps, int? goals, int? assists, bool keeper, int? rank, (int Place, int Of)? leagueRank, bool rankHidden)
    {
        var lines = new List<string>();
        var what = $"{(age is { } a ? $"{a}-year-old " : "")}{Position(position)}";
        var an = "aeiou8".Contains(what[0]) || what.StartsWith("11-") || what.StartsWith("18-");
        var who = $"{name} is a{(an ? "n" : "")} {what}{(nationality is { Length: > 0 } n ? $" from {n}" : "")}";
        lines.Add(club is { Length: > 0 } c ? $"{who}, playing for {c}{(league is { Length: > 0 } l ? $" in {The(l)}" : "")}." : $"{who}.");

        if (minutes is > 0)
        {
            var parts = new List<string> { $"{minutes:N0} league minutes{(apps is { } ap ? $" in {ap} appearance{(ap == 1 ? "" : "s")}" : "")}" };
            if (!keeper)
            {
                if (goals is { } g) parts.Add($"{g} goal{(g == 1 ? "" : "s")}");
                if (assists is { } s) parts.Add($"{s} assist{(s == 1 ? "" : "s")}");
            }
            lines.Add($"In {seasonName} he has {string.Join(", ", parts.Take(parts.Count - 1))}{(parts.Count > 1 ? " and " : "")}{parts[^1]}.");
        }
        else lines.Add($"He has no league minutes yet in {seasonName}.");

        if (!rankHidden && rank is { } r)
            lines.Add(leagueRank is { } lr && league is { Length: > 0 } lg
                ? $"His Ability rank is {r}, the {Nth(lr.Place)} highest of {lr.Of:N0} players in {The(lg)}."
                : $"His Ability rank is {r}.");
        return lines;
    }
}
