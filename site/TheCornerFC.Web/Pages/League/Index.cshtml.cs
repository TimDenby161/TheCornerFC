using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Pages.League;

public sealed class IndexModel(Database db) : LeaguePage(db)
{
    protected override Task<IActionResult?> Load() =>
        Task.FromResult<IActionResult?>(new RedirectResult($"/league/{L.Id}/{(L.Table.Count > 0 ? "table" : "matches")}", permanent: false, preserveMethod: true));
}
