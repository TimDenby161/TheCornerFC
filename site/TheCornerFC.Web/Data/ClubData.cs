using System.Text.Json;
using System.Text.Json.Serialization;

namespace TheCornerFC.Web.Data;

// A club's own file (clubs/<id>; web/src/lib/club.ts): every match since 2020 with the rating after
// it, the manager, the names of the clubs it has played, its kit colours, and for the squad model
// who started where this season ("starts") and each player's minutes by role ("positions").
public sealed record ClubDoc(
    int Id, double? Start, string[] Fields, JsonElement[][] Matches, Coach? Coach, string[]? Colors,
    Dictionary<string, string>? Teams, Starts? Starts, Dictionary<string, JsonElement[][]>? Positions);
public sealed record Coach(int? Id, string? Name, string? Since);

// matches this season with a line-up, each player's starts by role, every line-up as
// [player, role, player, role, ...] with its competition and formation, and minutes over 12 months
// as [starts, minutes started, sub appearances, minutes as a sub]
public sealed record Starts(
    int? Games, Dictionary<string, Dictionary<string, int>>? Players, JsonElement[][]? Xi,
    [property: JsonPropertyName("xi_league")] int[]? XiLeague,
    [property: JsonPropertyName("xi_formation")] string?[]? XiFormation,
    Dictionary<string, double[]>? Mins,
    [property: JsonPropertyName("mins_matches")] int? MinsMatches);

public sealed record ClubMatch(string Date, double Rank, int Opponent, int Home, int Gf, int Ga, int League, string? Formation,
    double? Attack, double? Defence, double?[]? XiLines, double? Xgf, double? Xga, double? XgEst);

// One player as site_players gives him (web/src/lib/players.ts): a row in the order of the site
// document's player_fields. `Locked`: the database blanked his ranks for this visitor.
public sealed record Player(int Id, string Name, string? Position, double? Rank, int? Team, double? Ord,
    Dictionary<string, double>? PositionRanks, string[]? Positions12m, PlayerSeason? Season, bool Locked,
    int? League = null, string? Nationality = null, int? Age = null, int? LgRank = null, int? LgN = null,
    double?[]? Seasons = null, int[]? Estimated = null, double?[]? Future = null, int? World = null, int? Lg = null, int? LgOf = null,
    Dictionary<string, double>? Skills = null);
public sealed record PlayerSeason(int? Minutes, int? Goals, int? Assists);
public sealed record PlayersAnswer(int Total, bool? Paywall, JsonElement[][] Rows);

// A match as site_matches gives it (web/src/lib/matches.ts): a row in the order of match_fields
public sealed record Match(int Id, string Kickoff, int League, string? Round, int Home, int Away, string Status,
    int? Hg, int? Ag, int? PenH, int? PenA, double? PHome, double? PDraw, double? PAway, double? HomeXg, double? AwayXg,
    string? Likely, double? HomeRank, double? AwayRank, string? Source, double? HomeXi, double? AwayXi,
    double? HomeMissing, double? AwayMissing, int? Rating, int? RWinner, int? RMargin, int? RCleanSheets, int? RShape, int? RGoals,
    double? MHome, double? MDraw, int? Intl, List<(string Key, double Goals)> Reasons,
    // the last five starting XIs' average rank, over 2.5 goals and both to score
    double? HomeRecentXi = null, double? AwayRecentXi = null, double? POver25 = null, double? PBtts = null);
public sealed record MatchesAnswer(JsonElement[][] Matches, Dictionary<string, JsonElement[][]>? Reasons, bool? Paywall);

// The injury lists: per club, its next match's, else its latest recent one. A row is
// [player, name, type, ban, matches missed in a row, season rank]
public sealed record Injuries(Dictionary<string, Injuries.Team>? Teams, string[]? Fields = null)
{
    public sealed record Team(string Kickoff, bool Upcoming, JsonElement[][] Players);
}

public static class ClubData
{
    public static List<ClubMatch> Matches(ClubDoc? doc) => doc is null ? [] : doc.Matches.Select(r =>
    {
        var n = new Named(doc.Fields, r);
        var lines = Array.IndexOf(doc.Fields, "xi_lines") is var i and >= 0 && r[i].ValueKind == JsonValueKind.Array
            ? r[i].EnumerateArray().Select(e => e.ValueKind == JsonValueKind.Number ? e.GetDouble() : (double?)null).ToArray() : null;
        return new ClubMatch(n.S("date") ?? "", n.D("rank") ?? 0, n.I("opponent") ?? 0, n.I("home") ?? 0, n.I("gf") ?? 0, n.I("ga") ?? 0,
            n.I("league") ?? 0, n.S("formation"), n.D("attack"), n.D("defence"), lines, n.D("xgf"), n.D("xga"), n.D("xg_est"));
    }).ToList();

    // API-Football sends some names HTML-encoded ("O&apos;Reilly")
    // (only these six, as the Svelte site decodes them)
    static readonly Dictionary<string, string> Entities = new() { ["apos"] = "'", ["#39"] = "'", ["quot"] = "\"", ["amp"] = "&", ["lt"] = "<", ["gt"] = ">" };
    // A few names come garbled with an invisible control character in them (U+0080 to U+009F): the
    // Svelte site writes it as it is, which browsers don't show, but C# would write it as a code that
    // browsers show as a stray mark, so it is dropped here.
    public static string Decode(string t)
    {
        if (t.Any(c => c is >= '\u0080' and <= '\u009f')) t = new string(t.Where(c => c is < '\u0080' or > '\u009f').ToArray());
        return t.Contains('&') ? System.Text.RegularExpressions.Regex.Replace(t, "&(apos|#39|quot|amp|lt|gt);", m => Entities[m.Groups[1].Value]) : t;
    }

    public static List<Player> Players(SiteDoc site, JsonElement[][] rows)
    {
        var fields = site.PlayerFields ?? [];
        var seasonFields = site.PlayerSeasonFields ?? [];
        return rows.Select(r =>
        {
            var n = new Named(fields, r);
            JsonElement? At(string f) => Array.IndexOf(fields, f) is var i and >= 0 && i < r.Length ? r[i] : null;
            var season = At("season") is { ValueKind: JsonValueKind.Array } s ? new Named(seasonFields, s.EnumerateArray().ToArray()) : null;
            var ranks = At("position_ranks") is { ValueKind: JsonValueKind.Object } pr
                ? pr.EnumerateObject().Where(p => p.Value.ValueKind == JsonValueKind.Number).ToDictionary(p => p.Name, p => p.Value.GetDouble()) : null;
            var skills = At("skills") is { ValueKind: JsonValueKind.Object } sk
                ? sk.EnumerateObject().Where(p => p.Value.ValueKind == JsonValueKind.Number).ToDictionary(p => p.Name, p => p.Value.GetDouble()) : null;
            var pos12 = At("positions_12m") is { ValueKind: JsonValueKind.Array } ps ? ps.EnumerateArray().Select(e => e.GetString()!).ToArray() : null;
            double?[]? Doubles(string f) => At(f) is { ValueKind: JsonValueKind.Array } a
                ? a.EnumerateArray().Select(e => e.ValueKind == JsonValueKind.Number ? e.GetDouble() : (double?)null).ToArray() : null;
            return new Player(n.I("id") ?? 0, Decode(n.S("name") ?? ""), n.S("position"), n.D("rank"), n.I("team"), n.D("ord"), ranks, pos12,
                season is null ? null : new PlayerSeason(season.I("minutes"), season.I("goals"), season.I("assists")),
                At("seasons") is not { ValueKind: not JsonValueKind.Null },
                n.I("league"), n.S("nationality"), n.I("age"), n.I("lg_rank"), n.I("lg_n"), Doubles("seasons"),
                Doubles("estimated")?.Where(x => x is not null).Select(x => (int)x!.Value).ToArray(), Doubles("future"), n.I("world"), n.I("lg"), n.I("lg_of"), skills);
        }).ToList();
    }

    public static List<Match> MatchRows(SiteDoc site, MatchesAnswer answer)
    {
        var fields = site.MatchFields ?? [];
        return answer.Matches.Select(r =>
        {
            var n = new Named(fields, r);
            var id = n.I("id") ?? 0;
            var reasons = answer.Reasons?.GetValueOrDefault(id.ToString())?.Select(x => (x[0].GetString()!, x[1].GetDouble())).ToList() ?? [];
            return new Match(id, n.S("kickoff") ?? "", n.I("league") ?? 0, n.S("round"), n.I("home") ?? 0, n.I("away") ?? 0, n.S("status") ?? "",
                n.I("hg"), n.I("ag"), n.I("pen_h"), n.I("pen_a"), n.D("p_home"), n.D("p_draw"), n.D("p_away"), n.D("home_xg"), n.D("away_xg"),
                n.S("likely"), n.D("home_rank"), n.D("away_rank"), n.S("source"), n.D("home_xi"), n.D("away_xi"), n.D("home_missing"), n.D("away_missing"),
                n.I("rating"), n.I("r_winner"), n.I("r_margin"), n.I("r_clean_sheets"), n.I("r_shape"), n.I("r_goals"),
                n.D("m_home"), n.D("m_draw"), n.I("intl"), reasons, n.D("home_recent_xi"), n.D("away_recent_xi"), n.D("p_over25"), n.D("p_btts"));
        }).OrderBy(m => m.Kickoff, StringComparer.Ordinal).ThenBy(m => m.Id).ToList();
    }

    public static readonly HashSet<string> Finished = ["FT", "AET", "PEN", "AWD", "WO"];
    public static readonly HashSet<string> Live = ["1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"];
    public static readonly HashSet<string> CalledOff = ["CANC", "PST", "ABD"];
    // ... and on a match card, one awarded or walked over has nothing to predict either
    public static readonly HashSet<string> NoGame = ["PST", "CANC", "ABD", "AWD", "WO"];
    // still to be played (or being played), oldest first
    public static List<Match> Upcoming(IEnumerable<Match> list) => list.Where(m => !Finished.Contains(m.Status) && !CalledOff.Contains(m.Status)).ToList();
}

// A player's own file (players/<id> through site_player_page; web/src/lib/player.ts): league
// seasons by club, his last 20 league appearances, his clubs and positions season by season. A
// visitor who isn't a subscriber gets it with a locked player's ranks left out.
public sealed record PlayerDoc(
    int Id, string? Born, bool? Cut,
    [property: JsonPropertyName("season_fields")] string[] SeasonFields, JsonElement[][] Seasons,
    [property: JsonPropertyName("match_fields")] string[] MatchFields, JsonElement[][] Matches,
    [property: JsonPropertyName("spell_fields")] string[] SpellFields, Dictionary<string, JsonElement[][]>? Spells,
    Dictionary<string, JsonElement[][]>? Positions,
    JsonElement? Injury,              // [fixture, type, ban]
    Dictionary<string, string>? Teams);

public sealed record SeasonLine(int Season, int Team, int League, int Apps, int? Starts, int Minutes, int? Goals, int? Assists, int? Yellow, int? Red);
public sealed record Appearance(int Fixture, string Date, int League, int Team, int Opponent, int Home, int Gf, int Ga, int Started, int Minutes,
    string? Role, double? Rank, int Goals, int Assists, int Yellow, int Red);
public sealed record Spell(int Team, int? Minutes, double? ClubRank, int? Goals, int? Assists);

public static class PlayerFiles
{
    public static List<SeasonLine> Seasons(PlayerDoc? doc) => doc is null ? [] : doc.Seasons.Select(r =>
    {
        var n = new Named(doc.SeasonFields, r);
        return new SeasonLine(n.I("season") ?? 0, n.I("team") ?? 0, n.I("league") ?? 0, n.I("apps") ?? 0, n.I("starts"), n.I("minutes") ?? 0,
            n.I("goals"), n.I("assists"), n.I("yellow"), n.I("red"));
    }).ToList();

    public static List<Appearance> Appearances(PlayerDoc? doc) => doc is null ? [] : doc.Matches.Select(r =>
    {
        var n = new Named(doc.MatchFields, r);
        return new Appearance(n.I("fixture") ?? 0, n.S("date") ?? "", n.I("league") ?? 0, n.I("team") ?? 0, n.I("opponent") ?? 0, n.I("home") ?? 0,
            n.I("gf") ?? 0, n.I("ga") ?? 0, n.I("started") ?? 0, n.I("minutes") ?? 0, n.S("role"), n.D("rank"),
            n.I("goals") ?? 0, n.I("assists") ?? 0, n.I("yellow") ?? 0, n.I("red") ?? 0);
    }).ToList();

    public static List<Spell> Spells(PlayerDoc? doc, string key) =>
        doc?.Spells?.GetValueOrDefault(key) is { } rows ? rows.Select(r =>
        {
            var n = new Named(doc.SpellFields, r);
            return new Spell(n.I("team") ?? 0, n.I("minutes"), n.D("club_rank"), n.I("goals"), n.I("assists"));
        }).ToList() : [];

    // [[role, minutes], ...] as the file has them
    public static List<(string Role, double Minutes)> Roles(JsonElement[][]? rows) =>
        (rows ?? []).Select(r => (r[0].GetString() ?? "", r[1].GetDouble())).ToList();
}
