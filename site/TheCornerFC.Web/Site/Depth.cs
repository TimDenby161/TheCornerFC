using System.Text.Json;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// A club's squad by position for its next match: who can play where, each player's chance of
// starting there and the minutes he is expected to play (web/src/lib/depth.ts, ported line for
// line so both sites give the same figures). Worked out from the club's own file (who started
// where this season, minutes over 12 months), its players' ranks and its injury list.
//
// Where depth.ts does sums with a rank that may be missing, JavaScript counts the missing rank as
// 0; R() does the same here.
public static class Depth
{
    public sealed record SquadPlayer(int Id, string Name, string? Position, double? Rank,
        IReadOnlyDictionary<string, double>? PositionRanks, IReadOnlyList<string>? Positions12m);

    public sealed record Input(
        List<SquadPlayer> Squad,              // everyone listed at the club
        HashSet<int> Out,                     // injured or suspended: left off the pitch
        Starts? Starts,
        Dictionary<string, JsonElement[][]>? Positions,   // each player's starting minutes by role over 12 months
        List<string?> SeasonFormations,       // this season's matches' formations
        string? NextGroup,                    // the next match's kind of competition ("league", "europe", "cup")
        Func<int, string> GroupOf);

    public sealed record Ps(SquadPlayer P, double? Rank);
    public sealed record Proj(Dictionary<int, double> Share, bool Changed);
    public sealed class Box(string label, string[] roles, string row, int col)
    {
        public string Label { get; } = label;
        public string[] Roles { get; } = roles;
        public string Row { get; } = row;
        public int Col { get; } = col;
        public int N { get; set; }
        public int Exact { get; set; }
        public List<Ps> Ps { get; set; } = [];
        public Proj? Proj { get; set; }
    }

    public sealed record Result(List<Box> Shown, Dictionary<string, double> StartChance, Dictionary<string, double> XMins,
        Dictionary<string, double> BoxMins, Dictionary<string, List<int>> Picks,
        Func<SquadPlayer, string[], int?> StartPct, Func<SquadPlayer, double> Lasts, Func<SquadPlayer, double> BenchRate);

    // a full-back with no wing-back rank is shown there on his full-back one, and the other way round
    public static readonly IReadOnlyDictionary<string, string> NearGroup = new Dictionary<string, string> { ["FB"] = "WB", ["WB"] = "FB" };
    const double DepthMinutes = 180;
    const double AbilityPull = 0.2;
    // a squad player with no box goes in the nearest one the club uses
    static readonly Dictionary<string, string[]> Near = new()
    {
        ["LWB"] = ["LB", "LM", "CB"], ["RWB"] = ["RB", "RM", "CB"], ["LB"] = ["LWB", "CB"], ["RB"] = ["RWB", "CB"],
        ["LW"] = ["LM", "AM", "ST"], ["RW"] = ["RM", "AM", "ST"], ["LM"] = ["LW", "CM", "AM"], ["RM"] = ["RW", "CM", "AM"],
        ["AM"] = ["CM", "LW", "RW", "ST"], ["DM"] = ["CM", "CB"], ["CM"] = ["CM", "AM"], ["ST"] = ["AM", "LW", "RW"], ["CB"] = ["LB", "RB", "CM"],
    };
    static readonly Dictionary<string, string> Partner = new()
    {
        ["LM"] = "LW", ["LW"] = "LM", ["RM"] = "RW", ["RW"] = "RM", ["LWB"] = "LB", ["LB"] = "LWB", ["RWB"] = "RB", ["RB"] = "RWB", ["AM"] = "CM", ["CM"] = "AM", ["ST"] = "AM",
    };

    static double R(double? v) => v ?? 0;
    static string? Group(string? r) => r is null ? null : Names.GroupOf.GetValueOrDefault(r);
    // a stable sort, as the browser's is
    static List<T> Sorted<T>(IEnumerable<T> items, Comparison<T> cmp) =>
        items.Select((x, i) => (x, i)).OrderBy(t => t, Comparer<(T x, int i)>.Create((a, b) => cmp(a.x, b.x) is var c and not 0 ? c : a.i.CompareTo(b.i))).Select(t => t.x).ToList();
    static int Desc(double a, double b) => b.CompareTo(a);

    // a line-up as [player, role, player, role ...]
    sealed record XiMatch((int Player, string Role)[] Pairs);
    static XiMatch ToXi(JsonElement[] row)
    {
        var pairs = new List<(int, string)>();
        for (var i = 0; i + 1 < row.Length; i += 2)
            pairs.Add((row[i].ValueKind == JsonValueKind.Number ? row[i].GetInt32() : -1, row[i + 1].ValueKind == JsonValueKind.String ? row[i + 1].GetString()! : ""));
        return new(pairs.ToArray());
    }

    public static Result? Of(Input input)
    {
        var o = input.Out;
        var st = input.Starts;
        var positions = input.Positions;
        var atClub = input.Squad.Select(p => p.Id).ToHashSet();
        var squad = input.Squad.Where(p => !o.Contains(p.Id)).ToList();
        if (squad.Count == 0) return null;
        double? RankAt(SquadPlayer p, string r)
        {
            var g = Group(r)!;
            if (p.PositionRanks?.TryGetValue(g, out var a) == true) return a;
            if (NearGroup.TryGetValue(g, out var near) && p.PositionRanks?.TryGetValue(near, out var b) == true) return b;
            return Group(p.Position) == g ? p.Rank : null;
        }
        // who can play where: his main position, or 2+ full matches' worth of starting minutes there
        // over the last 12 months (until those are known, the 25% rule of the position filter)
        HashSet<string?> CanPlay(SquadPlayer p)
        {
            if (positions?.TryGetValue(p.Id.ToString(), out var rows) != true)
                return [p.Position, .. (p.Positions12m ?? [])];
            return [p.Position, .. rows!.Where(x => x[0].GetString() != "SUB" && x[1].GetDouble() >= DepthMinutes).Select(x => x[0].GetString())];
        }
        // only the positions in the formations the club has used (all of them if none are known); a
        // formation used only once this season is left out, unless none has been used more than once
        var formationCount = new Dictionary<string, int>();
        foreach (var f in input.SeasonFormations) if (!string.IsNullOrEmpty(f)) formationCount[f] = formationCount.GetValueOrDefault(f) + 1;
        var oneOff = formationCount.Values.Any(n => n > 1) ? formationCount.Where(kv => kv.Value == 1).Select(kv => kv.Key).ToHashSet() : [];
        var used = formationCount.Keys.Where(f => !oneOff.Contains(f)).SelectMany(ClubPage.FormationRoles).ToHashSet();
        // one box per position; DM and CM share one central-midfield box over both lines
        var boxes = Names.PitchSpots.Where(s => s.Role is not "DM" and not "CM").Select(s =>
            new Box(s.Role, [s.Role], (s.Y < 20 ? 6 : s.Y < 35 ? 5 : s.Y < 50 ? 4 : s.Y < 65 ? 3 : s.Y < 80 ? 2 : 1).ToString(), s.X < 35 ? 3 : s.X < 65 ? 2 : 1)).ToList();
        boxes.Add(new Box("CM", ["DM", "CM"], "3 / span 2", 2));
        // his share of the club's matches this season (with a line-up) that he started in this box
        int? StartPct(SquadPlayer p, string[] roles)
        {
            var byRole = st?.Players?.GetValueOrDefault(p.Id.ToString());
            var n = roles.Sum(r => byRole?.GetValueOrDefault(r) ?? 0);
            return st?.Games is > 0 && n > 0 ? Js.RoundInt(100.0 * n / st.Games.Value) : null;
        }
        double UsualExact(string[] roles) => st?.Games is > 0
            ? (st.Players ?? []).Values.Sum(byRole => roles.Sum(r => byRole.GetValueOrDefault(r))) / (double)st.Games.Value : 0;
        var xiFormation = st?.XiFormation ?? [];
        bool Keep(int k) => !oneOff.Contains(k < xiFormation.Length ? xiFormation[k] ?? "" : "\0");
        var allXi = (st?.Xi ?? []).Select(ToXi).ToList();
        var xi = allXi.Where((_, k) => Keep(k)).ToList();
        var xiLeague = (st?.XiLeague ?? []).Where((_, k) => Keep(k)).ToList();
        var seasonXi = xi;
        // (a line-up with no competition counts as a cup's, as an unknown competition does)
        var groupXi = input.NextGroup is not null ? xi.Where((_, k) => input.GroupOf(k < xiLeague.Count ? xiLeague[k] : 0) == input.NextGroup).ToList() : [];
        var wGroup = groupXi.Count / (groupXi.Count + 1.0);
        double? PerMatch(List<XiMatch> matches, string[] roles) =>
            matches.Count > 0 ? matches.Sum(m => m.Pairs.Count(x => roles.Contains(x.Role))) / (double)matches.Count : null;
        double ExactFor(string[] roles)
        {
            var all = PerMatch(xi, roles) ?? UsualExact(roles);
            return groupXi.Count > 0 ? wGroup * PerMatch(groupXi, roles)!.Value + (1 - wGroup) * all : all;
        }
        double ShareIn(List<XiMatch> matches, SquadPlayer p, string[] roles) =>
            matches.Count == 0 ? 0 : 100.0 * matches.Sum(m => m.Pairs.Count(x => x.Player == p.Id && roles.Contains(x.Role))) / matches.Count;

        // The share each available player is expected to start in a box: his own starts there this
        // season, plus a cut of the starts of players now injured or gone. That missing share goes
        // to the players who have started there since the last of them did, then to the others by
        // rank (each 3 points lower halves it), each start there this season adding one more share;
        // nobody over 100%. Only players who really play there take it.
        Proj ProjectedIn(string[] roles, int n, List<Ps> ps, List<XiMatch> xiIn)
        {
            var actual = ps.Select(d => (d.P.Id, ShareIn(xiIn, d.P, roles))).ToList();
            var share = new Dictionary<int, double>();
            foreach (var (id, v) in actual) share[id] = v;
            var left = n * 100 - actual.Sum(a => a.Item2);
            if (left <= 0.5) return new(share, false);
            var last = -1;
            for (var k = 0; k < xiIn.Count; k++)
                foreach (var (pl, role) in xiIn[k].Pairs)
                    if (roles.Contains(role) && (o.Contains(pl) || !atClub.Contains(pl))) last = k;
            if (last < 0) return new(share, false); // short only because the formation varies
            int StartsIn(int id, bool inBox, List<XiMatch>? matches = null) =>
                (matches ?? xiIn).Sum(m => m.Pairs.Count(x => x.Player == id && roles.Contains(x.Role) == inBox));
            var season = seasonXi; // a start there in any competition counts
            var regular = ps.Where(d => roles.Any(x => CanPlay(d.P).Contains(x))
                || (StartsIn(d.P.Id, true, season) > 0 && StartsIn(d.P.Id, false, season) <= season.Count / 2.0)).ToList();
            var pool = regular.Count > 0 ? regular : ps;
            double Room(int id) => 100 - share[id];
            void Hand(List<(int Id, double W)> weights)
            {
                var wsum = weights.Sum(x => x.W);
                if (left <= 0.5 || wsum == 0) return;
                var give = left;
                foreach (var (id, w) in weights)
                {
                    var g = Math.Min(Room(id), give * w / wsum);
                    share[id] = share[id] + g;
                    left -= g;
                }
            }
            var since = new Dictionary<int, int>();
            foreach (var m in xiIn.Skip(last + 1))
                foreach (var (pl, role) in m.Pairs)
                    if (roles.Contains(role)) since[pl] = since.GetValueOrDefault(pl) + 1;
            Hand(pool.Select(d => (d.P.Id, (double)since.GetValueOrDefault(d.P.Id))).ToList());
            var top = pool.Max(d => R(d.Rank));
            Hand(pool.Select(d => (d.P.Id, Math.Pow(2, (R(d.Rank) - top) / 3) * (1 + StartsIn(d.P.Id, true)))).ToList());
            foreach (var d in pool)
            {
                if (left <= 0.5) break;
                var g = Math.Min(Room(d.P.Id), left);
                share[d.P.Id] = share[d.P.Id] + g;
                left -= g;
            }
            return new(share, true);
        }
        // for the next match's kind of competition: this season's matches of that kind, blended with
        // all its matches in proportion k : 1 (k = matches of that kind)
        Proj Projected(string[] roles, int n, List<Ps> ps)
        {
            var all = ProjectedIn(roles, n, ps, xi);
            if (groupXi.Count == 0) return all;
            var grp = ProjectedIn(roles, n, ps, groupXi);
            var share = new Dictionary<int, double>();
            foreach (var d in ps) share[d.P.Id] = wGroup * grp.Share.GetValueOrDefault(d.P.Id) + (1 - wGroup) * all.Share.GetValueOrDefault(d.P.Id);
            return new(share, all.Changed || grp.Changed);
        }
        var visible = boxes.Where(b => used.Count == 0 || b.Roles.Any(used.Contains)).ToList();
        // who can play in a box, and anyone who has started there this season
        bool Fits(SquadPlayer p, Box b) => b.Roles.Any(x => CanPlay(p).Contains(x)) || StartPct(p, b.Roles) is not null and not 0;
        var labels = visible.Select(b => b.Label).ToHashSet();
        var fallback = new Dictionary<int, string?>();
        foreach (var p in squad.Where(p => !visible.Any(b => Fits(p, b))))
            fallback[p.Id] = (p.Position is not null && Near.TryGetValue(p.Position, out var near) ? near : []).FirstOrDefault(labels.Contains) ?? (labels.Contains("CM") ? "CM" : null);
        // Starters per box: its starters per match rounded to whole players that make an XI, the
        // largest fractions taking the places left after rounding down
        var exactOf = visible.Select(b => (b.Label, X: ExactFor(b.Roles))).ToList();
        var starters = exactOf.ToDictionary(e => e.Label, e => (int)Math.Floor(e.X));
        var places = exactOf.Any(e => e.X > 0) ? 11 - starters.Values.Sum() : 0;
        foreach (var (l, x) in Sorted(exactOf, (a, b) => Desc(a.X % 1, b.X % 1)))
        {
            if (places <= 0 || x % 1 == 0) break;
            starters[l] = starters[l] + 1;
            places--;
        }
        var shown = visible.Select(b =>
        {
            var n = starters[b.Label];
            var ps = Sorted(squad.Where(p => Fits(p, b) || (fallback.TryGetValue(p.Id, out var fb) && fb == b.Label))
                    .Select(p => new Ps(p, b.Roles.Max(x => RankAt(p, x) ?? -1)))
                    .Select(d => d with { Rank = d.Rank >= 0 ? d.Rank : d.P.Rank }), (x, y) => Desc(R(x.Rank), R(y.Rank)));
            b.N = n;
            b.Exact = n;
            b.Ps = ps;
            b.Proj = ps.Count > 0 ? Projected(b.Roles, n, ps) : null;
            return b;
        }).ToList();
        // The best XI by rating: the usual number of starters in each box, filled from the highest
        // player-and-position ranks down, one position per player. A pick only counts if he's rated
        // above one of the box's usual starters or is one himself. The expected share is
        // AbilityPull of that and the rest history.
        var picks = new Dictionary<string, List<int>>();
        var placed = new HashSet<int>();
        var filled = new Dictionary<string, int>();
        double HistOf(Box b, int id) => b.Proj?.Share.GetValueOrDefault(id) ?? 0;
        foreach (var (b, d, _) in Sorted(shown.SelectMany(b => b.N > 0 ? b.Ps.Select(d => (B: b, D: d, H: HistOf(b, d.P.Id))) : []),
                     (x, y) => Desc(R(x.D.Rank), R(y.D.Rank)) is var c and not 0 ? c : Desc(x.H, y.H)))
        {
            if (placed.Contains(d.P.Id) || filled.GetValueOrDefault(b.Label) >= b.N) continue;
            placed.Add(d.P.Id);
            filled[b.Label] = filled.GetValueOrDefault(b.Label) + 1;
            if (!picks.ContainsKey(b.Label)) picks[b.Label] = [];
            picks[b.Label].Add(d.P.Id);
        }
        var ability = new Dictionary<string, Dictionary<int, double>>();
        foreach (var b in shown)
        {
            if (b.N == 0 || b.Ps.Count == 0) continue;
            var usual = Sorted(b.Ps, (x, y) => Desc(HistOf(b, x.P.Id), HistOf(b, y.P.Id))).Take(b.N).ToList();
            var worst = usual.Min(d => R(d.Rank));
            var rankOf = new Dictionary<int, double>();
            foreach (var d in b.Ps) rankOf[d.P.Id] = R(d.Rank);
            var count = (picks.GetValueOrDefault(b.Label) ?? []).Where(id => usual.Any(d => d.P.Id == id) || rankOf[id] > worst).ToList();
            var rest = b.Ps.Where(d => !count.Contains(d.P.Id)).ToList();
            var restHist = rest.Sum(d => HistOf(b, d.P.Id));
            double leftAb = Math.Max(0, b.N - count.Count) * 100;
            var ab = new Dictionary<int, double>();
            foreach (var d in b.Ps) ab[d.P.Id] = count.Contains(d.P.Id) ? 100 : restHist != 0 ? leftAb * HistOf(b, d.P.Id) / restHist : 0;
            ability[b.Label] = ab;
        }
        // Start chance per player and box: history with the pull towards the best XI
        var startChance = new Dictionary<string, double>(); // "box:player" -> %
        foreach (var b in shown)
        {
            var ab = ability.GetValueOrDefault(b.Label);
            foreach (var d in b.Ps)
            {
                var hist = b.Proj?.Share.GetValueOrDefault(d.P.Id) ?? 0;
                startChance[$"{b.Label}:{d.P.Id}"] = ab is not null ? (1 - AbilityPull) * hist + AbilityPull * Math.Min(100, ab.GetValueOrDefault(d.P.Id)) : hist;
            }
        }
        double Sc(string k) => startChance.GetValueOrDefault(k);
        // A player starts in one position at most: his chances across boxes can't pass 100%. Over
        // it, he keeps his likeliest positions and gives up the rest; each box then tops its starts
        // back up from its other players with room, by their chance there (or their rank if nobody
        // has one)
        double TotalChance(int id) => shown.Sum(b => Sc($"{b.Label}:{id}"));
        List<int> Everyone()
        {
            var seen = new List<int>();
            foreach (var b in shown) foreach (var d in b.Ps) if (!seen.Contains(d.P.Id)) seen.Add(d.P.Id);
            return seen;
        }
        foreach (var id in Everyone())
        {
            double cap = 100;
            foreach (var b in Sorted(shown, (x, y) => Desc(Sc($"{x.Label}:{id}"), Sc($"{y.Label}:{id}"))))
            {
                var k = $"{b.Label}:{id}";
                if (!startChance.ContainsKey(k)) continue;
                var v = Math.Min(startChance[k], cap);
                startChance[k] = v;
                cap -= v;
            }
        }
        foreach (var b in shown)
        {
            var left = b.Exact * 100 - b.Ps.Sum(d => startChance[$"{b.Label}:{d.P.Id}"]);
            if (left < -0.5) // over its starters: scale the box down to them
            {
                var k = b.Exact * 100 / (b.Exact * 100 - left);
                foreach (var d in b.Ps) startChance[$"{b.Label}:{d.P.Id}"] = startChance[$"{b.Label}:{d.P.Id}"] * k;
                left = 0;
            }
            foreach (var pass in new[] { "chance", "rank" })
            {
                if (left <= 0.5) break;
                var w = b.Ps.Select(d => (d.P.Id, V: pass == "chance" ? startChance[$"{b.Label}:{d.P.Id}"] : R(d.Rank))).Where(x => x.V > 0).ToList();
                var wsum = w.Sum(x => x.V);
                var give = left;
                foreach (var (id, v) in w)
                {
                    var k = $"{b.Label}:{id}";
                    var g = Math.Min(Math.Min(give * v / wsum, 100 - TotalChance(id)), 100 - startChance[k]);
                    if (g > 0) { startChance[k] = startChance[k] + g; left -= g; }
                }
            }
        }
        // Expected minutes in each box: as a starter, his start chance x how long he usually lasts
        // when he starts; off the bench, the minutes the box's starters are expected to leave shared
        // among the squad players whose main position is there, by their minutes per match off the
        // bench; nobody over 90 in all
        var mins = st?.Mins ?? [];
        var minsMatches = st?.MinsMatches ?? 0;
        double Lasts(SquadPlayer p)
        {
            var row = mins.GetValueOrDefault(p.Id.ToString()) ?? [];
            double n = row.Length > 0 ? row[0] : 0, m = row.Length > 1 ? row[1] : 0, typical = Group(p.Position) == "GK" ? 90 : 80;
            return (m + 3 * typical) / (n + 3);
        }
        double BenchRate(SquadPlayer p)
        {
            var row = mins.GetValueOrDefault(p.Id.ToString()) ?? [];
            return minsMatches != 0 ? (row.Length > 3 ? row[3] : 0) / minsMatches : 0;
        }
        string? MainBox(SquadPlayer p) => shown.FirstOrDefault(b => p.Position is not null && b.Roles.Contains(p.Position))?.Label;
        var xMins = new Dictionary<string, double>();
        var boxMins = new Dictionary<string, double>();
        foreach (var b in shown)
        {
            var r = b.Label;
            double starting = 0;
            foreach (var d in b.Ps)
            {
                var m = startChance[$"{r}:{d.P.Id}"] / 100 * Lasts(d.P);
                xMins[$"{r}:{d.P.Id}"] = m;
                starting += m;
            }
            var demand = Math.Max(0, b.Exact * 90 - starting);
            double NotStarting(Ps d) => Math.Max(0, 100 - TotalChance(d.P.Id)) / 100;
            double SubW(Ps d) => BenchRate(d.P) * NotStarting(d);
            var bench = b.Ps.Where(d => MainBox(d.P) == r && SubW(d) > 0).ToList();
            if (bench.Count == 0) bench = b.Ps.Where(d => SubW(d) > 0).ToList();
            Func<Ps, double> weight = bench.Count > 0 ? SubW : NotStarting;
            if (bench.Count == 0) bench = b.Ps;
            var wsum = bench.Sum(weight);
            if (wsum != 0) foreach (var d in bench) xMins[$"{r}:{d.P.Id}"] = xMins[$"{r}:{d.P.Id}"] + demand * weight(d) / wsum;
        }
        foreach (var id in Everyone())
        {
            var keys = shown.Select(b => $"{b.Label}:{id}").Where(xMins.ContainsKey).ToList();
            var over = keys.Sum(k => xMins[k]) - 90;
            foreach (var k in Sorted(keys, (x, y) => xMins[x].CompareTo(xMins[y])))
            {
                if (over <= 0) break;
                var cut = Math.Min(over, xMins[k]);
                xMins[k] = xMins[k] - cut;
                over -= cut;
            }
        }
        double PlayerMins(int id) => shown.Sum(b => xMins.GetValueOrDefault($"{b.Label}:{id}"));
        double TopUp(double need, string into) // give `need` minutes to box `into`'s players
        {
            var b = shown.FirstOrDefault(x => x.Label == into);
            if (b is null) return need;
            for (var pass = 0; pass < 2; pass++)
            {
                var w = b.Ps.Select(d => (d.P.Id, Rank: R(d.Rank), Room: 90 - PlayerMins(d.P.Id))).Where(x => x.Room > 0.01).ToList();
                var wsum = w.Sum(x => x.Rank);
                if (wsum == 0 || need <= 0.01) break;
                var give = need;
                foreach (var (id, r, room) in w)
                {
                    var g = Math.Min(room, give * r / wsum);
                    xMins[$"{into}:{id}"] = xMins.GetValueOrDefault($"{into}:{id}") + g;
                    need -= g;
                }
            }
            return need;
        }
        foreach (var b in shown)
        {
            var shortfall = b.Exact * 90 - b.Ps.Sum(d => xMins.GetValueOrDefault($"{b.Label}:{d.P.Id}"));
            if (shortfall > 0.01)
            {
                var rest = TopUp(shortfall, b.Label);
                if (rest > 0.01 && Partner.TryGetValue(b.Label, out var partner)) TopUp(rest, partner);
            }
        }
        foreach (var b in shown)
        {
            var r = b.Label;
            // whole minutes that add up to the box's total (largest remainders get the spare minutes)
            var raw = b.Ps.Select(d => (d.P.Id, V: Math.Min(90, xMins.GetValueOrDefault($"{r}:{d.P.Id}")))).ToList();
            var total = Js.Round(raw.Sum(x => x.V));
            var whole = new Dictionary<int, double>();
            foreach (var (id, v) in raw) whole[id] = Math.Floor(v);
            var spare = total - whole.Values.Sum();
            foreach (var (id, _) in Sorted(raw, (x, y) => Desc(x.V % 1, y.V % 1)))
            {
                if (spare <= 0) break;
                whole[id] = whole[id] + 1;
                spare--;
            }
            foreach (var (id, v) in whole) xMins[$"{r}:{id}"] = v;
            boxMins[r] = total;
        }
        return new(shown, startChance, xMins, boxMins, picks, StartPct, Lasts, BenchRate);
    }

    // The predicted XI from the start chances: each position's usual number of starters, one
    // position per player, filled from the surest picks down
    public sealed record XiPick(Box Box, SquadPlayer P, double? Rank, double Chance, double Mins);
    public static List<XiPick>? PredictedXi(Result? d)
    {
        if (d is null) return null;
        var filled = new Dictionary<string, int>();
        var placed = new HashSet<int>();
        var xi = new List<XiPick>();
        var candidates = d.Shown.SelectMany(b => b.N > 0 ? b.Ps.Select(x => (Box: b, x.P, x.Rank, Chance: d.StartChance.GetValueOrDefault($"{b.Label}:{x.P.Id}"))) : [])
            .Where(c => c.Chance > 0);
        foreach (var c in Sorted(candidates, (x, y) => Desc(x.Chance, y.Chance) is var k and not 0 ? k : Desc(R(x.Rank), R(y.Rank))))
        {
            if (placed.Contains(c.P.Id) || filled.GetValueOrDefault(c.Box.Label) >= c.Box.N) continue;
            placed.Add(c.P.Id);
            filled[c.Box.Label] = filled.GetValueOrDefault(c.Box.Label) + 1;
            xi.Add(new(c.Box, c.P, c.Rank, c.Chance, d.XMins.GetValueOrDefault($"{c.Box.Label}:{c.P.Id}")));
        }
        return xi.Count > 0 ? xi : null;
    }

    // The expected squad's strength: the minutes-weighted average position rank of everyone
    // expected to play (bench minutes too); attack and defence weight each position by how much
    // it attacks or defends
    static readonly Dictionary<string, (double A, double D)> SquadWeights = new()
    {
        ["GK"] = (0, 1), ["CB"] = (0.1, 1), ["LB"] = (0.3, 0.8), ["RB"] = (0.3, 0.8), ["LWB"] = (0.4, 0.6), ["RWB"] = (0.4, 0.6),
        ["CM"] = (0.5, 0.6), ["LM"] = (0.8, 0.3), ["RM"] = (0.8, 0.3), ["AM"] = (1, 0.2), ["LW"] = (1, 0.15), ["RW"] = (1, 0.15), ["ST"] = (1, 0.1),
    };
    public sealed record Strength(double Overall, double? Attack, double? Defence);
    public static Strength? SquadStrength(Result? d)
    {
        if (d is null) return null;
        double[] all = [0, 0], att = [0, 0], def = [0, 0];
        foreach (var b in d.Shown)
        {
            var (wa, wd) = SquadWeights.GetValueOrDefault(b.Label, (0.5, 0.5));
            foreach (var x in b.Ps)
            {
                var m = d.XMins.GetValueOrDefault($"{b.Label}:{x.P.Id}");
                var r = R(x.Rank);
                all[0] += r * m; all[1] += m;
                att[0] += r * m * wa; att[1] += m * wa;
                def[0] += r * m * wd; def[1] += m * wd;
            }
        }
        static double? Avg(double[] s) => s[1] != 0 ? s[0] / s[1] : null;
        return all[1] != 0 ? new(Avg(all)!.Value, Avg(att), Avg(def)) : null;
    }

    // Where the XI stands on its pitch: keeper at the top, attacking down, left-sided positions on
    // the right. Players on the same line that would sit too close are spread evenly around their
    // middle, 24% apart (less if that won't fit). A wide player whose line is only just off a
    // central one's is then moved out towards the touchline until he is 24% from him too. x and y
    // are % of the pitch.
    public static List<(T C, double X, double Y)> XiSpots<T>(List<T> xi, Func<T, string> label)
    {
        var spot = Names.PitchSpots.ToDictionary(s => s.Role, s => (s.X, s.Y));
        spot["LM"] = (18, 34);
        spot["RM"] = (82, 34);
        var lines = new List<(double Y, List<(T C, double X)> Ps)>();
        foreach (var c in xi)
        {
            var (x0, y0) = spot.TryGetValue(label(c), out var s) ? s : spot["CM"];
            double x = 100 - x0, y = Js.Round(100 - y0) + (y0 > 85 ? 1 : 0);
            var k = lines.FindIndex(l => l.Y == y);
            if (k < 0) lines.Add((y, [(c, x)])); else lines[k].Ps.Add((c, x));
        }
        var placed = lines.SelectMany(line =>
        {
            var ps = Sorted(line.Ps, (a, b) => a.X.CompareTo(b.X));
            var xs = ps.Select(q => q.X).ToList();
            var clash = xs.Where((v, i) => i > 0 && v - xs[i - 1] < 22).Any();
            var gap = Math.Min(24, 72.0 / Math.Max(1, ps.Count - 1));
            var width = gap * (ps.Count - 1);
            var from = Math.Min(Math.Max(xs.Sum() / xs.Count - width / 2, 14), 86 - width);
            return ps.Select((q, i) => (q.C, X: clash ? from + i * gap : q.X, line.Y));
        }).ToList();
        // lines under 10% apart are closer than a player's box is tall
        for (var i = 0; i < placed.Count; i++)
            for (var j = 0; j < placed.Count; j++)
            {
                var (p, q) = (placed[i], placed[j]);
                if (p.Y == q.Y || Math.Abs(p.Y - q.Y) >= 10 || Math.Abs(p.X - q.X) >= 22) continue;
                if (Math.Abs(p.X - 50) <= Math.Abs(q.X - 50)) continue; // the wider of the two is the one that moves
                placed[i] = (p.C, p.X > 50 ? Math.Min(86, q.X + 24) : Math.Max(14, q.X - 24), p.Y);
            }
        return placed;
    }
}
