using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// What every part of a competition's page starts from (web/src/lib/server/league.ts): the names,
// every club's ratings, and the competition's own file as this visitor may see it (site_league
// gives the whole file to a subscriber and a cut-down one to anyone else). A competition the names
// don't know, with no file, has no page.
public sealed record LeagueBase(int Id, SiteDoc Site, List<Club> All, LeagueFile? Lg, Competition? Comp,
    List<TableRow> Table, List<Fixture> Fixtures, List<(string Text, string Cls)> Zones)
{
    public Dictionary<int, Club> ByTeam { get; } = All.ToDictionary(c => c.Team);

    // a club's name as the competition's file has it (clubs the names row doesn't hold), else the site's
    public string Club(int t) => Lg?.Teams?.GetValueOrDefault(t.ToString()) ?? Site.TeamName(t);

    public static async Task<LeagueBase?> Load(Database db, string param, string? token)
    {
        if (param.Length is 0 or > 7 || !param.All(char.IsAsciiDigit)) return null;
        var id = int.Parse(param);
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var rankingsTask = db.KeptDoc<Rankings>("rankings");
        var lgTask = Safe(db.AskAs<LeagueFile?>(token, "site_league", new { p_id = id }));
        await Task.WhenAll(siteTask, rankingsTask, lgTask);
        var site = siteTask.Result;
        var lg = lgTask.Result;
        var comp = site.Comp(id);
        if (lg is null && comp is null) return null;
        var table = lg is null ? [] : LeagueFiles.TableRows(lg);
        return new(id, site, Clubs.From(rankingsTask.Result), lg, comp, table, lg is null ? [] : LeagueFiles.FixtureRows(lg),
            Leagues.Zones(table.Select(r => r.Description)));
    }

    static async Task<T?> Safe<T>(Task<T?> t) where T : class
    {
        try { return await t; }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or System.Text.Json.JsonException) { return null; }
    }
}

public static class SiteDocs
{
    // A competition's name where competitions from several countries are listed together: its short
    // name, or its own name with the country added when another competition shares it (site.ts)
    public static string CompLabel(this SiteDoc site, int id)
    {
        var c = site.Comp(id);
        if (c is null) return $"Competition {id}";
        if (Names.ShortNames.TryGetValue(id, out var shortName)) return shortName;
        var shared = site.Competitions.Values.Count(x => x.Name == c.Name);
        return c.Country is "England" or "World" || shared == 1 ? c.Name : $"{c.Name} ({SiteDoc.CountryName(c)})";
    }
}
