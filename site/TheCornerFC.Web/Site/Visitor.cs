namespace TheCornerFC.Web.Site;

// Who is asking and how they want the page written. Signed-in visitors come with step 7 of the
// rebuild (audit/csharp-rebuild-plan.md): until then everyone is signed out.
public sealed record Visitor(ZoneChoice Zone, string? Email = null, string? Token = null, bool Admin = false, bool Owner = false)
{
    public bool SignedIn => Email is not null;

    public static Visitor Of(HttpContext context) =>
        context.Items.TryGetValue(nameof(Visitor), out var v) && v is Visitor visitor
            ? visitor
            : (Visitor)(context.Items[nameof(Visitor)] = new Visitor(ZoneChoice.From(context.Request.Cookies["tz"]),
                Owner: context.Request.Cookies["owner"] == "1"));
}
