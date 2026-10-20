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
        var ranks = Clubs.From(rankingsTask.Result).GroupBy(c => c.Team).ToDictionary(g => g.Key, g => g.Last());
        Card = Cards.Of(site, ranks, m, answerTask.Result.Paywall == true, clock.GetUtcNow());
        Competition = site.CompLabel(m.League);
        CompetitionHref = Card.Intl ? null : Menu.PageHref("league", m.League.ToString());

        if (!visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        var name = $"{Card.Home.Name} v {Card.Away.Name}";
        // (the shared title and description are the same for every visitor: the day in UK time)
        var day = Times.Show(DateTimeOffset.Parse(m.Kickoff), "Europe/London", "day");
        ViewData["Name"] = name;
        ViewData["Title"] = $"{name} · {Competition}, {day} · The Corner FC";
        ViewData["Description"] = Card.Finished
            ? $"{name}, {Competition}, {day}: the result, the model's chances before kick-off, how its prediction did, and both line-ups."
            : $"{name}, {Competition}, {day}: the model's win, draw and loss chances, projected score, key reasons and how the prediction was made.";
        return Page();
    }
}
