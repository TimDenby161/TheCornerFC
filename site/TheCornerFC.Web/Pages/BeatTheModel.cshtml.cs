using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// Beat the Model (T-095): the shell only; the game is asked for as the visitor (Site/BeatTheModel.cs).
public sealed class BeatTheModelModel : PageModel
{
    public void OnGet() => ViewData["TabHead"] = TabHead.For("Beat the Model", "btm");
}
