using System.Text.Encodings.Web;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Html;

namespace TheCornerFC.Web.Site;

// Small pieces of markup many pages share (the Svelte site's components of the same names).
public static partial class Markup
{
    // (written as they read, as the pages are: only <, >, &, quotes are escaped)
    static readonly HtmlEncoder Encoder = HtmlEncoder.Create(System.Text.Unicode.UnicodeRanges.All);
    static string E(string? s) => Encoder.Encode(s ?? "");

    // An instant in the visitor's own time (LocalTime.svelte): written here in the zone the server
    // has for them, and again by the page's script in the browser's own zone, unless they chose UK
    // time. show: "day" (Sat 10 Oct), "time" (12:30), "short" (10 Oct).
    public static IHtmlContent LocalTime(DateTimeOffset at, string show, Visitor visitor) =>
        new HtmlString($"<time datetime=\"{at.UtcDateTime:yyyy-MM-ddTHH:mm:ss.fffZ}\" data-show=\"{show}\">" +
                       $"{E(Times.Show(at, visitor.Zone.Tz, show))}</time>");

    // ---- A club's or competition's chip (Crest.svelte): its initials on a colour of its own (no
    // badges or logos: those are trade marks). With `href` it opens that page; with `label` it is
    // read out, otherwise it is hidden from screen readers.
    static readonly HashSet<string> CrestSkip = ["fc", "afc", "cf", "sc", "ac", "as", "cd", "ud", "sd", "rc", "fk", "sk",
        "nk", "bk", "sv", "if", "de", "del", "la", "le", "el", "the", "and", "of", "&"];

    public static string CrestInitials(string name, bool skip)
    {
        var all = CrestWordSplit().Split(CrestDrop().Replace(name ?? "", "")).Where(w => w.Length > 0).ToList();
        var kept = skip ? all.Where(w => !CrestSkip.Contains(w.ToLowerInvariant())).ToList() : all;
        var words = kept.Count > 0 ? kept : all;
        if (words.Count == 0) return "?";
        static IEnumerable<string> Chars(string w) => w.EnumerateRunes().Select(r => r.ToString());
        var text = words.Count == 1 ? string.Concat(Chars(words[0]).Take(3)) : string.Concat(words.Take(3).Select(w => Chars(w).First()));
        return text.ToUpperInvariant();
    }

    public static int CrestHue(int id) => (int)Js.Round(id * 137.508 % 360) % 360;

    public static IHtmlContent Crest(int id, string name, string size = "club-logo", bool league = false, string? href = null, string? label = null, string? title = null)
    {
        var cls = $"{size} crest crest-h{CrestHue(league ? id + 7 : id)}";
        var text = E(CrestInitials(name, !league));
        title ??= name;
        return new HtmlString(href is not null
            ? $"<a class=\"{cls}\" href=\"{E(href)}\" title=\"{E(title)}\" aria-label=\"{E(label ?? name)}\"><b>{text}</b></a>"
            : $"<span class=\"{cls}\" title=\"{E(title)}\"{(label is not null ? $" role=\"img\" aria-label=\"{E(label)}\"" : " aria-hidden=\"true\"")}><b>{text}</b></span>");
    }

    // A country's flag, linking to its page (its name where there is no flag; Flag.svelte). `key`
    // is the country as the data names it ("Saudi-Arabia"), `name` as it is shown.
    public static IHtmlContent Flag(string key, string name)
    {
        var href = E(Menu.PageHref("country", key));
        return new HtmlString(Names.FlagCodes.TryGetValue(name, out var code)
            ? $"<a class=\"flag-link\" href=\"{href}\" title=\"{E(name)}\" aria-label=\"{E(name)}\"><img class=\"flag\" src=\"https://flagcdn.com/w40/{code}.png\" alt=\"\" loading=\"lazy\" /></a>"
            : $"<a class=\"nat-link\" href=\"{href}\">{E(name)}</a> ·");
    }

    // A signed change: green with a plus when up, red when down, a plain 0, nothing when unknown.
    public static IHtmlContent Move(double? value) => new HtmlString(value switch
    {
        null => "",
        > 0 => $"<span class=\"form-up\">+{value}</span>",
        < 0 => $"<span class=\"form-down\">{value}</span>",
        _ => "0",
    });

    // "1st", "2nd", "11th", "23rd"
    public static string Ordinal(int n)
    {
        string[] s = ["th", "st", "nd", "rd"];
        var v = n % 100;
        var i = (v - 20) % 10;
        return n + (i is >= 1 and <= 3 ? s[i] : v is >= 1 and <= 3 ? s[v] : s[0]);
    }

    // A column heading that sorts its table (SortTh.svelte): the first press sorts the column best
    // first, a second reverses it. The choice is in the address (?sort=points, &rev=1 reversed);
    // `def` is the table's own order, which is left out.
    public static IHtmlContent SortTh(HttpRequest request, string key, Leagues.Sort sort, string def, string title, string inner, string cls = "")
    {
        var on = sort.Key == key;
        var q = Microsoft.AspNetCore.WebUtilities.QueryHelpers.ParseQuery(request.QueryString.Value)
            .Where(kv => kv.Key is not "sort" and not "rev").ToDictionary(kv => kv.Key, kv => kv.Value.ToString());
        if (on) { if (key != def) q["sort"] = key; if (!request.Query.ContainsKey("rev")) q["rev"] = "1"; }
        else if (key != def) q["sort"] = key;
        var href = q.Count > 0 ? "?" + Query(q) : request.Path.Value!;
        var aria = on ? $" aria-sort=\"{(sort.Dir > 0 ? "ascending" : "descending")}\"" : "";
        var dir = on ? $"<span class=\"sort-dir\">{(sort.Dir > 0 ? "▲" : "▼")}</span>" : "";
        return new HtmlString($"<th class=\"{cls} sortable{(on ? " active" : "")}\" title=\"{E(title)}. Click to sort.\"{aria}><a href=\"{E(href)}\">{inner}{dir}</a></th>");
    }

    // a query string as URLSearchParams writes it (spaces as +)
    public static string Query(IEnumerable<KeyValuePair<string, string>> q) =>
        string.Join('&', q.Select(kv => $"{Uri.EscapeDataString(kv.Key)}={Uri.EscapeDataString(kv.Value)}".Replace("%20", "+")));

    // A person's chip: initials on the plain chip colour (no photos: they belong to photographers)
    public static IHtmlContent PersonChip(string name, string size = "player-photo") =>
        new HtmlString($"<span class=\"{size} person-chip\" aria-hidden=\"true\"><b>{E(ClubPage.PersonInitials(name))}</b></span>");

    // A pitch (Pitch.svelte), in the club's home kit colours where its file has them (stripes in the
    // shirt colour, lines in the number colour); otherwise the plain dark pitch. The colours are the
    // club's own, so they can't be classes: the page's script sets them from data-kit. Close it
    // with PitchEnd.
    public static IHtmlContent PitchStart(string kind, string[]? kit) => new HtmlString(
        $"<div class=\"pitch {kind}{(kit is not null ? " kit" : "")}\"{(kit is not null ? $" data-kit=\"{E(kit[0])},{E(kit[1])}\"" : "")}>" +
        "<svg viewBox=\"0 0 68 88\" preserveAspectRatio=\"none\" aria-hidden=\"true\" fill=\"none\" stroke=\"rgba(255,255,255,0.16)\" stroke-width=\"0.6\">" +
        "<rect x=\"3\" y=\"3\" width=\"62\" height=\"82\" rx=\"1\" /><line x1=\"3\" y1=\"44\" x2=\"65\" y2=\"44\" />" +
        "<circle cx=\"34\" cy=\"44\" r=\"7\" /><rect x=\"17\" y=\"3\" width=\"34\" height=\"12\" /><rect x=\"26\" y=\"3\" width=\"16\" height=\"5\" />" +
        "<rect x=\"17\" y=\"73\" width=\"34\" height=\"12\" /><rect x=\"26\" y=\"80\" width=\"16\" height=\"5\" /></svg>");
    public static readonly IHtmlContent PitchEnd = new HtmlString("</div>");

    [GeneratedRegex("[.'’]")] private static partial Regex CrestDrop();
    [GeneratedRegex(@"[\s-]+")] private static partial Regex CrestWordSplit();
}