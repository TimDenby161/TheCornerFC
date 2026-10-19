using System.Text.Json;
using System.Text.Json.Serialization;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// A national team's own file (nations/<team id>: its matches, line-ups and stat lines from
// API-Football; web/src/lib/nation.ts). Nothing here is a model: the "predicted XI" is read off
// the current coach's recent team sheets.
public sealed record NationDoc(int Id, string? Name, NationDoc.Head? Coach,
    [property: JsonPropertyName("match_fields")] string[] MatchFields, JsonElement[][] Matches,
    [property: JsonPropertyName("app_fields")] string[] AppFields, JsonElement[][] Apps,
    Dictionary<string, string> Players)
{
    public sealed record Head(int? Id, string? Name, string? Since);
}

public static class Nation
{
    public sealed record App(int Match, int Player, int? Minutes, int Started, string? Role, int? Goals, int? Assists, int? Yellow, int? Red);
    public sealed record NatMatch(int I, string Date, string Opp, string Venue, int Gf, int Ga, string? Tournament, string? Formation,
        string? Coach, int? CoachId, List<App> Xi);
    public sealed record Team(List<NatMatch> Matches, List<App> Apps, Dictionary<int, string> Players, NationDoc.Head? Coach)
    {
        public string? PlayerName(int id) => Players.GetValueOrDefault(id);
    }

    // A nation's file made ready: names as text (API-Football sends some HTML-encoded), each match
    // with the eleven that started it
    public static Team ReadTeam(NationDoc doc)
    {
        static string? Text(string? t) => t is null ? null : ClubData.Decode(t);
        var matches = doc.Matches.Select((r, i) =>
        {
            var n = new Named(doc.MatchFields, r);
            return new NatMatch(i, n.S("date") ?? "", Text(n.S("opp")) ?? "", n.S("venue") ?? "", n.I("gf") ?? 0, n.I("ga") ?? 0,
                Text(n.S("tournament")), n.S("formation"), Text(n.S("coach")), n.I("coach_id"), []);
        }).ToList();
        var apps = doc.Apps.Select(r =>
        {
            var n = new Named(doc.AppFields, r);
            return new App(n.I("match") ?? -1, n.I("player") ?? 0, n.I("minutes"), n.I("started") ?? 0, n.S("role"),
                n.I("goals"), n.I("assists"), n.I("yellow"), n.I("red"));
        }).ToList();
        foreach (var a in apps) if (a.Started != 0 && a.Match >= 0 && a.Match < matches.Count) matches[a.Match].Xi.Add(a);
        var coach = doc.Coach is { Name: { Length: > 0 } name } c ? c with { Name = ClubData.Decode(name) } : doc.Coach;
        return new(matches, apps, doc.Players.ToDictionary(kv => int.Parse(kv.Key), kv => ClubData.Decode(kv.Value)), coach);
    }

    // The current coach's matches (oldest first). With his start date (when he's the coach on the
    // latest team sheet): the matches since then. Else his unbroken spell up to the latest match on
    // the team sheets, from his first known one. Every match when the latest names no coach.
    // Full: the stored matches go back to the start of his spell
    public sealed record Spell(string? Coach, int? CoachId, string? Since, List<NatMatch> Rows, bool Full);
    public static Spell SpellOf(Team team)
    {
        var rows = team.Matches;
        var head = team.Coach;
        var last = rows[^1];
        if (head?.Since is { } since && head.Name is { Length: > 0 } && (last.CoachId is null || last.CoachId == head.Id))
        {
            var list = rows.Where(m => string.CompareOrdinal(m.Date, since) >= 0).ToList();
            if (list.Count > 0) return new(head.Name, head.Id, since, list, string.CompareOrdinal(rows[0].Date, since) <= 0);
        }
        var coach = last.Coach;
        if (string.IsNullOrEmpty(coach)) return new(null, null, null, rows, false);
        var k = rows.Count;
        while (k > 0 && (rows[k - 1].Coach == coach || rows[k - 1].Coach is null)) k--;
        while (rows[k].Coach is null) k++;
        return new(coach, last.CoachId, null, rows[k..], k > 0);
    }
    public static string SpellLabel(Spell s) => s.Coach is not null ? $"Under {s.Coach}" : "All matches (coach not known)";

    public static readonly string[] RoleOrder = ["GK", "RB", "RWB", "CB", "LB", "LWB", "DM", "RM", "CM", "LM", "AM", "RW", "ST", "LW"];
    public static int Order(string? r) { var i = Array.IndexOf(RoleOrder, r ?? ""); return i == -1 ? 99 : i + 1; }
    // Each role's cell on the overview pitch (row, column; column 1 is the right: attacking down the page)
    static readonly Dictionary<string, (int Row, int Col)> RoleCell = new()
    {
        ["GK"] = (1, 2), ["RB"] = (2, 1), ["CB"] = (2, 2), ["LB"] = (2, 3), ["RWB"] = (3, 1), ["DM"] = (3, 2), ["LWB"] = (3, 3),
        ["RM"] = (4, 1), ["CM"] = (4, 2), ["LM"] = (4, 3), ["RW"] = (5, 1), ["AM"] = (5, 2), ["LW"] = (5, 3), ["ST"] = (6, 2),
    };
    // A player's main position -> the roles he fits, nearest first (the first the shape has is his)
    static readonly Dictionary<string, string[]> PosFit = new()
    {
        ["GK"] = ["GK"], ["CB"] = ["CB", "DM"], ["RB"] = ["RB", "RWB", "RM", "CB"], ["LB"] = ["LB", "LWB", "LM", "CB"],
        ["RWB"] = ["RWB", "RB", "RM", "RW"], ["LWB"] = ["LWB", "LB", "LM", "LW"], ["DM"] = ["DM", "CM", "CB"], ["CM"] = ["CM", "DM", "AM"],
        ["AM"] = ["AM", "CM", "ST", "RW", "LW"], ["RM"] = ["RM", "RW", "RWB", "AM", "CM"], ["LM"] = ["LM", "LW", "LWB", "AM", "CM"],
        ["RW"] = ["RW", "RM", "AM", "ST"], ["LW"] = ["LW", "LM", "AM", "ST"], ["ST"] = ["ST", "AM"],
    };

    const int XiRecent = 6;      // his latest team sheets weighed
    const double XiDecay = 0.75; // each older sheet counts this much of the one after it
    static readonly Dictionary<string, string[]> RoleNear = new()
    {
        ["GK"] = [], ["CB"] = [], ["RB"] = ["RWB"], ["LB"] = ["LWB"], ["RWB"] = ["RB", "RM"], ["LWB"] = ["LB", "LM"], ["DM"] = ["CM"],
        ["CM"] = ["DM", "AM"], ["AM"] = ["CM", "ST"], ["RM"] = ["RW", "RWB"], ["LM"] = ["LW", "LWB"], ["RW"] = ["RM", "ST"], ["LW"] = ["LM", "ST"], ["ST"] = ["AM"],
    };

    // The team's usual shape: its most used formation in the current coach's last 5 team sheets
    // (ties: the latest), as {role: count} from his latest XI in it. Null without full team sheets
    public sealed record Shape(Spell Spell, List<NatMatch> Sheets, string? Formation, NatMatch Template, List<(string Role, int N)> Need);
    public static Shape? ShapeOf(Team team)
    {
        var spell = SpellOf(team);
        var full = spell.Rows.Where(m => m.Xi.Count >= 11 && m.Xi.All(a => !string.IsNullOrEmpty(a.Role))).ToList();
        var sheets = full.Skip(Math.Max(0, full.Count - XiRecent)).ToList();
        if (sheets.Count == 0) return null;
        var counts = new List<(string F, int N)>();
        foreach (var m in sheets.Skip(Math.Max(0, sheets.Count - 5)))
            if (!string.IsNullOrEmpty(m.Formation))
            {
                var k = counts.FindIndex(c => c.F == m.Formation);
                if (k < 0) counts.Add((m.Formation, 1)); else counts[k] = (m.Formation, counts[k].N + 1);
            }
        var latest = Enumerable.Reverse(sheets).ToList();
        var formation = counts.OrderByDescending(c => c.N).ThenBy(c => latest.FindIndex(m => m.Formation == c.F)).Select(c => c.F).FirstOrDefault();
        var template = (formation is null ? null : latest.FirstOrDefault(m => m.Formation == formation)) ?? latest[0];
        var need = new List<(string Role, int N)>();
        foreach (var a in template.Xi)
        {
            var k = need.FindIndex(x => x.Role == a.Role);
            if (k < 0) need.Add((a.Role!, 1)); else need[k] = (a.Role!, need[k].N + 1);
        }
        return new(spell, sheets, template.Formation, template, need);
    }

    // The predicted XI, from the current coach's recent team sheets (no model). His most used
    // formation in his last 5 matches, laid out as his latest XI in it; then each of its positions
    // goes to the player who has started there most, recent matches counting more (a start in a
    // neighbouring position counts half). Players their club lists as out injured are left out.
    public sealed record Pick(string Role, int Pid, int Starts);
    public sealed record Predicted(string? Formation, List<Pick> Picks, List<int> Out);
    public static Predicted? PredictedXi(Team team, IReadOnlySet<int> injured)
    {
        if (ShapeOf(team) is not { } shape) return null;
        var (sheets, template) = (shape.Sheets, shape.Template);
        var need = shape.Need.ToDictionary(x => x.Role, x => x.N);
        var score = new List<(string Role, int Pid, double V)>();
        var scoreAt = new Dictionary<(string, int), int>();
        var starts = new List<(int Pid, int N)>();
        var startAt = new Dictionary<int, int>();
        for (var k = 0; k < sheets.Count; k++)
        {
            var w = Math.Pow(XiDecay, sheets.Count - 1 - k);
            foreach (var a in sheets[k].Xi)
            {
                if (startAt.TryGetValue(a.Player, out var si)) starts[si] = (a.Player, starts[si].N + 1);
                else { startAt[a.Player] = starts.Count; starts.Add((a.Player, 1)); }
                foreach (var (role, f) in new[] { (a.Role!, 1.0) }.Concat((RoleNear.GetValueOrDefault(a.Role!) ?? []).Select(r => (r, 0.5))))
                {
                    if (scoreAt.TryGetValue((role, a.Player), out var at)) score[at] = (role, a.Player, score[at].V + f * w);
                    else { scoreAt[(role, a.Player)] = score.Count; score.Add((role, a.Player, f * w)); }
                }
            }
        }
        int StartsOf(int pid) => startAt.TryGetValue(pid, out var i) ? starts[i].N : 0;
        var picks = new List<Pick>();
        var placed = new HashSet<int>();
        var filled = new Dictionary<string, int>();
        foreach (var c in score.Where(c => need.ContainsKey(c.Role) && !injured.Contains(c.Pid))
                     .OrderByDescending(c => c.V).ThenByDescending(c => StartsOf(c.Pid)))
        {
            if (placed.Contains(c.Pid) || filled.GetValueOrDefault(c.Role) >= need[c.Role]) continue;
            placed.Add(c.Pid);
            filled[c.Role] = filled.GetValueOrDefault(c.Role) + 1;
            picks.Add(new(c.Role, c.Pid, StartsOf(c.Pid)));
        }
        return new(template.Formation, picks.OrderBy(p => Order(p.Role)).ToList(),
            // regulars (2+ starts in these sheets) missing through injury
            starts.Where(s => s.N >= 2 && injured.Contains(s.Pid)).Select(s => s.Pid).ToList());
    }

    // ---- Overview: the best by current rank in each position of the team's usual shape (3 per
    // player the shape has there: 6 for a pair of centre-backs), each player in the nearest of its
    // positions to his main one, plus everyone the current coach has picked. Without line-ups, the
    // top 3 in each of a fixed set of positions. `list`: the nationality's ranked players, in the
    // export's order (by current rank; a hidden rank keeps its place).
    public sealed record Shown(int Id, string Name, double? Rank, double? Ord, string? Position, int? Team, bool Listed);
    public sealed record BoxPlayer(Shown P, bool Unpicked);
    public sealed record Box(string Label, int Row, int Col, List<BoxPlayer> Players);
    public sealed record Overview(string? Formation, string? Coach, bool HasShape, List<Box> Boxes);

    static readonly (string Role, int Max, int Row, int Col)[] FixedLayout =
        [("GK", 3, 1, 2), ("RB", 3, 2, 1), ("CB", 3, 2, 2), ("LB", 3, 2, 3), ("DM", 3, 3, 2), ("CM", 3, 4, 2), ("RW", 3, 5, 1), ("AM", 3, 5, 2), ("LW", 3, 5, 3), ("ST", 3, 6, 2)];

    public static Overview OverviewPitch(List<Player> list, Team? team)
    {
        var shape = team?.Matches.Count > 0 ? ShapeOf(team) : null;
        var layout = shape is not null
            ? shape.Need.OrderBy(x => Array.IndexOf(RoleOrder, x.Role)).Select(x => (x.Role, Max: 3 * x.N, RoleCell[x.Role].Row, RoleCell[x.Role].Col)).ToArray()
            : FixedLayout;
        var roles = layout.Select(l => l.Role).ToHashSet();
        string? SlotOf(string? pos) => string.IsNullOrEmpty(pos) ? null : (PosFit.GetValueOrDefault(pos) ?? [pos]).FirstOrDefault(roles.Contains);
        static Shown Listed(Player p) => new(p.Id, p.Name, p.Rank, p.Ord, p.Position, p.Team, true);

        // everyone the current coach has picked (played for him, starting or from the bench): our
        // ranked players by their main position, the rest by the one they've started in most for him
        var picked = new Dictionary<int, Shown>();
        var pickedOrder = new List<int>();
        if (shape is not null && team is not null)
        {
            var inSpell = shape.Spell.Rows.Select(m => m.I).ToHashSet();
            var started = new Dictionary<int, List<(string Role, int N)>>();
            var ids = new List<int>();
            var seen = new HashSet<int>();
            foreach (var a in team.Apps)
            {
                if (!inSpell.Contains(a.Match)) continue;
                if (seen.Add(a.Player)) ids.Add(a.Player);
                if (a.Started != 0 && !string.IsNullOrEmpty(a.Role))
                {
                    if (!started.TryGetValue(a.Player, out var c)) started[a.Player] = c = [];
                    var k = c.FindIndex(x => x.Role == a.Role);
                    if (k < 0) c.Add((a.Role, 1)); else c[k] = (a.Role, c[k].N + 1);
                }
            }
            foreach (var pid in ids)
            {
                var p = list.FirstOrDefault(q => q.Id == pid);
                var role = started.GetValueOrDefault(pid)?.OrderByDescending(x => x.N).Select(x => x.Role).FirstOrDefault();
                picked[pid] = p is not null ? Listed(p) : new(pid, team.PlayerName(pid) ?? "Unknown", null, null, role, null, false);
                pickedOrder.Add(pid);
            }
        }
        static int ByOrd(Shown a, Shown b) => (a.Ord ?? 1e9).CompareTo(b.Ord ?? 1e9) is var c && c != 0 ? c : Js.Compare.Compare(a.Name, b.Name);
        return new(shape?.Formation, shape?.Spell.Coach, shape is not null, layout.Select(l =>
        {
            var top = list.Where(p => SlotOf(p.Position) == l.Role).Take(l.Max).ToList();
            var topIds = top.Select(p => p.Id).ToHashSet();
            var extra = pickedOrder.Select(id => picked[id]).Where(p => !string.IsNullOrEmpty(p.Position) && SlotOf(p.Position) == l.Role && !topIds.Contains(p.Id));
            // (a top player the coach hasn't picked is shown in red)
            var ps = top.Select(p => new BoxPlayer(Listed(p), shape is not null && !picked.ContainsKey(p.Id)))
                .Concat(extra.Select(p => new BoxPlayer(p, false))).ToList();
            var sorted = ps.Select((x, i) => (x, i)).OrderBy(t => t.x.P, Comparer<Shown>.Create(ByOrd)).ThenBy(t => t.i).Select(t => t.x).ToList();
            return new Box(l.Role, l.Row, l.Col, sorted);
        }).ToList());
    }

    // ---- Players: everyone who has played under the current coach
    public sealed record NatPlayer(int Id, string Name, int Apps, int Minutes, int NoMins, int Goals, int Assists, int Y, int R, int Cards, string Last, string Role);
    public static readonly string[] PlayerSorts = ["apps", "minutes", "goals", "assists", "cards", "last"];
    public static List<NatPlayer> Players(Team team, Spell spell, Func<int, string?> clubPosition, string sort)
    {
        var inWindow = spell.Rows.Select(m => m.I).ToHashSet();
        var order = new List<int>();
        var by = new Dictionary<int, (int Apps, int Minutes, int NoMins, int Goals, int Assists, int Y, int R, string Last, List<(string Role, int N)> Roles)>();
        foreach (var a in team.Apps)
        {
            if (!inWindow.Contains(a.Match)) continue;
            if (!by.TryGetValue(a.Player, out var p)) { order.Add(a.Player); p = (0, 0, 0, 0, 0, 0, 0, "", []); }
            var m = team.Matches[a.Match];
            p.Apps++;
            if (a.Minutes is { } mins) p.Minutes += mins; else p.NoMins++;
            p.Goals += a.Goals ?? 0; p.Assists += a.Assists ?? 0;
            p.Y += a.Yellow ?? 0; p.R += a.Red ?? 0;
            if (string.CompareOrdinal(m.Date, p.Last) > 0) p.Last = m.Date;
            if (!string.IsNullOrEmpty(a.Role))
            {
                var k = p.Roles.FindIndex(x => x.Role == a.Role);
                if (k < 0) p.Roles.Add((a.Role, 1)); else p.Roles[k] = (a.Role, p.Roles[k].N + 1);
            }
            by[a.Player] = p;
        }
        var players = order.Select(id =>
        {
            var p = by[id];
            var role = p.Roles.OrderByDescending(x => x.N).Select(x => x.Role).FirstOrDefault() is { Length: > 0 } r ? r : clubPosition(id) ?? "";
            return new NatPlayer(id, team.PlayerName(id) ?? "Unknown", p.Apps, p.Minutes, p.NoMins, p.Goals, p.Assists, p.Y, p.R, p.Y + 3 * p.R, p.Last, role);
        }).ToList();
        int Val(NatPlayer a, NatPlayer b) => sort switch
        {
            "apps" => b.Apps.CompareTo(a.Apps), "goals" => b.Goals.CompareTo(a.Goals), "assists" => b.Assists.CompareTo(a.Assists),
            "cards" => b.Cards.CompareTo(a.Cards), "last" => Math.Sign(string.CompareOrdinal(b.Last, a.Last)), _ => b.Minutes.CompareTo(a.Minutes),
        };
        return players.Select((p, i) => (p, i)).OrderBy(t => t.p, Comparer<NatPlayer>.Create((a, b) =>
            Val(a, b) is var v && v != 0 ? v : b.Apps != a.Apps ? b.Apps.CompareTo(a.Apps) : b.Minutes.CompareTo(a.Minutes))).ThenBy(t => t.i).Select(t => t.p).ToList();
    }

    // A nationality page's nation in the ranking (API-Football's name or the dataset's)
    public static NationsDoc.Nation? For(NationsDoc d, string nat) =>
        d.Nations.FirstOrDefault(x => x.Name == nat || (d.Aliases?.GetValueOrDefault(x.Name) ?? []).Contains(nat));
}
