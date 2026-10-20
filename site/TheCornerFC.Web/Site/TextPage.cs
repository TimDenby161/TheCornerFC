using System.Text.RegularExpressions;

namespace TheCornerFC.Web.Site;

// The plain text pages (terms, privacy, how the models work, what the models assume) are whole HTML files in web/src/text,
// as the old site wrote them, read by both sites (web/src/lib/textPage.ts). This takes one's text
// out of its file and points its links at this site.
public sealed partial record TextPage(string Title, string Description, string Html)
{
    static readonly System.Collections.Concurrent.ConcurrentDictionary<string, TextPage> Read = new();

    public static TextPage Named(string name) => Read.GetOrAdd(name, Load);

    static TextPage Load(string name)
    {
        using var file = typeof(TextPage).Assembly.GetManifestResourceStream($"text/{name}.html")
            ?? throw new ArgumentException($"No text page {name}", nameof(name));
        return From(new StreamReader(file).ReadToEnd());
    }

    public static TextPage From(string file)
    {
        var main = MainPart().Match(file) is { Success: true } m ? m.Groups[1].Value : "";
        main = SectionLink().Replace(main, "href=\"/$1\"");                       // a section of the site
        main = PageLink().Replace(main, m => $"href=\"/{m.Groups[1].Value}{m.Groups[2].Value}\"");
        main = main.Replace("href=\"./\"", "href=\"/\"").Replace("href=\".well-known/", "href=\"/.well-known/");
        return new(TitlePart().Match(file) is { Success: true } t ? t.Groups[1].Value : "The Corner FC",
                   DescriptionPart().Match(file) is { Success: true } d ? d.Groups[1].Value : "", main);
    }

    // The text cut where the page has a box for live figures (<div id="..-live" ...>...</div>):
    // the text before each box with the box's id, then the rest
    public IReadOnlyList<(string Html, string? Live)> Parts()
    {
        var parts = new List<(string, string?)>();
        var at = 0;
        foreach (Match m in LiveBox().Matches(Html))
        {
            parts.Add((Html[at..m.Index], m.Groups[1].Value));
            at = m.Index + m.Length;
        }
        parts.Add((Html[at..], null));
        return parts;
    }

    [GeneratedRegex(@"<main>([\s\S]*)</main>")] private static partial Regex MainPart();
    [GeneratedRegex(@"<title>([^<]*)</title>")] private static partial Regex TitlePart();
    [GeneratedRegex("<meta name=\"description\" content=\"([^\"]*)\"")] private static partial Regex DescriptionPart();
    [GeneratedRegex(@"href=""\./#/([\w-]+)""")] private static partial Regex SectionLink();
    [GeneratedRegex(@"href=""(terms|privacy|methodology|assumptions)\.html(#[\w-]+)?""")] private static partial Regex PageLink();
    [GeneratedRegex(@"<div id=""([\w-]+-live)""[^>]*>[\s\S]*?</div>")] private static partial Regex LiveBox();
}
