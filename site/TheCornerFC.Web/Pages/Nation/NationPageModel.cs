using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.NationTabs;

// A nation's page (web/src/routes/(app)/nation/[name]; this folder is Pages/Nation): the header
// every tab shares (flag, head coach, the national team's rating), then the tab.
public abstract class NationPageModel(Database db) : PageModel
{
    protected Database Db { get; } = db;
    public NationBase N { get; private set; } = null!;
    public string? Flag { get; private set; }
    protected Visitor Visitor => TheCornerFC.Web.Site.Visitor.Of(HttpContext);

    public async Task<IActionResult> OnGet(string name)
    {
        var n = await NationBase.Load(Db, name, Visitor.Token);
        if (n is null) return NotFound();
        N = n;
        ViewData["Name"] = n.Name;
        Flag = Names.FlagCodes.GetValueOrDefault(name);
        if (!Visitor.SignedIn) Response.Headers.CacheControl = "public, max-age=60";
        return await Load() ?? Page();
    }

    // the tab's own part; a result in place of the page where it has one
    protected abstract Task<IActionResult?> Load();
}
