using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.AdminArea;

// The paper simulation's open selections (where the model and the market disagree enough for it
// to take one), one per pick, soonest first, grouped by day and competition
// (web/src/routes/(app)/admin/model-vs-market). The administrator's only: the selections are one of
// their documents, not a public row.
public sealed class ModelVsMarketModel(Database db, TimeProvider clock) : PageModel
{
    public sealed record Tile(bool? Ok, string Pill, string Label, string Value, string? Small, List<(string Key, string Value)> Rows, string? Title = null);
    public sealed record Pick(int Id, string Label, string Probs, string Odds, List<(int Id, string Name)> Teams);
    public sealed record MatchTips(int Fixture, Cards.View? Card, string Kickoff, string Home, string Away, bool Intl, List<Pick> Picks);
    public sealed record CompTips(string Key, string Name, int Count, List<MatchTips> Matches);
    public sealed record DayTips(string Key, string Name, int Count, List<CompTips> Comps);

    public List<Tile> Tiles { get; private set; } = [];
    public List<DayTips> Days { get; private set; } = [];

    public async Task<IActionResult> OnGet()
    {
        ViewData["TabHead"] = TabHead.For("Model vs Market", "tips");
        var visitor = Visitor.Of(HttpContext);
        var tz = visitor.Zone.Tz;
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var rankingsTask = db.KeptDoc<Rankings>("rankings");
        var docTask = TheCornerFC.Web.Site.Admin.Doc<BetsDoc>(db, visitor.Token, "bets");
        var statsTask = Quiet(db.KeptDoc<StatsDoc>("stats", TimeSpan.FromMinutes(5)));
        await Task.WhenAll(siteTask, rankingsTask, docTask, statsTask);
        if (docTask.Result.Refused) return NotFound();
        var (site, doc, stats) = (siteTask.Result, docTask.Result.Doc, statsTask.Result);
        var stake = doc?.Rules.StakeGbp ?? 10;
        var picks = Bets.OnePerPick(doc?.Bets ?? []);
        var now = clock.GetUtcNow();
        var tips = picks.Where(b => b.Result is null && b.At > now).OrderBy(b => b.At).ThenBy(b => b.Fixture).ThenBy(b => b.Id).ToList();
        // the top of each card is the match as on the Matches page
        var ids = tips.Select(b => b.Fixture).Distinct().ToArray();
        var answer = ids.Length > 0 ? await Quiet(db.AskAs<MatchesAnswer>(visitor.Token, "site_matches", new { p_ids = ids })) : null;
        var ranks = Clubs.From(rankingsTask.Result).GroupBy(c => c.Team).ToDictionary(g => g.Key, g => g.Last());
        var cards = (answer is not null ? ClubData.MatchRows(site, answer) : []).Select(m => Cards.Of(site, ranks, m, answer!.Paywall == true, now))
            .GroupBy(v => v.Id).ToDictionary(g => g.Key, g => g.Last());

        // How the model has done against the market: accuracy on every market with odds (last 12
        // months), and the settled paper selections' closing-price record and simulated profit
        var st = stats?.Ranges.GetValueOrDefault("365d")?.GetValueOrDefault("all");
        var ms = st?.Markets?.Values.ToList() ?? [];
        var s = Bets.Summarise(picks.Where(b => b.Result is "win" or "loss").ToList(), stake);
        if (ms.Count > 0 && st is not null)
        {
            var better = ms.Count(m => (m.ModelLl ?? 9) < (m.CloseLl ?? 0));
            var ahead = better > ms.Count / 2.0;
            List<(string, string)> rows = [("Matches with odds", Js.Num(ms.Max(m => m.N)))];
            if (st.Market is { } mk) rows.AddRange([("Right result, model", Home.PctText(mk.ModelCorrect ?? 0)), ("Right result, market", Home.PctText(mk.MarketCorrect ?? 0))]);
            Tiles.Add(new(ahead, ahead ? "Ahead" : "Behind", "Model vs Market", better.ToString(), $"of {ms.Count} markets", rows,
                "Bet markets where the model's log loss beat the closing market fair price, last 12 months"));
        }
        Tiles.Add(new(s.Beat is { } bt ? bt >= 0.5 : null, s.Beat is not { } b2 ? "No data" : b2 >= 0.5 ? "Above 50%" : "Below 50%", "Beat closing price",
            s.Beat is { } b3 ? Home.PctText(b3) : "–", null, [("Settled selections", s.Settled.ToString()), ("Target", "Over 50%")],
            "Share of paper selections taken at better odds than the last price before kickoff. Staying above 50% over a large sample would suggest real mispricing; it is not proof on its own"));
        Tiles.Add(new(s.Settled != 0 ? s.Profit >= 0 : null, s.Settled != 0 && s.Roi is { } roi ? $"{(roi > 0 ? "+" : "")}{Js.ToFixed(100 * roi, 1)}% return" : "No data", "Simulated profit",
            s.Settled != 0 ? $"{(s.Profit >= 0 ? "+" : "−")}{Bets.Gbp(Math.Abs(s.Profit))}" : "–", null,
            [("Won", s.Settled != 0 ? $"{s.Wins} of {s.Settled}" : "–"), ("Strike rate", s.Settled != 0 ? Home.PctText((double)s.Wins / s.Settled) : "–")]));

        Days = tips.GroupBy(b => Matchday.LocalDay(b.At, tz)).Select(day => new DayTips($"d:{day.Key}", Matchday.DayName(day.Key), day.Count(),
            day.GroupBy(b => b.League).Select(g => g.Key).OrderBy(Matchday.GroupOrderOf).ThenBy(id => site.CompLabel(id), Js.Compare).Select(id =>
            {
                var list = day.Where(b => b.League == id).ToList();
                return new CompTips($"c:{day.Key}|{id}", site.CompLabel(id), list.Count, list.GroupBy(b => b.Fixture).Select(bs =>
                {
                    var f = bs.First();
                    return new MatchTips(f.Fixture, cards.GetValueOrDefault(f.Fixture), f.Kickoff, f.Home, f.Away, f.IsIntl,
                        bs.Select(b => new Pick(b.Id, Bets.TipLabel(b), Bets.BetProbs(b), Js.ToFixed(b.Odds, 2), Bets.Teams(b))).ToList());
                }).ToList());
            }).ToList())).ToList();
        return Page();
    }

    static async Task<T?> Quiet<T>(Task<T> t) where T : class
    {
        try { return await t; }
        catch (DatabaseException) { return null; }
    }
}
