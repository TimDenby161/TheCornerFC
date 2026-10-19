namespace TheCornerFC.Web.Site;

// Who is asking and how they want the page written: their time zone choice and, signed in, their
// account and the token the database checks for itself (Sessions works this out before any page runs)
public sealed record Visitor(ZoneChoice Zone, string? Email = null, string? Token = null, bool Admin = false, bool Owner = false, string? UserId = null)
{
    public bool SignedIn => Email is not null;

    // (a session with no email to it, as a phone sign-in would have, isn't counted as signed in)
    public static Visitor For(HttpContext context, Session? session)
    {
        var s = session is { Email.Length: > 0 } ? session : null;
        return new(ZoneChoice.From(context.Request.Cookies["tz"]), s?.Email, s?.AccessToken, Owner: context.Request.Cookies["owner"] == "1", UserId: s?.UserId);
    }

    // (signed out where nothing has said otherwise: a request that never passed through Sessions)
    public static Visitor Of(HttpContext context) =>
        context.Items.TryGetValue(nameof(Visitor), out var v) && v is Visitor visitor
            ? visitor
            : (Visitor)(context.Items[nameof(Visitor)] = For(context, null));
}
