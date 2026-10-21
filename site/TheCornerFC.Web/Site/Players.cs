using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// A range as the address has it: "20-25", "-25" (up to), "20-" (from); null = that end open
public readonly record struct PickRange(double? Lo, double? Hi)
{
    public bool On => Lo is not null || Hi is not null;
}

// What the Players view's filters can offer (site_player_facets): the age and Ability spans, the
// most minutes, players by position, [club, league] for every club with players, the nationalities.
public sealed record PlayerFacets(int Players, double[]? Age, double[]? Ability, double Minutes,
    Dictionary<string, int> Positions, int[][] Clubs, string[] Nats);

// The club and nationality boxes' lists (/players/options)
public sealed record WhoClub(int Id, string Name, int League, string Key);
public sealed record WhoLeague(int Id, string Name, string? Country, List<int> Clubs);
public sealed record WhoNat(string Name, string Key);
public sealed record WhoOptions(List<WhoClub> Clubs, List<WhoLeague> Leagues, List<WhoNat> Nats);

// A slider: its stops and where its two handles stand
public sealed record Slider(List<double> Stops, int A, int B);

// A player's row as the page draws it, names and all
public sealed record PlayerRow(int Id, string Name, string Short, int? Team, string? TeamName, string League, string? Nat, string? Flag,
    string Pos, int? Age, int? World, int? Lg, int? LgOf, (int? Goals, int? Assists)? Ga,
    double?[]? Seasons, int[] Estimated, double?[]? Future, double? PosRank, double? Skill = null);

// The Players table: what it asks the database's site_players for, and its side filters (the
// ranges and age as two-handled sliders, the position pitch, the club and nationality picks).
// web/src/lib/players.ts, playerFilters.ts and server/players.ts. The database filters, sorts and
// counts; a visitor who isn't a subscriber gets a player outside the free slice with his ranks
// blanked, in the place a subscriber would see him.
public static partial class Players
{
    public const int PageRows = 100;
    static readonly Dictionary<string, string> PosLabel = new() { ["G"] = "GK", ["D"] = "DEF", ["M"] = "MID", ["F"] = "FWD" };

    // ---- Ranges
    public static PickRange ParseRange(string? text)
    {
        var m = RangeRe().Match(text ?? "");
        static double? End(string s) => s == "" ? null : double.Parse(s, CultureInfo.InvariantCulture);
        return m.Success ? new(End(m.Groups[1].Value), End(m.Groups[2].Value)) : default;
    }
    static string N(double v) => v.ToString(CultureInfo.InvariantCulture);
    public static string? RangeText(PickRange r) => r.On ? $"{(r.Lo is { } lo ? N(lo) : "")}-{(r.Hi is { } hi ? N(hi) : "")}" : null;
    // for the database: whole numbers, an open end as null
    public static double?[] RangeParam(PickRange r) => [r.Lo is { } lo ? Math.Ceiling(lo) : null, r.Hi is { } hi ? Math.Floor(hi) : null];

    public static readonly string[] RangeKeys = ["ab", "crank", "mins"];
    public static readonly Dictionary<string, (string Label, string Tip)> RangeInfo = new()
    {
        ["ab"] = ("Ability", "Underlying Ability, 0-100: the model's estimate of his level now"),
        ["crank"] = ("Club world rank", "His club's place among every ranked club by Baseline Strength (1 = strongest). Players without a ranked club drop out while this is set"),
        ["mins"] = ("Minutes", "Minutes over his last 20 appearances, the evidence behind his Ability"),
    };

    // Each slider moves over a list of stops: every age and every whole Ability from the lowest to
    // the highest, minutes a match (90) at a time, and club ranks finer at the top (1, 5, 10, 20
    // ...) so the top 50 can be picked out of thousands. A handle at either end leaves that end open.
    public static List<double> RangeStops(string k, PlayerFacets facets, int rankedClubs)
    {
        static List<double> Span(double[] lohi) =>
            Enumerable.Range(0, Math.Max(0, (int)Math.Floor(lohi[1] - lohi[0] + 1))).Select(i => lohi[0] + i).ToList();
        if (k == "age") return Span(facets.Age ?? [15, 45]);
        if (k == "ab") return Span(facets.Ability ?? [0, 0]);
        if (k == "mins") return Enumerable.Range(0, (int)Math.Ceiling(facets.Minutes / 90) + 1).Select(i => i * 90.0).ToList();
        var n = rankedClubs;
        return [.. new double[] { 1, 5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 400, 500, 750 }.Where(x => x < n),
            .. Enumerable.Range(0, Math.Max(0, (int)Math.Ceiling(n / 500.0) - 1)).Select(i => (i + 2) * 500.0).Where(x => x < n), n];
    }

    // a handle's stop for a range end (one from a link needn't be on a stop: the nearest stop inside it)
    public static int StopIndex(List<double> stops, double? v, int end)
    {
        var n = stops.Count - 1;
        if (v is not { } x) return end == 1 ? n : 0;
        var i = end == 1 ? stops.FindLastIndex(s => s <= x) : stops.FindIndex(s => s >= x);
        return i < 0 ? (end == 1 ? 0 : n) : i;
    }

    // the range two handles stand for
    public static PickRange HandlesRange(List<double> stops, int a, int b) => new(a <= 0 ? null : stops[a], b >= stops.Count - 1 ? null : stops[b]);
    // ... and what the slider says beside its name
    public static string RangeLabel(string k, List<double> stops, int a, int b)
    {
        var n = stops.Count - 1;
        static string Fmt(double v) => v.ToString("#,##0.###", Js.British);
        if (k == "age") return a == 0 && b == n ? "All ages" : a == b ? N(stops[a]) : $"{N(stops[a])}–{N(stops[b])}";
        if (a == 0 && b == n) return "All";
        if (a == 0) return k == "crank" ? $"Top {Fmt(stops[b])}" : $"Up to {Fmt(stops[b])}";
        if (b == n) return $"{Fmt(stops[a])}{(k == "crank" ? " down" : "+")}";
        return $"{Fmt(stops[a])}–{Fmt(stops[b])}";
    }
    // where a handle stands along its track, in whole per cent
    public static int At(int i, int n) => Js.RoundInt((double)i / (n == 0 ? 1 : n) * 100);

    // ---- Position: the selected role groups, and a player's rank as the best of them
    public static bool IsPosition(string p) => Names.PitchSpots.Any(s => s.Role == p);
    public static List<string> SelectedGroups(IEnumerable<string> positions) =>
        positions.Select(r => Names.GroupOf.GetValueOrDefault(r)).Where(g => !string.IsNullOrEmpty(g)).Select(g => g!).Distinct().ToList();
    public static double? PosRank(Dictionary<string, double>? ranks, List<string> groups)
    {
        var v = groups.Where(g => ranks?.ContainsKey(g) == true).Select(g => ranks![g]).ToList();
        return v.Count > 0 ? v.Max() : null;
    }

    // ---- The column the list is sorted on, as the address has it: a season's rank ("s2026": the
    // current season by default), a projected season ("f2028"), "age" (youngest first), "ga" (goals
    // and assists) or "pos" (his rank in the positions picked, which takes Ability's place while any
    // are). With the other seasons closed, only the current one can be sorted on.
    // The skills a list can be sorted by (player_ratings.SKILLS, MC-0030): the sort key is
    // "k_<skill>", and the column shows each player's 0 to 100 score in it
    public static readonly (string Key, string Label, string Tip)[] Skills =
    [
        ("finishing", "Finishing", "Goals and shots on target per 90"),
        ("creating", "Creating", "Key passes and assists per 90"),
        ("passing", "Passing", "Passes per 90 and pass accuracy"),
        ("dribbling", "Dribbling", "Dribbles won per 90, less the ones lost"),
        ("ball_winning", "Ball-winning", "Tackles, interceptions and blocks per 90"),
        ("duels", "Duels", "Share of duels won (all duels: the data doesn't split out aerial ones)"),
        ("solidity", "Solidity", "Times dribbled past and his team's xG conceded while he plays, both per 90 (fewer is better)"),
    ];
    public static string? SkillOf(string sort) => sort.StartsWith("k_", StringComparison.Ordinal) && Skills.Any(s => "k_" + s.Key == sort) ? sort[2..] : null;

    public static string SortKey(string? asked, int[] seasons, int[] future, bool open, List<string> groups)
    {
        var now = groups.Count > 0 ? "pos" : $"s{seasons[0]}";
        if (asked is "age" or "ga") return asked;
        if (asked is not null && SkillOf(asked) is not null) return asked;
        if (string.IsNullOrEmpty(asked) || !open || asked == "pos") return now;
        if (asked == $"s{seasons[0]}") return now;
        var ok = int.TryParse(asked[1..], NumberStyles.None, CultureInfo.InvariantCulture, out var y);
        return ok && ((asked[0] == 's' && seasons.Contains(y)) || (asked[0] == 'f' && future.Contains(y))) ? asked : now;
    }
    // the same for the database: seasons and projected seasons by their place, newest first
    static string SortParam(string key, int[] seasons, int[] future) =>
        key is "age" or "ga" or "pos" || SkillOf(key) is not null ? key
        : key[0] == 'f' ? $"f{Array.IndexOf(future, int.Parse(key[1..]))}" : $"s{Array.IndexOf(seasons, int.Parse(key[1..]))}";

    // ---- The page's choices, as its address has them
    public sealed record Choices(string Filter, IReadOnlySet<string> Excluded, IReadOnlyList<string> ExcludedList, string Search, string Sort,
        Dictionary<string, PickRange> Ranges, List<string> Positions, List<int> Clubs, List<string> Nats);

    // What the Players page and its "more rows" requests both start from: the names, the clubs, the
    // cups, what the filters can offer, and the page's choices as its address has them.
    public sealed record Base(SiteDoc Site, List<Club> All, Dictionary<int, HashSet<int>> Cups, PlayerFacets Facets, List<Country> Countries,
        bool Years, Choices Choices, List<string> Groups);

    public static Task<PlayerFacets> Facets(Database db) => db.KeptAsk<PlayerFacets>("site_player_facets", new { }, TimeSpan.FromMinutes(5));

    public static async Task<Base> Load(Database db, IQueryCollection q)
    {
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var docTask = db.KeptDoc<Rankings>("rankings");
        var cupsTask = Cups.Load(db);
        var facetsTask = Facets(db);
        await Task.WhenAll(siteTask, docTask, cupsTask, facetsTask);
        var site = siteTask.Result;
        var all = Clubs.From(docTask.Result);
        var countries = ClubTable.Countries(site, all);
        var years = q["y"].ToString() == "1";
        var positions = q["pos"].ToString().Split(',').Where(IsPosition).ToList();
        var groups = SelectedGroups(positions);
        var excluded = q["ex"].ToString().Split('|').Where(ClubTable.IsExcludeKey).Distinct().ToList();
        var search = q["q"].ToString();
        var c = q["c"].ToString();
        var choices = new Choices(
            ClubTable.KnownFilter(c, countries) ? c : "all",
            excluded.ToHashSet(), excluded,
            search.Length > 80 ? search[..80] : search,
            SortKey(q["sort"].ToString(), site.PlayerSeasons!, site.PlayerFutureSeasons ?? [], years, groups),
            new[] { "age", "ab", "crank", "mins" }.ToDictionary(k => k, k => ParseRange(q[k].ToString())),
            positions,
            q["club"].ToString().Split(',').Select(s => int.TryParse(s, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var n) ? n : 0)
                .Where(n => n > 0).Distinct().Take(50).ToList(),
            q["nat"].ToString().Split('|').Where(n => n.Length is > 0 and <= 60).Distinct().Take(50).ToList());
        return new(site, all, cupsTask.Result, facetsTask.Result, countries, years, choices, groups);
    }

    // ---- What to ask site_players
    static List<int> ExcludedLeagues(SiteDoc site, IReadOnlySet<string> ex) =>
        site.Competitions.Keys.Select(int.Parse).Order().Where(id => ClubTable.IsExcluded(site, ex, id)).ToList();

    // the side filters, which narrow the list and the menu's numbers alike
    static Dictionary<string, object?> SideParams(Choices ch)
    {
        var p = new Dictionary<string, object?>();
        void AddRange(string k) { if (ch.Ranges[k].On) p[$"p_{k}"] = RangeParam(ch.Ranges[k]); }
        AddRange("age");
        if (ch.Positions.Count > 0) p["p_positions"] = ch.Positions;
        if (ch.Clubs.Count > 0) p["p_teams"] = ch.Clubs;
        if (ch.Nats.Count > 0) p["p_nats"] = ch.Nats;
        AddRange("ab"); AddRange("crank"); AddRange("mins");
        return p;
    }

    // The search, for the database: his name as typed, and for each word the clubs whose search text
    // it fits (worked out here, where the clubs' short forms, leagues and countries are known). Each
    // word is "word|1 if it fits a player with no club|the ids of the clubs it fits".
    public static (string Q, List<string> Words) SearchParams(SiteDoc site, List<Club> all, PlayerFacets facets, string q)
    {
        var byTeam = all.GroupBy(r => r.Team).ToDictionary(g => g.Key, g => g.Last());
        var texts = new Dictionary<int, string>();
        string ClubText(int team) => texts.TryGetValue(team, out var t) ? t
            : texts[team] = byTeam.TryGetValue(team, out var club) ? ClubTable.SearchText(site, club) : $" {ClubTable.FoldText(site.TeamName(team))} ";
        static bool Fits(string text, string w) => text.Contains(" " + w);
        var noClub = $" {ClubTable.FoldText("Team null")} "; // what the old site's search knew a player with no club as
        var words = ClubTable.FoldText(q).Split(' ', StringSplitOptions.RemoveEmptyEntries)
            .Select(w => $"{w}|{(Fits(noClub, w) ? 1 : 0)}|{string.Join(',', facets.Clubs.Where(c => Fits(ClubText(c[0]), w)).Select(c => c[0]))}")
            .ToList();
        return (q, words);
    }

    // What to ask site_players for the list. A search looks at every player, whatever the menu and
    // the exclusions say; a club pick shows that club's players whatever league is selected.
    public static Dictionary<string, object?> ListParams(Base b)
    {
        var (site, ch) = (b.Site, b.Choices);
        var p = SideParams(ch);
        var q = ch.Search.Trim().ToLowerInvariant();
        if (q != "")
        {
            var (pq, words) = SearchParams(site, b.All, b.Facets, q);
            p["p_q"] = pq;
            p["p_words"] = words;
        }
        else if (ch.Clubs.Count == 0)
        {
            if (ClubTable.IsCupFilter(ch.Filter)) p["p_teams"] = ClubTable.CupTeams(ch.Filter, b.Cups).ToList();
            else if (ClubTable.FilterLeagues(ch.Filter, b.Countries) is { } ids) p["p_leagues"] = ids;
            var ex = ExcludedLeagues(site, ch.Excluded);
            if (ex.Count > 0) p["p_not_leagues"] = ex;
        }
        p["p_sort"] = SortParam(ch.Sort, site.PlayerSeasons!, site.PlayerFutureSeasons ?? []);
        if (ch.Sort == "pos") p["p_groups"] = SelectedGroups(ch.Positions);
        return p;
    }

    // ... and for the numbers in the competition menu: players by league and club, with the side
    // filters and the exclusions applied (the menu's own pick and the search don't count)
    public static Dictionary<string, object?> CountParams(SiteDoc site, Choices ch)
    {
        var p = SideParams(ch);
        var not = ExcludedLeagues(site, ch.Excluded);
        if (not.Count > 0) p["p_not_leagues"] = not;
        p["p_count"] = true;
        return p;
    }

    public sealed record CountsAnswer(int?[][]? Counts);

    // how many players each choice in the menu shows, from [[league, club, players]] (a player with
    // no league or no club: null)
    public static Func<string, int> Counts(int?[][] counts, List<Country> countries, Dictionary<int, HashSet<int>> cups)
    {
        var byLeague = new Dictionary<int, int>();
        var total = 0;
        foreach (var c in counts)
        {
            var n = c[2] ?? 0;
            if (c[0] is { } lg) byLeague[lg] = byLeague.GetValueOrDefault(lg) + n;
            total += n;
        }
        return value =>
        {
            if (value == "all") return total;
            if (ClubTable.IsCupFilter(value)) { var teams = ClubTable.CupTeams(value, cups); return counts.Where(c => c[1] is { } t && teams.Contains(t)).Sum(c => c[2] ?? 0); }
            return (ClubTable.FilterLeagues(value, countries) ?? []).Sum(id => byLeague.GetValueOrDefault(id));
        };
    }

    // A page of the list from `offset`, as this visitor may see it (`token`: theirs, if signed in)
    public static async Task<(int Total, bool Paywall, List<PlayerRow> Rows)> Page(Database db, Base b, int offset, string? token)
    {
        var p = ListParams(b);
        p["p_limit"] = PageRows;
        p["p_offset"] = offset;
        var answer = await db.AskAs<PlayersAnswer>(token, "site_players", p);
        return (answer.Total, answer.Paywall == true, ClubData.Players(b.Site, answer.Rows ?? []).Select(x => RowView(b.Site, x, b.Groups, SkillOf(b.Choices.Sort))).ToList());
    }

    static PlayerRow RowView(SiteDoc site, Player p, List<string> groups, string? skill) => new(
        p.Id, p.Name, ClubPage.ShortName(p.Name), p.Team, p.Team is { } t and not 0 ? site.TeamName(t) : null,
        p.League is { } lg ? site.LeagueShort(lg) : "",
        p.Nationality, p.Nationality is { Length: > 0 } nat
            ? Names.FlagCodes.GetValueOrDefault(ClubTable.CountryDisplay(nat)) ?? Names.FlagCodes.GetValueOrDefault(nat) : null,
        p.Position is { Length: > 0 } pos ? PosLabel.GetValueOrDefault(pos) ?? pos : "",
        p.Age, p.World, p.Lg, p.LgOf, p.Season is { } s ? (s.Goals, s.Assists) : null,
        p.Seasons, p.Estimated ?? [], p.Future,
        // his rank in the positions picked: his best of them, null if he has started in none
        groups.Count > 0 ? PosRank(p.PositionRanks, groups) : null,
        // his score in the skill the list is sorted by
        skill is null ? null : p.Skills?.GetValueOrDefault(skill) is { } v ? v : null);

    // ---- Club and nationality: what the two boxes list: clubs (the league added to a name two
    // clubs share), the same clubs under their leagues in the competition menu's order, and the
    // nationalities; each with a key for accent-free matching.
    public static string WhoKey(string s)
    {
        var sb = new StringBuilder();
        foreach (var ch in s.Normalize(NormalizationForm.FormD))
            if (CharUnicodeInfo.GetUnicodeCategory(ch) != UnicodeCategory.NonSpacingMark) sb.Append(ch);
        return sb.ToString().ToLowerInvariant();
    }

    public static WhoOptions Who(SiteDoc site, PlayerFacets facets, List<Country> countries)
    {
        var names = new Dictionary<string, int>();
        foreach (var c in facets.Clubs) { var n = site.TeamName(c[0]); names[n] = names.GetValueOrDefault(n) + 1; }
        var clubs = facets.Clubs.Select(c =>
        {
            var n = site.TeamName(c[0]);
            var name = names[n] > 1 ? $"{n} ({site.LeagueName(c[1])})" : n;
            return new WhoClub(c[0], name, c[1], WhoKey(name));
        }).OrderBy(c => c.Name, Js.Compare).ToList();
        var order = countries.SelectMany(c => c.Leagues).ToList();
        int Pos(int lg) { var i = order.IndexOf(lg); return i == -1 ? order.Count : i; }
        var byLeague = new Dictionary<int, List<int>>();
        foreach (var c in clubs) { if (!byLeague.TryGetValue(c.League, out var l)) byLeague[c.League] = l = []; l.Add(c.Id); }
        var leagues = byLeague.Select(kv => new WhoLeague(kv.Key, site.LeagueName(kv.Key), site.Comp(kv.Key)?.Country, kv.Value))
            .OrderBy(l => Pos(l.Id)).ThenBy(l => l.Name, Js.Compare).ToList();
        return new(clubs, leagues, facets.Nats.OrderBy(n => n, Js.Compare).Select(n => new WhoNat(n, WhoKey(n))).ToList());
    }

    // ---- A player's clubs season by season, for the tip over a season's rank. Each season:
    // [club, his rank there, minutes, goals, assists].
    public static Dictionary<string, object?[][]> SeasonSpells(SiteDoc site, PlayerDoc? doc) =>
        (doc?.Spells?.Keys ?? Enumerable.Empty<string>()).ToDictionary(y => y, y => PlayerFiles.Spells(doc, y)
            .Select(s => new object?[] { doc!.Teams?.GetValueOrDefault(s.Team.ToString()) is { Length: > 0 } t ? t : site.TeamName(s.Team),
                s.ClubRank, s.Minutes ?? 0, s.Goals ?? 0, s.Assists ?? 0 }).ToArray());

    [GeneratedRegex(@"^([0-9]*(?:\.[0-9]+)?)-([0-9]*(?:\.[0-9]+)?)$")] private static partial Regex RangeRe();
}
