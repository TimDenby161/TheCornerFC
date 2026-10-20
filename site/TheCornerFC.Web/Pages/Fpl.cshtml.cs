using System.Text.Json;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// The FPL page (web/src/routes/(app)/fpl), the site owner's. A visitor who isn't signed in is sent
// nothing but the way in. The findings hold no FPL data (they are the model's own test results);
// the predictions, which do, are never written here: the owner's browser asks for them
// (/fantasy/data).
public sealed class FplModel(Database db) : PageModel
{
    public JsonElement? Findings { get; private set; }

    public async Task OnGet()
    {
        ViewData["TabHead"] = TabHead.For("FPL", "fpl");
        if (!Visitor.Of(HttpContext).SignedIn) return;
        try { Findings = await db.KeptDoc<JsonElement>("fpl", TimeSpan.FromMinutes(5)); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { }
    }
}
