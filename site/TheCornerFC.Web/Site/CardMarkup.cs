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
