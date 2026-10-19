namespace TheCornerFC.Web.Site;

// A club's next match as its card shows it (NextMatchCard.svelte)
public sealed record NextMatch(DateTimeOffset Kickoff, bool Live, bool Home, int Opp, string OppName, string Comp, int? Win,
    double? Gf = null, double? Ga = null, string? Proj = null, double? Xi = null, double? Missing = null);
