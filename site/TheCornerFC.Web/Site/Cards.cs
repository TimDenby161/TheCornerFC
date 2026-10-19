using TheCornerFC.Web.Data;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Site;

// A match as its card draws it (web/src/lib/server/matches.ts cardView and matchday.ts): names,
// the strengths beside them, the chances as the bars show them, the key reasons in words, and what
// (if anything) the database held back for subscribers.
public static class Cards
{
    public sealed record Side(int Id, string Name, bool Nation, string? Href, double? Rank);
    public sealed record Reason(string Text, string Size);
    public sealed record Factor(string Label, string Weight, int? Score);
    public sealed record RatingView(int Score, string Label, List<Factor> Factors);
    public sealed record View(int Id, string Kickoff, string? Round, string Status, bool Intl, Side Home, Side Away,
        int? Hg, int? Ag, int? PenH, int? PenA, double? HomeXg, double? AwayXg, string? Likely, string? Source,
        bool Finished, bool Upcoming, int[]? Probs, int[]? Market, string Tag, bool Live, string? Lock,
        bool CanLineups, bool CanDetail, bool CanSquads, List<Reason> Reasons, RatingView? Rating);

    static readonly Dictionary<int, string> RatingLabels = new() { [1] = "Terrible", [2] = "Poor", [3] = "Decent", [4] = "Very good", [5] = "Excellent" };

    // Home, draw and away as whole percentages that add up to 100, as the bars show them
    public static int[] ShownProbs(double home, double draw)
    {
        int h = Js.RoundInt(home * 100), d = Js.RoundInt(draw * 100);
        return [h, d, 100 - h - d];
    }
    // Goals to one decimal, never "0.0" for something the model did count
    public static string GoalsText(double v) { var a = Math.Abs(v); return a == 0 ? "0" : a < 0.05 ? "<0.1" : Js.ToFixed(a, 1); }
    public static string SignedGoals(double v) => v != 0 && Math.Abs(v) < 0.05 ? "≈0" : $"{(v > 0 ? "+" : v < 0 ? "−" : "")}{GoalsText(v)}";
    // One key reason as a phrase and its size; + favours the home side (or, for tendencies, more goals)
    public static Reason? ReasonText(string key, double v, string home, string away)
    {
        string fav = v >= 0 ? home : away, other = v >= 0 ? away : home;
        var text = key switch
        {
            "strength" => $"{fav} rated the stronger side",
            "home_advantage" => $"Home advantage for {fav}",
            "europe_home" => $"Extra home advantage in European ties for {fav}",
            "home_edges" => $"Clubs' home/away records lean to {fav}",
            "absences" => $"More of {other}'s regulars listed as missing",
            "lineups" => $"Predicted line-up rated higher for {fav}",
            "tendencies" => v >= 0 ? "Both sides' games tend to be open" : "Both sides' games tend to be tight",
            _ => null,
        };
        return text is null ? null : new(text, key == "tendencies" ? $"{SignedGoals(v)} total goals" : $"{GoalsText(v)} goals");
    }

    public static View Of(SiteDoc site, IReadOnlyDictionary<int, Club> ranks, Match m, bool paywall, DateTimeOffset now)
    {
        var finished = ClubData.Finished.Contains(m.Status) && m.Hg is not null;
        var upcoming = !finished && !ClubData.Live.Contains(m.Status);
        var intl = m.Intl is > 0;
        Side SideOf(int id, double? rankThen)
        {
            var name = site.TeamName(id);
            // a finished match: the strength going into it; otherwise the club's strength now
            return new(id, name, intl, intl ? Menu.PageHref("nation", site.NationPages?.GetValueOrDefault(id.ToString()) ?? name) : null,
                finished ? rankThen : ranks.TryGetValue(id, out var c) ? c.Current : rankThen);
        }
        Side home = SideOf(m.Home, m.HomeRank), away = SideOf(m.Away, m.AwayRank);
        var probs = m.PHome is { } ph && m.PDraw is { } pd ? ShownProbs(ph, pd) : null;
        var market = m.MHome is { } mh && m.MDraw is { } md && probs is not null ? ShownProbs(mh, md) : null;
        // behind the paywall: the database left the paid fields of a match to come out for this
        // visitor. It decides by the kick-off time (a match that has kicked off is whole), so the
        // card does too
        var kickedOff = DateTimeOffset.Parse(m.Kickoff) <= now;
        var locked = paywall && upcoming && !kickedOff && !ClubData.NoGame.Contains(m.Status);
        var live = ClubData.Live.Contains(m.Status);
        (string Key, string Label, string Weight)[] factors = [("r_winner", "Winner", "30%"), ("r_margin", "Margin", "25%"), ("r_clean_sheets", "Clean sheets", "20%"), ("r_shape", "Shape", "15%"), ("r_goals", "Goals", "10%")];
        int? FactorScore(string k) => k switch { "r_winner" => m.RWinner, "r_margin" => m.RMargin, "r_clean_sheets" => m.RCleanSheets, "r_shape" => m.RShape, _ => m.RGoals };
        return new(m.Id, m.Kickoff, m.Round, m.Status, intl, home, away, m.Hg, m.Ag, m.PenH, m.PenA, m.HomeXg, m.AwayXg, m.Likely, m.Source,
            finished, upcoming, probs, market,
            live ? "Live" : m.Status switch { "PST" => "Postponed", "CANC" => "Cancelled", "ABD" => "Abandoned", _ => ClubData.Finished.Contains(m.Status) ? m.Status : "" },
            live, !locked ? null : probs is not null ? "depth" : "chances",
            // what opens from the card: the line-ups (not while it is being played, nor for a
            // national match once played) and the model's detail
            !locked && !live && !ClubData.NoGame.Contains(m.Status) && (!intl || (!finished && probs is not null)),
            !locked && probs is not null,
            upcoming && !intl && !locked && !ClubData.NoGame.Contains(m.Status),
            upcoming && probs is not null ? m.Reasons.Select(r => ReasonText(r.Key, r.Goals, home.Name, away.Name)).Where(r => r is not null).Select(r => r!).ToList() : [],
            finished && m.Rating is { } rt and > 0 ? new(rt, RatingLabels.GetValueOrDefault(rt, ""), factors.Select(f => new Factor(f.Label, f.Weight, FactorScore(f.Key))).ToList()) : null);
    }

    public static string RoundName(string r) =>
        System.Text.RegularExpressions.Regex.Replace(System.Text.RegularExpressions.Regex.Replace(r, "^Regular Season - ", "Round "), "^League Stage - ", "League phase ");
}
