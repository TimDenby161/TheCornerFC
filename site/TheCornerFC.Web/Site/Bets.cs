using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TheCornerFC.Web.Site;

// The paper simulation (web/src/lib/bets.ts): bets the model would take where it disagrees with the
// bookmakers enough, at a UK bookmaker's recorded price, with a flat paper stake. No real money.
// "bets" (one of the administrator's documents) holds the rules and every bet; everything on the two
// betting pages is counted from it here.
public sealed record Bet(int Id, string Strategy, int Fixture, string Kickoff, int League, string Market, string Selection,
    [property: JsonPropertyName("model_prob")] double ModelProb, [property: JsonPropertyName("fair_prob")] double? FairProb, double Odds,
    [property: JsonPropertyName("closing_odds")] double? ClosingOdds, double? Clv, string? Result, double? Profit, string Home, string Away,
    [property: JsonPropertyName("home_id")] int? HomeId, [property: JsonPropertyName("away_id")] int? AwayId, string? Score, bool Cautious,
    // a national team match (true, or 1)
    JsonElement? Intl = null)
{
    public bool IsIntl => Intl is { } e && (e.ValueKind == JsonValueKind.True || (e.ValueKind == JsonValueKind.Number && e.GetDouble() != 0));
    public DateTimeOffset At => DateTimeOffset.Parse(Kickoff, CultureInfo.InvariantCulture);
}
public sealed record BetsDoc(BetRules Rules, List<Bet> Bets);
public sealed record BetRules([property: JsonPropertyName("min_edge")] double MinEdge, [property: JsonPropertyName("max_odds")] double MaxOdds,
    [property: JsonPropertyName("stake_gbp")] double? StakeGbp, double? Bank);

public static class Bets
{
    public static readonly Dictionary<string, string> SelLabels = new() { ["Home"] = "Home win", ["Draw"] = "Draw", ["Away"] = "Away win", ["Yes"] = "Both score", ["No"] = "Not both score" };
    public static readonly string[] Markets = ["1X2", "OU15", "OU25", "OU35", "OU45", "BTTS"];

    // Each kind of bet placed once per match (result, goal line, both teams score): when both runs
    // bet it, the night-before bet (placed first) counts
    static string Kind(Bet b) => $"{b.Fixture}|{(b.Market.StartsWith("OU", StringComparison.Ordinal) ? "OU" : b.Market)}";
    public static List<Bet> OnePerPick(List<Bet> bets)
    {
        var early = bets.Where(b => b.Strategy == "early").Select(Kind).ToHashSet();
        return bets.Where(b => b.Strategy == "early" || !early.Contains(Kind(b))).ToList();
    }
    // Bets on the strategy / market / cautious choices, before the competition menu
    public sealed record Choices(string Strategy, string Market, string View);
    public static List<Bet> Scope(List<Bet> bets, Choices ch) =>
        (ch.Strategy == "all" ? OnePerPick(bets) : bets).Where(b =>
            (ch.Strategy == "all" || b.Strategy == ch.Strategy) && (ch.Market == "all" || b.Market == ch.Market) && (ch.View == "all" || b.Cautious)).ToList();

    public sealed record Summary(int Placed, int Settled, int Pending, double AtRisk, int Wins, double Profit, double Staked, double? Roi, double? Beat);
    public static Summary Summarise(List<Bet> bets, double stake)
    {
        var settled = bets.Where(b => b.Result is "win" or "loss").ToList();
        var clvs = settled.Where(b => b.Clv is not null).Select(b => b.Clv!.Value).ToList();
        double sum = 0;
        foreach (var b in settled) sum += b.Profit ?? 0; // (added in order, as JavaScript's reduce)
        var profit = stake * sum;
        var staked = stake * settled.Count;
        var pending = bets.Count(b => b.Result is null);
        return new(bets.Count, settled.Count, pending, stake * pending, settled.Count(b => b.Result == "win"), profit, staked,
            staked != 0 ? profit / staked : null,
            // took better odds than the last price before kickoff
            clvs.Count > 0 ? (double)clvs.Count(c => c > 0) / clvs.Count : null);
    }
    // The bank after each settled bet, oldest first: bet id -> bank
    public static Dictionary<int, double> BankAfter(List<Bet> bets, double stake, double bank)
    {
        var after = new Dictionary<int, double>();
        var running = bank;
        foreach (var b in bets.Where(b => b.Result is not null).OrderBy(b => b.At).ThenBy(b => b.Id))
        {
            running += stake * (b.Profit ?? 0);
            after[b.Id] = running;
        }
        return after;
    }

    // ---- Words and money: £1,234.50, as en-GB writes it to two places
    static string Pounds(double x)
    {
        var text = Js.ToFixed(Math.Abs(x), 2);
        var dot = text.IndexOf('.');
        return $"{long.Parse(text[..dot], CultureInfo.InvariantCulture).ToString("N0", Js.British)}{text[dot..]}";
    }
    public static string Gbp(double? x) => x is not { } v ? "–" : $"{(v < 0 ? "−" : "")}£{Pounds(v)}";
    public static string SignedGbp(double x) => $"{(x > 0 ? "+" : x < 0 ? "−" : "")}£{Pounds(x)}";
    public static string TipLabel(Bet b) => b.Market switch
    {
        "1X2" => b.Selection == "Draw" ? "Draw" : $"{(b.Selection == "Home" ? b.Home : b.Away)} to win",
        "BTTS" => b.Selection == "Yes" ? "Both teams to score: Yes" : "Both teams to score: No",
        _ => $"{b.Selection} goals",
    };
    // A paper bet's model probability, market fair probability and the difference, in whole points,
    // as they were when it was taken (the match card's bars show the latest prices)
    public static string BetProbs(Bet b)
    {
        var model = Js.RoundInt(100 * b.ModelProb);
        int? fair = b.FairProb is { } f ? Js.RoundInt(100 * f) : null;
        var diff = fair is not { } fr ? "" : $" · difference {(model >= fr ? "+" : "−")}{Math.Abs(model - fr)} pts";
        return $"When taken: model {model}% · market fair {(fair is { } x ? $"{x}%" : "–")}{diff}";
    }
    // the teams whose badge a bet carries: the one it backs, or both for a draw or goals bet
    public static List<(int Id, string Name)> Teams(Bet b)
    {
        (int? Id, string Name)[] list = b.Market == "1X2" && b.Selection != "Draw"
            ? [b.Selection == "Home" ? (b.HomeId, b.Home) : (b.AwayId, b.Away)]
            : [(b.HomeId, b.Home), (b.AwayId, b.Away)];
        return list.Where(t => t.Id is { } id && id != 0).Select(t => (t.Id!.Value, t.Name)).ToList();
    }
}
