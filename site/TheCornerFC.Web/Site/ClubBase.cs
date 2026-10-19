using System.Text.RegularExpressions;
using TheCornerFC.Web.Data;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Site;

// What every part of a club's page starts from (web/src/lib/server/club.ts): the names, every
// club's ratings, and this club's own file. A club neither the names nor the ratings know, with no
// file, has no page.
public sealed partial record ClubBase(int Id, SiteDoc Site, List<Club> All, Club? Rank, ClubDoc? Doc, List<ClubMatch> Rows, string Name)
{
    // an opponent's name as the club's file has it (clubs the names row doesn't hold), else the site's
    public string Opponent(int o) => Doc?.Teams?.GetValueOrDefault(o.ToString()) ?? Site.TeamName(o);

    public static async Task<ClubBase?> Load(Database db, string param)
    {
        if (param.Length is 0 or > 9 || !param.All(char.IsAsciiDigit)) return null;
        var id = int.Parse(param);
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var rankingsTask = db.KeptDoc<Rankings>("rankings");
        var docTask = db.KeptDocOrNull<ClubDoc>($"clubs/{id}");
        await Task.WhenAll(siteTask, rankingsTask, docTask);
        var site = siteTask.Result;
        var all = Clubs.From(rankingsTask.Result);
        var rank = all.FirstOrDefault(c => c.Team == id);
        if (docTask.Result is null && rank is null && !site.Teams.ContainsKey(id.ToString())) return null;
        return new(id, site, all, rank, docTask.Result, ClubData.Matches(docTask.Result), site.TeamName(id));
    }

    // The club's matches from the matches table, oldest first, as this visitor may see them;
    // `Paywall`: the database left the paid fields of matches to come out.
    public async Task<(List<Match> Matches, bool Paywall)> Fixtures(Database db, string? token)
    {
        var answer = await db.AskAs<MatchesAnswer>(token, "site_matches", new { p_team = Id });
        return (ClubData.MatchRows(Site, answer), answer.Paywall == true);
    }

    public async Task<Injuries.Team?> InjuryList(Database db)
    {
        try { return (await db.KeptDoc<Injuries>("injuries", TimeSpan.FromMinutes(5))).Teams?.GetValueOrDefault(Id.ToString()); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or System.Text.Json.JsonException) { return null; }
    }

    // Everyone listed at the club, as this visitor may see them (a visitor who isn't a subscriber
    // gets the players outside the free slice with their ranks blanked: `Paywall`)
    public async Task<(List<Player> List, bool Paywall)> Players(Database db, string? token)
    {
        var answer = await db.AskAs<PlayersAnswer>(token, "site_players", new { p_teams = new[] { Id }, p_limit = 2000 });
        var list = ClubData.Players(Site, answer.Rows).Where(p => p.Team == Id).ToList();
        return (list, answer.Paywall == true || list.Any(p => p.Locked));
    }

    public sealed record Squad(Depth.Result? Depth, List<Player> List, Injuries.Team? Inj, Match? Next, List<Match> Matches, bool Paywall, string[]? Kit);

    // The squad by position for the club's next match (Depth), with what it was worked out from
    // (`forLeague`: work it out for a match in that competition, not the club's own next one)
    public async Task<Squad> SquadFor(Database db, string? token, int? forLeague = null)
    {
        var playersTask = Players(db, token);
        var injTask = InjuryList(db);
        var fixturesTask = Fixtures(db, token);
        await Task.WhenAll(playersTask, injTask, fixturesTask);
        var (list, locked) = playersTask.Result;
        var inj = injTask.Result;
        var fixtures = fixturesTask.Result;
        var next = ClubData.Upcoming(fixtures.Matches).FirstOrDefault();
        string GroupOf(int lg)
        {
            var c = Site.Comp(lg);
            return c is null ? "cup" : c.Type == "League" ? "league" : c.Country == "World" ? "europe" : "cup";
        }
        var seasons = ClubPage.SeasonsOf(Rows);
        int? season = Rows.Count > 0 ? seasons.Of(Rows[^1]) : null;
        var depth = TheCornerFC.Web.Site.Depth.Of(new(
            list.Select(p => new Depth.SquadPlayer(p.Id, p.Name, p.Position, p.Rank, p.PositionRanks, p.Positions12m)).ToList(),
            (inj?.Players ?? []).Select(r => r[0].GetInt32()).ToHashSet(),
            Doc?.Starts, Doc?.Positions,
            Rows.Where(m => seasons.Of(m) == season).Select(m => m.Formation).ToList(),
            forLeague is { } fl ? GroupOf(fl) : next is not null ? GroupOf(next.League) : null, GroupOf));
        var colors = Doc?.Colors;
        string[]? kit = colors is { Length: > 0 } && HexRe().IsMatch(colors[0])
            ? [colors[0], colors.Length > 1 && HexRe().IsMatch(colors[1]) ? colors[1] : "ffffff"] : null;
        return new(depth, list, inj, next, fixtures.Matches, locked || fixtures.Paywall, kit);
    }

    [GeneratedRegex("^[0-9a-f]{6}$", RegexOptions.IgnoreCase)] private static partial Regex HexRe();
}
