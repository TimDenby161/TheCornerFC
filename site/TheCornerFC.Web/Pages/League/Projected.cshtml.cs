using System.Collections.Concurrent;
using Microsoft.AspNetCore.Mvc;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.League;

// The projected table. The whole of it (the rest of the season played out from the model's
// predictions) is for subscribers; anyone else gets the headline the database sends: where the
// model expects each club to finish, and on how many points. The Svelte site plays the season out
// in the browser (its Worker has 10 ms of CPU a request); this server does it, once per
// competition and data, and keeps the answer.
public sealed class ProjectedModel(Database db, TimeProvider clock) : LeaguePage(db)
{
    public sealed record HeadlineRow(Headline X, string Name, string Zone);
    public sealed record ZoneCol(string Text, string Cls, List<int> Places);
    public sealed record Group(string Name, List<string> Zones, List<ZoneCol> Cols, List<Projection.Projected> Played);

    public bool Headline { get; private set; }
    public bool Several { get; private set; }
    public List<(string Name, List<HeadlineRow> Rows)> HeadlineGroups { get; private set; } = [];
    public List<Group> Groups { get; private set; } = [];
    public int Left { get; private set; }

    static readonly ConcurrentDictionary<string, (DateTimeOffset At, List<Projection.Projected>[] Played)> Kept = new();

    protected override Task<IActionResult?> Load()
    {
        var groups = L.Table.Select(r => r.Group).Distinct().ToList();
        Several = groups.Count > 1;
        // the zone a place carries today, by group
        string ZoneAt(string? g, int place) => Leagues.ZoneOf(L.Zones, L.Table.FirstOrDefault(r => r.Group == g && r.Rank == place)?.Description);
        if (L.Lg?.Cut == true)
        {
            Headline = true;
            var list = LeagueFiles.Headline(L.Lg);
            HeadlineGroups = list.Select(x => x.Group).Distinct()
                .Select(g => (g ?? "", list.Where(x => x.Group == g).Select(x => new HeadlineRow(x, L.Club(x.Team), ZoneAt(g, x.Place))).ToList())).ToList();
            return Task.FromResult<IActionResult?>(null);
        }
        var upcoming = Projection.Projectable(L.Fixtures);
        Left = upcoming.Count;
        if (Left == 0) return Task.FromResult<IActionResult?>(null);
        // played out once for this competition and these fixtures, then kept for ten minutes
        var key = $"{L.Id}:{L.Lg?.Season}:{string.Join(',', upcoming.Select(f => $"{f.Id}/{f.PHome}/{f.HomeXg}/{f.AwayXg}"))}:{string.Join(',', L.Table.Select(r => $"{r.Team}/{r.Points}/{r.Gd}"))}";
        var now = clock.GetUtcNow();
        if (!Kept.TryGetValue(key, out var have) || now - have.At > TimeSpan.FromMinutes(10))
        {
            have = (now, groups.Select(g => Projection.Group(L.Table.Where(r => r.Group == g).ToList(), upcoming)).ToArray());
            Kept[key] = have;
            foreach (var (k, v) in Kept) if (now - v.At > TimeSpan.FromMinutes(10)) Kept.TryRemove(k, out _);
        }
        Groups = groups.Select((g, k) =>
        {
            var rows = L.Table.Where(r => r.Group == g).ToList();
            // a zone's chance is the chance of finishing in any of the places carrying its note today
            var cols = L.Zones.Where(z => rows.Any(r => r.Description == z.Text))
                .Select(z => new ZoneCol(z.Text, z.Cls, rows.Where(r => r.Description == z.Text).Select(r => r.Rank - 1).ToList())).ToList();
            return new Group(g ?? "", rows.Select(r => ZoneAt(g, r.Rank)).ToList(), cols, have.Played[k]);
        }).ToList();
        return Task.FromResult<IActionResult?>(null);
    }
}
