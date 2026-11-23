using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// The Fantasy points page (T-104): the shell only. A signed-in visitor's browser asks
// /fantasy/points for the points (Site/FantasyPoints.cs); a signed-out one is shown the way in.
public sealed class FantasyPointsModel : PageModel
{
    public void OnGet() => ViewData["TabHead"] = TabHead.For("Fantasy points", "fantasypoints");
}
