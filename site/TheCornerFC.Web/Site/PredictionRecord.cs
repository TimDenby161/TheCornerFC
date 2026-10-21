using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// The Prediction record (/record; owner, 2026-10-21): every finished club match's prediction as it
// was locked before kick-off, beside what happened, for a month, a competition and a page at a
// time. Read from site_prediction_record (db/migrations/20261021_prediction_record.sql), filled by
// the export from the locked snapshots (site_record.store_prediction_record).
public sealed record PredictionRecordDoc(bool? Any, DateTimeOffset? Since, int? Total, int? Right,
    [property: JsonPropertyName("log_loss")] double? LogLoss, DateTimeOffset? First, DateTimeOffset? Last,
    Dictionary<string, int>? Comps, JsonElement[][]? Rows, Dictionary<string, string>? Teams);

public static class PredictionRecord
{
    public const int Page = 100;
    static readonly string[] MonthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

    public sealed record Row(int Fixture, DateTimeOffset Kickoff, int League, int Home, int Away, double[] Chances, string? Likely,
        double HomeXg, double AwayXg, int Hg, int Ag, int Outcome, bool Right, double LogLoss, DateTimeOffset Stored, string Version, string Hash);

    // one row as the function lists it: [fixture, kickoff, competition, home, away, p_home, p_draw,
    // p_away, likely, home_xg, away_xg, home goals, away goals, outcome, right, log loss, stored at,
    // version, hash]
    public static Row Read(JsonElement[] r) => new(r[0].GetInt32(), r[1].GetDateTimeOffset(), r[2].GetInt32(), r[3].GetInt32(), r[4].GetInt32(),
        [r[5].GetDouble(), r[6].GetDouble(), r[7].GetDouble()], r[8].ValueKind == JsonValueKind.String ? r[8].GetString() : null,
        r[9].GetDouble(), r[10].GetDouble(), r[11].GetInt32(), r[12].GetInt32(), r[13].GetInt32(), r[14].GetBoolean(), r[15].GetDouble(),
        r[16].GetDateTimeOffset(), r[17].GetString() ?? "", r[18].GetString() ?? "");

    // the months on record, newest first, as "2026-10" with its name ("October 2026")
    public static List<(string Key, string Name)> Months(DateTimeOffset? since, DateTimeOffset now)
    {
        if (since is not { } s) return [];
        var list = new List<(string, string)>();
        for (var m = new DateTime(now.UtcDateTime.Year, now.UtcDateTime.Month, 1); m >= new DateTime(s.UtcDateTime.Year, s.UtcDateTime.Month, 1); m = m.AddMonths(-1))
            list.Add((m.ToString("yyyy-MM", CultureInfo.InvariantCulture), $"{MonthNames[m.Month - 1]} {m.Year}"));
        return list;
    }

    // a month from the address ("2026-10") as its first and last day, or null for all of them
    public static (DateOnly From, DateOnly To)? MonthRange(string key) =>
        DateOnly.TryParseExact(key + "-01", "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var from)
            ? (from, from.AddMonths(1).AddDays(-1)) : null;

    // how long before kick-off the prediction was stored: "45 min", "6 h", "3 days"
    public static string Before(DateTimeOffset stored, DateTimeOffset kickoff)
    {
        var gap = kickoff - stored;
        if (gap.TotalHours < 1) return $"{Math.Max(1, (int)gap.TotalMinutes)} min";
        if (gap.TotalHours < 48) return $"{(int)gap.TotalHours} h";
        return $"{(int)gap.TotalDays} days";
    }

    public static string Pct(double p) => $"{Js.ToFixed(100 * p, 0)}%";
    public static string Share(int n, int of) => of == 0 ? "–" : $"{Js.ToFixed(100.0 * n / of, 1)}%";
    public static int Called(double[] p) => p[0] >= p[1] && p[0] >= p[2] ? 0 : p[1] >= p[2] ? 1 : 2;
}
