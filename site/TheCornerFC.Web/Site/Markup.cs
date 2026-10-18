using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Html;

namespace TheCornerFC.Web.Site;

// Small pieces of markup many pages share.
public static class Markup
{
    // An instant in the visitor's own time (LocalTime.svelte): written here in the zone the server
    // has for them, and again by the page's script in the browser's own zone, unless they chose UK
    // time. show: "day" (Sat 10 Oct), "time" (12:30), "short" (10 Oct).
    public static IHtmlContent LocalTime(DateTimeOffset at, string show, Visitor visitor) =>
        new HtmlString($"<time datetime=\"{at.UtcDateTime:yyyy-MM-ddTHH:mm:ss.fffZ}\" data-show=\"{show}\">" +
                       $"{HtmlEncoder.Default.Encode(Times.Show(at, visitor.Zone.Tz, show))}</time>");
}
