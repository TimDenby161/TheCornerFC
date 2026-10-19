using System.Globalization;

namespace TheCornerFC.Web.Site;

// The few places where C# and JavaScript differ on the same sum, written the way the Svelte site
// does them, so both sites show the same numbers.
public static class Js
{
    static readonly CultureInfo British = CultureInfo.GetCultureInfo("en-GB");

    // Math.round: halves go up (2.5 is 3, -2.5 is -2), where C#'s Math.Round goes to the even
    public static double Round(double x) => Math.Floor(x + 0.5);
    public static int RoundInt(double x) => (int)Math.Floor(x + 0.5);

    // n.toLocaleString('en-GB') for a whole number: 1,234
    public static string Num(long n) => n.ToString("N0", British);

    // encodeURIComponent: as Uri.EscapeDataString, but leaving ! ' ( ) * as they are
    public static string EncodeUriComponent(string s) => Uri.EscapeDataString(s)
        .Replace("%21", "!").Replace("%27", "'").Replace("%28", "(").Replace("%29", ")").Replace("%2A", "*");

    // a.localeCompare(b), as the Workers runtime does it
    public static readonly StringComparer Compare = StringComparer.Create(CultureInfo.GetCultureInfo("en-US"), false);
}
