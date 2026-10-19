using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// What every part of a nation's page starts from (web/src/lib/server/nation.ts): the nationality's
// ranked club players (as this visitor may see them), the nation's place in the ranking, and,
// where the feed has its internationals, the national team's own file. A name with neither
// players nor a ranking has no page (null).
public sealed record NationBase(SiteDoc Site, string Name, List<Player> List, Nation.Team? Team, Dictionary<int, Player> Known,
    bool Paywall, Nation.Spell? Spell, NationBase.Rating? Rated)
{
    public sealed record Rating(int Current, int Tier, int Rank, int Of, int? Change);

    // every player that fits, 2,000 a request (the most site_players sends)
    static async Task<(List<Player> Players, bool Paywall)> EveryPlayer(Database db, SiteDoc site, string? token, Dictionary<string, object?> ask)
    {
        var all = new List<Player>();
        var paywall = false;
        for (int at = 0, total = 1; at < total;)
        {
            var p = new Dictionary<string, object?>(ask) { ["p_limit"] = 2000, ["p_offset"] = at };
            var d = await db.AskAs<PlayersAnswer>(token, "site_players", p);
            paywall |= d.Paywall == true;
            if (d.Rows is not { Length: > 0 }) break;
            all.AddRange(ClubData.Players(site, d.Rows));
            at += d.Rows.Length;
            total = d.Total;
        }
        return (all, paywall);
    }

    public static async Task<NationBase?> Load(Database db, string name, string? token)
    {
        if (string.IsNullOrEmpty(name) || name.Length > 60) return null;
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var rankingTask = OrNull(db.KeptDoc<NationsDoc>("nations", TimeSpan.FromMinutes(5)));
        await Task.WhenAll(siteTask, rankingTask);
        var (site, ranking) = (siteTask.Result, rankingTask.Result);
        var (players, paywall) = await EveryPlayer(db, site, token, new() { ["p_nats"] = new[] { name } });
        var list = players.Where(p => p.Nationality == name).Select((p, i) => (p, i))
            .OrderBy(t => t.p.Ord ?? 1e9).ThenBy(t => t.p.Name, Js.Compare).ThenBy(t => t.i).Select(t => t.p).ToList();
        var n = ranking is null ? null : Nation.For(ranking, name);
        if (list.Count == 0 && n is null) return null;
        var doc = n?.TeamId is { } tid ? await OrNull(db.KeptDocOrNull<NationDoc>($"nations/{tid}", TimeSpan.FromMinutes(5))) : null;
        var team = doc?.Matches is { Length: > 0 } ? Nation.ReadTeam(doc) : null;
        // the squad's own rows in the Players list, for their ranks, clubs and links to their pages
        var listed = list.Select(p => p.Id).ToHashSet();
        var squadIds = team is null ? [] : team.Players.Keys.Where(id => !listed.Contains(id)).ToArray();
        var squad = squadIds.Length > 0 ? (await EveryPlayer(db, site, token, new() { ["p_ids"] = squadIds })).Players : [];
        var known = new Dictionary<int, Player>();
        foreach (var p in list.Concat(squad)) known[p.Id] = p;
        Rating? rated = n is not null && ranking is not null
            ? new(Js.RoundInt(n.Current), ranking.Tier(n.Current), ranking.Nations.Count(x => x.Current > n.Current) + 1, ranking.Nations.Count,
                n.YearAgo is { } y ? Js.RoundInt(n.Current - y) : null)
            : null;
        return new(site, name, list, team, known, paywall || list.Any(p => p.Locked), team is null ? null : Nation.SpellOf(team), rated);
    }

    static async Task<T?> OrNull<T>(Task<T> t) where T : class
    {
        try { return await t; }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or System.Text.Json.JsonException) { return null; }
    }

    // players their club's latest injury list has missing through injury (the list's "injured" flag)
    public static async Task<HashSet<int>> InjuredPlayers(Database db)
    {
        var d = await OrNull(db.KeptDoc<Injuries>("injuries", TimeSpan.FromMinutes(5)));
        var outs = new HashSet<int>();
        var fields = d?.Fields ?? [];
        int pi = Array.IndexOf(fields, "player"), ii = Array.IndexOf(fields, "injured");
        if (pi < 0 || ii < 0) return outs;
        foreach (var t in d!.Teams?.Values ?? Enumerable.Empty<Injuries.Team>())
            foreach (var r in t.Players)
                if (ii < r.Length && Truthy(r[ii]) && pi < r.Length && r[pi].ValueKind == System.Text.Json.JsonValueKind.Number) outs.Add(r[pi].GetInt32());
        return outs;
    }
    static bool Truthy(System.Text.Json.JsonElement e) => e.ValueKind switch
    {
        System.Text.Json.JsonValueKind.True => true,
        System.Text.Json.JsonValueKind.Number => e.GetDouble() != 0,
        System.Text.Json.JsonValueKind.String => e.GetString() != "",
        _ => false,
    };
}
