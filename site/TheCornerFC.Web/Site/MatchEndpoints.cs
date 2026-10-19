using System.Text.Json;
using System.Text.RegularExpressions;
using TheCornerFC.Web.Data;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Site;

// What a match card asks for as it is opened or comes into view (web/src/routes/(app)/match/[id]):
// its line-ups, its model detail and both clubs' expected squads, as JSON for the card's React part.
public static partial class MatchEndpoints
{
    sealed record LineupsAnswer(bool? Locked, Dictionary<string, JsonElement[][]>? Xi, Dictionary<string, JsonElement[][]>? Actual, Dictionary<string, JsonElement[][]>? Prematch);

    // One match by its id, as this visitor may see it (`Paywall`: the database held paid fields back)
    static async Task<(SiteDoc Site, Match M, bool Paywall)?> Base(Database db, string param, string? token)
    {
        if (!IdRe().IsMatch(param)) return null;
        var site = await db.KeptDoc<SiteDoc>("site");
        var answer = await db.AskAs<MatchesAnswer>(token, "site_matches", new { p_ids = new[] { long.Parse(param) } });
        var m = ClubData.MatchRows(site, answer).FirstOrDefault();
        return m is null ? null : (site, m, answer.Paywall == true);
    }
    static async Task<DetailAnswer?> Why(Database db, int id, string? token)
    {
        try { return await db.AskAs<DetailAnswer?>(token, "site_match_detail", new { p_fixture = id }); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { return null; }
    }
    static bool IsFinished(Match m) => ClubData.Finished.Contains(m.Status) && m.Hg is not null;
    static IResult Json(object? o) => Results.Json(o, Database.Json);

    public static void Map(WebApplication app)
    {
        // A match's model detail, asked for when its card's "Model detail" is opened
        app.MapGet("/match/{id}/detail", async (string id, HttpContext c, Database db) =>
        {
            var token = Visitor.Of(c).Token;
            if (await Base(db, id, token) is not { } b) return Results.NotFound();
            var row = await Why(db, b.M.Id, token);
            c.Response.Headers.CacheControl = token is not null ? "private, no-store" : "public, max-age=60";
            if (row?.Locked == true) return Json(new { locked = true });
            return Json(MatchDetail.Of(b.M, row?.Why, row?.Why is null ? null : row.Model, b.Site.TeamName(b.M.Home), b.Site.TeamName(b.M.Away)));
        });

        // Both clubs' expected squads for an upcoming match (their attack, defence and overall
        // rating, from expected minutes), asked for when its card comes into view. They rest on the
        // players' ranks, so a visitor the database sends cut-down data gets none.
        app.MapGet("/match/{id}/squads", async (string id, HttpContext c, Database db) =>
        {
            var token = Visitor.Of(c).Token;
            if (await Base(db, id, token) is not { } b) return Results.NotFound();
            c.Response.Headers.CacheControl = "private, no-store";
            var m = b.M;
            var upcoming = !IsFinished(m) && !ClubData.Live.Contains(m.Status) && !ClubData.NoGame.Contains(m.Status);
            if (!upcoming || m.Intl is > 0 || b.Paywall) return Json(null);
            async Task<object?> Side(int team, double? recent)
            {
                var club = await ClubBase.Load(db, team.ToString());
                if (club is null) return null;
                var sq = await club.SquadFor(db, token, m.League);
                var s = sq.Paywall ? null : Depth.SquadStrength(sq.Depth);
                if (s is not { Attack: { } att, Defence: { } dfn }) return null;
                var now = Js.RoundInt(s.Overall);
                int? then = recent is { } r ? Js.RoundInt(r) : null;
                return new { attack = Js.RoundInt(att), defence = Js.RoundInt(dfn), strength = now, recent = then,
                    trend = then is not { } t ? "" : now > t ? "good" : now < t ? "bad" : "same" };
            }
            var sides = await Task.WhenAll(Side(m.Home, m.HomeRecentXi), Side(m.Away, m.AwayRecentXi));
            return Json(sides[0] is not null && sides[1] is not null ? new { home = sides[0], away = sides[1] } : null);
        });

        // One match's line-ups by team (site_lineups): predicted, as started, and as predicted
        // before the team sheet. Not kept between openings: a line-up can change before kick-off.
        app.MapGet("/match/{id}/lineups", async (string id, HttpContext c, Database db) =>
        {
            var token = Visitor.Of(c).Token;
            if (await Base(db, id, token) is not { } b) return Results.NotFound();
            c.Response.Headers.CacheControl = "private, no-store";
            return Json(await Lineups(db, b.Site, b.M, b.Paywall, token));
        });
    }

    static object SpotsJson(List<Lineups.Spot> spots) => spots.Select(s => new
    {
        id = s.Id, name = s.Name, label = s.Label, x = s.X, y = s.Y, rank = s.Rank, chance = s.Chance, mins = s.Mins, predicted = s.Predicted,
        instead = s.Instead is { } i ? new { name = i.Name, rank = i.Rank } : null, tip = s.Tip,
    }).ToList();

    static async Task<object> Lineups(Database db, SiteDoc site, Match m, bool paywall, string? token)
    {
        var finished = IsFinished(m);

        // A national match: each side's predicted XI comes with the match's model detail; no player ranks
        if (m.Intl is > 0)
        {
            var row = await Why(db, m.Id, token);
            if (row?.Locked == true) return new { locked = true };
            object NationSide(int team)
            {
                var rows = row?.Why?.Xi?.GetValueOrDefault(team.ToString());
                var xi = rows is { Length: > 0 }
                    ? Site.Lineups.Spots(rows.Select(r => new Lineups.Starter(r[0].GetInt32(), ClubData.Decode(r[1].GetString() ?? ""), r[2].GetString() ?? "", null)).ToList(), false)
                    : null;
                return new { label = site.TeamName(team), score = (object?)null, kit = (string[]?)null, ranks = false, spots = xi is null ? null : SpotsJson(xi),
                    note = xi is not null ? "" : "No predicted XI for this team." };
            }
            return new { sides = new[] { NationSide(m.Home), NationSide(m.Away) }, marked = false,
                note = "From each side's recent national team matches. Call-ups, injuries and suspensions aren't known before the team sheet." };
        }

        LineupsAnswer? fx;
        try { fx = await db.AskAs<LineupsAnswer?>(token, "site_lineups", new { p_fixture = m.Id }); }
        catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { fx = null; }
        // predicted line-ups are for subscribers
        if (!finished && (fx?.Locked == true || paywall)) return new { locked = true };
        var exact = ((finished ? fx?.Actual : fx?.Xi) ?? []).ToDictionary(kv => kv.Key, kv => kv.Value.Select(Site.Lineups.ReadRow).ToList());
        // a match to come shows each predicted starter's rank in the position he is picked in, as
        // his own page has it, not the rank over his recent matches the stored line-up carries: one
        // read for both elevens
        if (!finished)
        {
            var ids = exact.Values.SelectMany(rows => rows.Select(r => r.Pid)).ToArray();
            PlayersAnswer? answer = null;
            if (ids.Length > 0)
                try { answer = await db.AskAs<PlayersAnswer>(token, "site_players", new { p_ids = ids, p_limit = ids.Length }); }
                catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { }
            var players = new Dictionary<int, Player>();
            foreach (var p in ClubData.Players(site, answer?.Rows ?? [])) players[p.Id] = p;
            exact = exact.ToDictionary(kv => kv.Key, kv => Site.Lineups.WithSlotRank(kv.Value, players));
        }

        async Task<object> Side(int team, bool home)
        {
            double? rating = home ? m.HomeXi : m.AwayXi, recent = home ? m.HomeRecentXi : m.AwayRecentXi;
            // the heading's number is the average of the ranks on the pitch under it: the stored XI
            // rating for a finished match, the eleven's average rank in their positions for one to come
            string Heading(int? average) => $"{site.TeamName(team)}{(finished
                ? rating is { } rt ? $" · rating {Js.RoundInt(rt)}{(recent is { } rc ? $" (recent {Js.RoundInt(rc)})" : "")}" : ""
                : average is { } a ? $" · average rank {a}" : "")}";
            ClubBase? club;
            try { club = await ClubBase.Load(db, team.ToString()); }
            catch (Exception e) when (e is DatabaseException or HttpRequestException or TaskCanceledException or JsonException) { club = null; }
            var colors = club?.Doc?.Colors;
            string[]? kit = colors is { Length: > 0 } && HexRe().IsMatch(colors[0])
                ? [colors[0], colors.Length > 1 && HexRe().IsMatch(colors[1]) ? colors[1] : "ffffff"] : null;
            if (exact.GetValueOrDefault(team.ToString()) is { Count: > 0 } listed)
            {
                var xi = listed.Select(r => new Lineups.Starter(r.Pid, r.Name, r.Role is { Length: > 0 } role ? role : "CM", r.Rank)).ToList();
                var predicted = finished ? fx?.Prematch?.GetValueOrDefault(team.ToString())?.Select(Site.Lineups.ReadRow).ToList() : null;
                object? score = null;
                if (predicted is { Count: > 0 })
                {
                    var (markedXi, hits) = Site.Lineups.MarkPredicted(xi, predicted);
                    xi = markedXi;
                    score = new { hits, of = xi.Count, cls = hits >= 9 ? "good" : hits >= 7 ? "ok" : "poor" };
                }
                return new { label = Heading(Site.Lineups.AverageRank(xi.Select(s => s.Rank))), kit, ranks = true, spots = SpotsJson(Site.Lineups.Spots(xi)), note = "", score };
            }
            if (finished) return new { label = Heading(null), kit, ranks = true, spots = (object?)null, score = (object?)null, note = "No actual line-up for this team." };
            // no stored prediction: the one the squad model gives for a match in this competition
            var picks = club is null ? null : Depth.PredictedXi((await club.SquadFor(db, token, m.League)).Depth);
            var starters = picks?.Select(p => new Lineups.Starter(p.P.Id, p.P.Name, p.Box.Label, p.Rank, p.Chance, p.Mins)).ToList();
            return new { label = Heading(Site.Lineups.AverageRank((starters ?? []).Select(s => s.Rank))), kit, ranks = true, score = (object?)null,
                note = starters is not null ? "" : "No predicted XI for this team.", spots = starters is null ? null : SpotsJson(Site.Lineups.Spots(starters)) };
        }
        var sides = await Task.WhenAll(Side(m.Home, true), Side(m.Away, false));
        return new { sides, marked = finished && fx?.Prematch is not null, note = "" };
    }

    [GeneratedRegex("^[0-9]{1,10}$")] private static partial Regex IdRe();
    [GeneratedRegex("^[0-9a-f]{6}$", RegexOptions.IgnoreCase)] private static partial Regex HexRe();
}
