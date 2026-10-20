using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace TheCornerFC.Web.Pages.AdminArea;

// The Admin area opens on the Model Change Tracker (a 303, as the current site answers)
public sealed class IndexModel : PageModel
{
    public IActionResult OnGet()
    {
        Response.Headers.Location = "/admin/changes";
        return StatusCode(303);
    }
}
