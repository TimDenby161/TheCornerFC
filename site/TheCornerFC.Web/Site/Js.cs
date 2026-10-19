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

    // x.toFixed(digits): the exact value of the double rounded to that many decimals, a tie going
    // away from zero. (C#'s "0.0" rounds a 15-digit copy, so 2.05, really 2.0499..., came out 2.1;
    // its "F1" rounds the exact value but takes a tie, 1.25, to the even 1.2.)
    public static string ToFixed(double x, int digits)
    {
        if (double.IsNaN(x) || double.IsInfinity(x)) return x.ToString(CultureInfo.InvariantCulture);
        var negative = x < 0;
        var bits = BitConverter.DoubleToInt64Bits(Math.Abs(x));
        var exp = (int)((bits >> 52) & 0x7FF);
        var mantissa = bits & 0xFFFFFFFFFFFFFL;
        if (exp == 0) exp++; else mantissa |= 1L << 52;
        exp -= 1075;                                  // x = mantissa * 2^exp exactly
        var scaled = new System.Numerics.BigInteger(mantissa) * System.Numerics.BigInteger.Pow(10, digits);
        System.Numerics.BigInteger whole;
        if (exp >= 0) whole = scaled << exp;
        else
        {
            whole = scaled >> -exp;
            var rest = scaled - (whole << -exp);
            if (rest * 2 >= System.Numerics.BigInteger.One << -exp) whole += 1;
        }
        var text = whole.ToString().PadLeft(digits + 1, '0');
        if (digits > 0) text = text[..^digits] + "." + text[^digits..];
        return negative ? "-" + text : text;           // (-0.04 is "-0.0", as in the browser)
    }

    // n.toLocaleString('en-GB') for a whole number: 1,234
    public static string Num(long n) => n.ToString("N0", British);

    // encodeURIComponent: as Uri.EscapeDataString, but leaving ! ' ( ) * as they are
    public static string EncodeUriComponent(string s) => Uri.EscapeDataString(s)
        .Replace("%21", "!").Replace("%27", "'").Replace("%28", "(").Replace("%29", ")").Replace("%2A", "*");

    // a.localeCompare(b), as the Workers runtime does it
    public static readonly StringComparer Compare = StringComparer.Create(CultureInfo.GetCultureInfo("en-US"), false);
}
