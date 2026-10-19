using System.Text.Json;
using System.Text.RegularExpressions;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// Which clubs a cup filter shows, from the cup's own file (leagues/<id>; web/src/lib/cups.ts).
public sealed record LeagueDoc(
    [property: System.Text.Json.Serialization.JsonPropertyName("fixture_fields")] string[] FixtureFields,
    JsonElement[][] Fixtures,
    [property: System.Text.Json.Serialization.JsonPropertyName("table_fields")] string[] TableFields,
    JsonElement[][] Table);

public static partial class Cups
{
    sealed record Fixture(string Kickoff, string? Round, int Home, int Away, string Status, int? Hg, int? Ag, int? PenH, int? PenA);

    static readonly HashSet<string> Off = ["CANC", "PST", "ABD"];
    static readonly HashSet<string> CupDone = ["FT", "AET", "PEN", "AWD", "WO"];

    static List<Fixture> Fixtures(LeagueDoc lg)
    {
        int At(string f) => Array.IndexOf(lg.FixtureFields, f);
        int kickoff = At("kickoff"), round = At("round"), home = At("home"), away = At("away"), status = At("status"),
            hg = At("hg"), ag = At("ag"), penH = At("pen_h"), penA = At("pen_a");
        static string? S(JsonElement[] r, int i) => i >= 0 && r[i].ValueKind == JsonValueKind.String ? r[i].GetString() : null;
        static int? I(JsonElement[] r, int i) => i >= 0 && r[i].ValueKind == JsonValueKind.Number ? r[i].GetInt32() : null;
        return lg.Fixtures.Select(r => new Fixture(S(r, kickoff) ?? "", S(r, round), I(r, home) ?? 0, I(r, away) ?? 0, S(r, status) ?? "",
            I(r, hg), I(r, ag), I(r, penH), I(r, penA))).ToList();
    }

    // A European cup: the league phase once it has a table; before that everyone drawn in it.
    public static HashSet<int> Entrants(LeagueDoc lg)
    {
        var team = Array.IndexOf(lg.TableFields, "team");
        if (lg.Table.Length > 0) return lg.Table.Select(r => r[team].GetInt32()).ToHashSet();
        return Fixtures(lg).SelectMany(f => new[] { f.Home, f.Away }).ToHashSet();
    }

    // A domestic cup: the clubs still in. A tie's loser is out (on aggregate, then penalties, then
    // whichever of the two doesn't turn up later against someone else). Group matches knock nobody
    // out; once knockout ties follow the group stage, the group clubs not in them are out. Clubs
    // yet to enter aren't in the file, so aren't counted.
    public static HashSet<int> TeamsLeft(LeagueDoc lg)
    {
        var fx = Fixtures(lg).Where(f => !Off.Contains(f.Status)).ToList();
        bool IsGroup(Fixture f) => GroupRe().IsMatch(f.Round ?? "");
        var outs = new HashSet<int>();
        var groupFx = fx.Where(IsGroup).ToList();
        var koFx = fx.Where(f => !IsGroup(f)).ToList();
        if (groupFx.Count > 0)
        {
            var groupEnd = groupFx.Aggregate("", (m, f) => string.CompareOrdinal(f.Kickoff, m) > 0 ? f.Kickoff : m);
            var after = koFx.Where(f => string.CompareOrdinal(f.Kickoff, groupEnd) > 0).ToList();
            if (after.Count > 0)
            {
                var through = after.SelectMany(f => new[] { f.Home, f.Away }).ToHashSet();
                foreach (var f in groupFx) foreach (var t in new[] { f.Home, f.Away }) if (!through.Contains(t)) outs.Add(t);
            }
        }
        var ties = new Dictionary<string, List<Fixture>>();
        foreach (var f in koFx)
        {
            var key = $"{f.Round}|{Math.Min(f.Home, f.Away)}|{Math.Max(f.Home, f.Away)}";
            if (!ties.TryGetValue(key, out var legs)) ties[key] = legs = [];
            legs.Add(f);
        }
        bool PlaysLater(int t, int opp, string after) =>
            koFx.Any(f => string.CompareOrdinal(f.Kickoff, after) > 0 && (f.Home == t || f.Away == t) && f.Home != opp && f.Away != opp);
        foreach (var legs in ties.Values)
        {
            if (!legs.All(f => CupDone.Contains(f.Status) && f.Hg is not null)) continue;
            int a = legs[0].Home, b = legs[0].Away;
            var last = legs[^1];
            int Goals(int t) => legs.Sum(f => (f.Home == t ? f.Hg : f.Ag) ?? 0);
            int? loser = Goals(a) > Goals(b) ? b : Goals(b) > Goals(a) ? a : null;
            if (loser is null && last.PenH is not null && last.PenA is not null && last.PenH != last.PenA)
                loser = last.PenH > last.PenA ? last.Away : last.Home;
            if (loser is null)
            {
                bool aOn = PlaysLater(a, b, last.Kickoff), bOn = PlaysLater(b, a, last.Kickoff);
                if (aOn != bOn) loser = aOn ? b : a;
            }
            if (loser is { } l) outs.Add(l);
        }
        return fx.SelectMany(f => new[] { f.Home, f.Away }).Where(t => !outs.Contains(t)).ToHashSet();
    }

    // Which clubs each cup filter shows, from the cups' own files (kept five minutes). A cup whose
    // file can't be read shows no clubs.
    public static async Task<Dictionary<int, HashSet<int>>> Load(Database db)
    {
        var ids = Names.EuroCups.Concat(Names.DomesticCups).ToList();
        var docs = await Task.WhenAll(ids.Select(async id =>
        {
            try { return await db.KeptDoc<LeagueDoc>($"leagues/{id}", TimeSpan.FromMinutes(5)); }
            catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { return null; }
        }));
        return ids.Select((id, i) => (id, lg: docs[i]))
            .ToDictionary(x => x.id, x => x.lg is null ? [] : Names.DomesticCups.Contains(x.id) ? TeamsLeft(x.lg) : Entrants(x.lg));
    }

    [GeneratedRegex("group", RegexOptions.IgnoreCase)] private static partial Regex GroupRe();
}
