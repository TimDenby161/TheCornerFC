using System.Globalization;

namespace TheCornerFC.Web.Site;

// Days and kick-off times in the visitor's own time (web/src/lib/matchday.ts zoneChoice and
// LocalTime.svelte). The `tz` cookie holds their browser's zone, which the page sets, so the
// server can write times in it; or "off", where they chose UK time in the menu, and then their
// zone is never kept. No cookie yet: UK time until the page sets it.
public sealed record ZoneChoice(string Tz, bool UkTime)
{
    public const string Off = "off", UkZone = "Europe/London";

    public static ZoneChoice From(string? cookie) =>
        cookie == Off ? new(UkZone, true) : new(Valid(cookie) ? cookie! : UkZone, false);

    static bool Valid(string? tz) => !string.IsNullOrEmpty(tz) && TimeZoneInfo.TryFindSystemTimeZoneById(tz, out _);
}

public static class Times
{
    static readonly CultureInfo British = CultureInfo.GetCultureInfo("en-GB");

    // How LocalTime.svelte writes an instant there: "day" (Sat 10 Oct), "time" (12:30), "short"
    // (10 Oct). The page's own script writes it again in the browser's zone once it runs.
    public static string Show(DateTimeOffset at, string tz, string show)
    {
        var there = TimeZoneInfo.ConvertTime(at, TimeZoneInfo.FindSystemTimeZoneById(tz));
        return show switch
        {
            "day" => there.ToString("ddd d MMM", British),
            "time" => there.ToString("H:mm", British),   // 8:32, not 08:32, as the browser writes it
            "short" => there.ToString("d MMM", British),
            _ => throw new ArgumentOutOfRangeException(nameof(show), show, null),
        };
    }

    // the calendar day ("2026-10-10") an instant falls on there
    public static string LocalDay(DateTimeOffset at, string tz) =>
        TimeZoneInfo.ConvertTime(at, TimeZoneInfo.FindSystemTimeZoneById(tz)).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    static readonly string[] Weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], Months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    // "Sat 10 Oct" for a calendar day
    public static string DayName(string day)
    {
        var d = DateTime.ParseExact(day, "yyyy-MM-dd", CultureInfo.InvariantCulture);
        return $"{Weekdays[(int)d.DayOfWeek]} {d.Day} {Months[d.Month - 1]}";
    }
}
