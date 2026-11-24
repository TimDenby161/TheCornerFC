using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// One match on a page of its own, to share or come back to: its card as the Matches page draws it,
// with the line-ups and model detail already open. What the database holds back for this visitor
// stays held back, as on the card.
public sealed class MatchModel(Database db, TimeProvider clock) : PageModel
{
    public Cards.View Card { get; private set; } = null!;
    public string Competition { get; private set; } = "";
    public string? CompetitionHref { get; private set; }
    // Reached from "See an example" (/match/example): a finished match, shown as what subscribers
    // get before kick-off. The page says so, and that address is kept out of search engines.
    public bool Example { get; private set; }
    // a few sentences about the match for its page (T-091), from what this visitor's card holds
    public List<string> Preview { get; private set; } = [];

    public async Task<IActionResult> OnGet(string id)
    {
        if (id.Length is 0 or > 10 || !id.All(char.IsAsciiDigit) || !long.TryParse(id, out var fixture)) return NotFound();
        var visitor = Visitor.Of(HttpContext);
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var rankingsTask = db.KeptDoc<Rankings>("rankings");
        var answerTask = db.AskAs<MatchesAnswer>(visitor.Token, "site_matches", new { p_ids = new[] { fixture } });
        await Task.WhenAll(siteTask, rankingsTask, answerTask);
        var site = siteTask.Result;
        var m = ClubData.MatchRows(site, answerTask.Result).FirstOrDefault();
        if (m is null) return NotFound();
        var all = Clubs.From(rankingsTask.Result);
        var ranks = all.GroupBy(c => c.Team).ToDictionary(g => g.Key, g => g.Last());
        Card = Cards.Of(site, ranks, m, answerTask.Result.Paywall == true, clock.GetUtcNow());
        Competition = site.CompLabel(m.League);
        CompetitionHref = Card.Intl ? null : Menu.PageHref("league", m.League.ToString());
        Example = Request.Query.ContainsKey("example") && Card.Finished && Card.Probs is not null;
        if (Example) ViewData["NoIndex"] = true;
        else ViewData["ShareImage"] = $"/share/match/{fixture}.png";

        if (!visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        var name = $"{Card.Home.Name} v {Card.Away.Name}";
        // (the shared title and description are the same for every visitor: the day in UK time)
        var day = Times.Show(DateTimeOffset.Parse(m.Kickoff), "Europe/London", "day");
        ViewData["Name"] = name;
        if (!Example)
        {
            var kick = DateTimeOffset.Parse(m.Kickoff);
            Preview = MatchPreview.Lines(Card, Competition, day, Times.Show(kick, "Europe/London", "time"),
                Card.Intl ? null : MatchPreview.StandingOf(m.Home, all, site.CompLabel),
                Card.Intl ? null : MatchPreview.StandingOf(m.Away, all, site.CompLabel));
        }
        // The title uses the words people search with: "Arsenal vs Chelsea prediction"
        var searched = $"{Card.Home.Name} vs {Card.Away.Name}";
        ViewData["Title"] = Card.Finished
            ? $"{searched} result and prediction · {Competition}, {day} · The Corner FC"
            : $"{searched} prediction · {Competition}, {day} · The Corner FC";
        ViewData["Description"] = Card.Finished
            ? $"{searched}, {Competition}, {day}: the result, the model's prediction before kick-off, how it did, and both line-ups."
            : $"{searched} prediction, {Competition}, {day}: the model's win, draw and loss chances, predicted score, predicted line-ups and the key reasons.";
        return Page();
    }
}
