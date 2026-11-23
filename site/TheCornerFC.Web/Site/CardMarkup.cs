using Microsoft.AspNetCore.Html;

namespace TheCornerFC.Web.Site;

// What the match card partials are drawn from
public sealed record MatchHeadModel(Cards.Side Home, Cards.Side Away, string Status, int? Hg, int? Ag, int? PenH, int? PenA,
    double? HomeXg, double? AwayXg, string? Likely, string? Source, IHtmlContent Meta, IHtmlContent? Right = null);
// (Page: the card is the match's own page, its panels open and no link to itself)
public sealed record MatchCardModel(Cards.View M, string When = "time", bool Lineups = true, IHtmlContent? Extra = null, bool Page = false);
public sealed record ProbBarsModel(int[] Probs, int[]? Market = null, bool Diff = false);
// A fantasy page's React part, and what the server draws before it runs (_OwnerIsland)
public sealed record OwnerIslandModel(string Island, string BodyId, string Label, object Props, string? Why = null);
// The invitation to Beat the Model or Fantasy points on a list page (_PlayBanner)
public sealed record PlayBannerModel(string Label, string Text, string Href, string Go, string SignedInGo)
{
    public static readonly PlayBannerModel Game = new("Beat the Model", "Predict every Premier League score this round and try to beat our model.", "/beat-the-model", "Play Beat the Model", "Make your picks");
    public static readonly PlayBannerModel Points = new("Fantasy points", "Every Premier League player's expected fantasy points for the next 10 rounds.", "/fantasy-points", "See Fantasy points", "See Fantasy points");
}
