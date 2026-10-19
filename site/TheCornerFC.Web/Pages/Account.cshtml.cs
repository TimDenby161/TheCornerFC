using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages;

// What the database says of a signed-in visitor's subscription (my_subscription); nothing about
// subscriptions shows unless its paywall is on
public sealed record Subscription(bool Paywall, [property: JsonPropertyName("signed_in")] bool SignedIn, bool Subscriber, string? Status, string? Plan,
    [property: JsonPropertyName("renews_at")] string? RenewsAt, bool Ends)
{
    // (asked once a request: the page and the layout's account box both want it)
    public static Task<Subscription?> Of(Database db, HttpContext context)
    {
        if (context.Items.TryGetValue(nameof(Subscription), out var kept) && kept is Task<Subscription?> t) return t;
        var asked = Ask(db, Visitor.Of(context));
        context.Items[nameof(Subscription)] = asked;
        return asked;
    }
    static async Task<Subscription?> Ask(Database db, Visitor visitor)
    {
        if (!visitor.SignedIn) return null;
        try { return await db.SiteAsk<Subscription?>("my_subscription", new { }, visitor.Token); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or System.Text.Json.JsonException) { return null; }
    }
}

// The account page (web/src/routes/(app)/account): sign in with Google or an email and password,
// create an account, reset a password, and for a signed-in visitor their profile, signing out and
// deleting the account. The same box the menu's button opens, as a page of its own: where a form
// lands when the page's script isn't running, and where an emailed link that failed, or a password
// reset, comes back to. Each form posts here; the box's script asks for its answer as JSON and shows
// it without leaving the page.
// (Forms here are checked as SvelteKit checks them, before any page runs: a post must come from
// this site's own pages, Site/Sessions.cs)
[IgnoreAntiforgeryToken]
public sealed class AccountModel(AuthClient auth, Database db) : PageModel
{
    public static readonly HashSet<string> Views = ["signin", "signup", "reset", "newpass", "subscribe", "delete"];
    public static readonly Dictionary<string, string> Titles = new()
    {
        ["signin"] = "Sign in", ["signup"] = "Create an account", ["reset"] = "Reset your password", ["newpass"] = "Choose a new password",
        ["note"] = "Check your email", ["account"] = "Your profile", ["delete"] = "Delete your account", ["subscribe"] = "Subscribe",
    };
    // whether subscriptions can be bought yet: not until payments come across (the rebuild's step 7c),
    // as on the live site today
    public const bool Pay = false;
    // what a subscription costs (owner, 2026-10-07): the words on the buttons; the charge itself is
    // the price set in Stripe, and the two must be changed together
    public static readonly (string Monthly, string Yearly) Prices = ("£4.99 a month", "£49 a year");
    const string NoCheck = "Wait for the check above the button to finish, then try again.";

    public Visitor Who => Visitor.Of(HttpContext);
    public Subscription? Sub { get; private set; }
    public string? Asked { get; private set; }
    public string Message { get; private set; } = "";
    public bool MessageOk { get; private set; }
    public string Note { get; private set; } = "";
    public string Email { get; private set; } = "";

    // what is shown: a signed-in visitor sees their profile unless choosing a password or deleting
    public string View => Asked == "subscribe" ? "subscribe" : Asked == "note" ? "note"
        : !Who.SignedIn ? (Asked is null or "delete" or "account" ? "signin" : Asked)
        : Asked is "newpass" or "delete" ? Asked : "account";

    async Task Load()
    {
        Sub = await Subscription.Of(db, HttpContext);
        ViewData["Title"] = $"{Titles[View]} · The Corner FC";
    }

    public async Task OnGet()
    {
        var view = Request.Query["view"].ToString();
        Asked = Views.Contains(view) ? view : null;
        var failed = Request.Query["failed"].ToString();
        // back from Stripe's checkout: its webhook switches the subscription on, usually within seconds
        var paid = Request.Query.ContainsKey("paid");
        Message = failed != "" ? AuthClient.ErrorText(failed) : paid ? "Thank you. Your subscription is being switched on: it can take a minute to show here." : "";
        MessageOk = failed == "" && paid;
        await Load();
    }

    // ---- answers: JSON for the box's script, the page again for a form sent without it
    bool WantsJson => Request.Headers.Accept.ToString().Contains("application/json");
    async Task<IActionResult> Fail(string message, string view, string email = "", int status = 400)
    {
        if (WantsJson) return new JsonResult(new { type = "failure", data = new { message } }) { StatusCode = status };
        Asked = view; Message = message; Email = email;
        await Load();
        Response.StatusCode = status;
        return Page();
    }
    async Task<IActionResult> Done(string done, string? note = null, string? message = null)
    {
        if (WantsJson) return new JsonResult(new { type = "success", data = new { done, note } });
        if (note is not null) { Asked = "note"; Note = note; await Load(); return Page(); }
        if (message is not null) { Asked = done == "erased" ? "signin" : "account"; Message = message; MessageOk = true; await Load(); return Page(); }
        return Redirect("/account");
    }
    IActionResult Away(string to) => WantsJson ? new JsonResult(new { type = "redirect", location = to }) : Redirect(to);

    string Text(string name) => Request.Form[name].ToString();
    // the bot check's answer, which Supabase verifies before it acts (the widget puts it in the form)
    string? Captcha => Text("cf-turnstile-response") is { Length: > 0 } c ? c : null;
    string Origin => $"{Request.Scheme}://{Request.Host}";

    public async Task<IActionResult> OnPostSignin()
    {
        var email = Text("email").Trim();
        if (Captcha is null) return await Fail(NoCheck, "signin", email);
        var a = await auth.SignIn(email, Text("password"), Captcha);
        if (!a.Ok || a.Session is null) return await Fail(AuthClient.ErrorText(a), "signin", email);
        Sessions.Keep(HttpContext, a.Session);
        return await Done("signin");
    }

    public async Task<IActionResult> OnPostSignup()
    {
        var email = Text("email").Trim();
        if (Captcha is null) return await Fail(NoCheck, "signup", email);
        var a = await auth.SignUp(email, Text("password"), Captcha, $"{Origin}/");
        if (!a.Ok) return await Fail(AuthClient.ErrorText(a), "signup", email);
        // the same answer whether or not the email has an account, so the box can't be used to find out
        if (a.Session is { } s) { Sessions.Keep(HttpContext, s); return await Done("signin"); }
        return await Done("note", $"We've sent a link to {email}. Open it to finish creating your account.");
    }

    public async Task<IActionResult> OnPostReset()
    {
        var email = Text("email").Trim();
        if (Captcha is null) return await Fail(NoCheck, "reset", email);
        var a = await auth.Recover(email, Captcha, $"{Origin}/");
        if (!a.Ok) return await Fail(AuthClient.ErrorText(a), "reset", email);
        return await Done("note", $"If {email} has an account, we've sent it a link to choose a new password.");
    }

    public async Task<IActionResult> OnPostNewpass()
    {
        if (Who.Token is not { } token) return await Fail("That link has expired or has already been used. Ask for a new one.", "newpass", status: 401);
        var a = await auth.UpdatePassword(token, Text("password"));
        if (!a.Ok) return await Fail(AuthClient.ErrorText(a), "newpass");
        return await Done("newpass", message: "Your password has been changed.");
    }

    // on to Google, which sends the visitor back to the page they were on
    public IActionResult OnPostGoogle()
    {
        var back = AuthClient.SafePath(Text("back"));
        var (url, verifier) = auth.GoogleUrl($"{Origin}{back}");
        Sessions.KeepVerifier(HttpContext, verifier);
        return Away(url);
    }

    // this browser only
    public async Task<IActionResult> OnPostSignout()
    {
        if (Who.Token is { } token)
        {
            var a = await auth.SignOut(token);
            if (!a.Ok) return await Fail(AuthClient.ErrorText(a), "account");
        }
        Sessions.Forget(HttpContext);
        return await Done("signout");
    }

    // removes the caller's own row from Supabase Auth and nothing else (delete_my_account)
    public async Task<IActionResult> OnPostErase()
    {
        if (Who.Token is not { } token) return await Fail("Sign in first.", "delete", status: 401);
        // (a subscription still running is cancelled with Stripe first, once payments come across: none can be bought yet)
        try { await db.SiteCall("delete_my_account", new { }, token); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException) { return await Fail("Something went wrong. Try again in a moment.", "delete"); }
        await auth.SignOut(token);
        Sessions.Forget(HttpContext);
        return await Done("erased", message: "Your account has been deleted.");
    }

    // On to Stripe's checkout, and to Stripe's own page for a subscriber: none until payments come across
    public Task<IActionResult> OnPostSubscribe() => Fail("Subscriptions are coming soon.", "subscribe");
    public Task<IActionResult> OnPostManage() => Fail("Subscriptions are coming soon.", "account");
}
