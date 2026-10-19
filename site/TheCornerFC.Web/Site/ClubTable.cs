using System.Text;
using System.Text.RegularExpressions;
using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// The Clubs table's choices: the competition menu, the Exclude chips, the search and the rows
// they leave (web/src/lib/clubTable.ts).
public sealed record Country(string Name, IReadOnlyList<int> Leagues, string? Region);

public sealed record Chip(string Value, string Label, string Full, string Title, int? Count, bool Pressed, bool Group, bool HasActive);
public sealed record MenuNode(Chip? Chip, bool Sep = false, bool Region = false, bool Open = false, IReadOnlyList<MenuNode>? Children = null);
public sealed record FilterMenuModel(IReadOnlyList<MenuNode> Nodes, string Name, int? Count);

// `Domestic`: the menu has a domestic cups group; `Intl`: a national team competitions group
public sealed record MenuTitles(string All, Func<string, string> Country, Func<string, string> Region, string Euro, Func<string, string> Cup,
    string? Domestic = null, Func<string, string>? DomesticCup = null, string? Intl = null);

public static partial class ClubTable
{
    public static string CountryDisplay(string c) => c == "World" ? "International" : (c ?? "").Replace('-', ' ');

    // The countries with a tracked league that has ranked clubs: the big five first, then by name.
    public static List<Country> Countries(SiteDoc site, List<Club> all)
    {
        var present = all.Select(r => r.League.ToString()).ToHashSet();
        var byCountry = new Dictionary<string, List<int>>();
        foreach (var (id, c) in site.Competitions)
        {
            if (c.Type != "League" || c.Country == "World" || !present.Contains(id)) continue;
            var name = c.Country.Replace('-', ' ');
            if (!byCountry.TryGetValue(name, out var ids)) byCountry[name] = ids = [];
            ids.Add(int.Parse(id));
        }
        int Rank(string n) { var i = Names.CountryFirst.ToList().IndexOf(n); return i == -1 ? 99 : i; }
        return byCountry.Select(kv => new Country(kv.Key, kv.Value.Order().ToList(), Names.CountryFirst.Contains(kv.Key) ? null : Names.RegionOf(kv.Key)))
            .OrderBy(c => Rank(c.Name)).ThenBy(c => c.Name, Js.Compare).ToList();
    }

    // ---- The menu's choice, as it is written in the address: "all", a league's id ("39"),
    // "c:England", "r:Scandinavia", "e:all" / "e:2" (European cups), "k:all" / "k:45" (domestic cups)
    public static bool IsCupFilter(string f) => f.StartsWith("e:") || f.StartsWith("k:");
    static bool Digits(string s) => s.Length > 0 && s.All(char.IsAsciiDigit);

    public static bool KnownFilter(string? f, List<Country> countries)
    {
        if (string.IsNullOrEmpty(f)) return false;
        if (f == "all") return true;
        if (Digits(f)) return int.TryParse(f, out var id) && countries.Any(c => c.Leagues.Contains(id));
        if (f.Length < 2) return false;
        var rest = f[2..];
        if (f.StartsWith("c:")) return countries.Any(c => c.Name == rest);
        if (f.StartsWith("r:")) return Names.Regions.Contains(rest);
        var group = f.StartsWith("e:") ? Names.EuroCups : f.StartsWith("k:") ? Names.DomesticCups : null;
        return group is not null && (rest == "all" || (Digits(rest) && int.TryParse(rest, out var lid) && group.Contains(lid)));
    }

    // League ids for a choice: null = all (a cup filter picks clubs, not leagues)
    public static List<int>? FilterLeagues(string f, List<Country> countries)
    {
        if (f == "all" || IsCupFilter(f)) return null;
        if (f.StartsWith("c:")) return countries.FirstOrDefault(c => c.Name == f[2..])?.Leagues.ToList() ?? [];
        if (f.StartsWith("r:")) return countries.Where(c => c.Region == f[2..]).SelectMany(c => c.Leagues).ToList();
        return [int.Parse(f)];
    }

    // the clubs for a cup filter ("e:all" / "k:all" = every cup in the group)
    public static HashSet<int> CupTeams(string f, Dictionary<int, HashSet<int>> cups)
    {
        var group = f == "e:all" ? Names.EuroCups : f == "k:all" ? Names.DomesticCups : null;
        if (group is not null) return group.SelectMany(lid => cups.GetValueOrDefault(lid) ?? []).ToHashSet();
        return cups.GetValueOrDefault(int.Parse(f[2..])) ?? [];
    }

    // ---- Exclude: the big five countries and whole continents hidden from the table, on top of
    // the menu. Keys: a big-five country's name, or "r:" + a continent (Europe takes in the big five).
    public static bool IsExcludeKey(string k) => Names.CountryFirst.Contains(k) || (k.StartsWith("r:") && Names.Continents.Contains(k[2..]));

    public static bool IsExcluded(SiteDoc site, IReadOnlySet<string> ex, int lid)
    {
        if (ex.Count == 0) return false;
        var c = site.Comp(lid)?.Country?.Replace('-', ' ');
        if (string.IsNullOrEmpty(c) || c == "World") return false;
        return ex.Contains(c) || ex.Contains($"r:{Names.ContinentOf(c)}");
    }

    // ---- Search: every word typed must start a word of the club's text (its name, initials and
    // nicknames, its league and country and theirs)
    public static string FoldText(string? t)
    {
        var s = MarkRe().Replace((t ?? "").Normalize(NormalizationForm.FormD), "").ToLowerInvariant();
        return NotWordRe().Replace(s, " ").Trim();
    }
    static string Initials(string[] words) => words.Length >= 2 ? string.Concat(words.Select(w => w[0])) : "";
    static readonly Dictionary<string, string> FoldedAliases = Names.ClubAliases.ToDictionary(kv => FoldText(kv.Key), kv => kv.Value);

    public static string SearchText(SiteDoc site, Club r)
    {
        var name = FoldText(site.TeamName(r.Team));
        var parts = new List<string> { name, Initials(name.Split(' ')), FoldedAliases.GetValueOrDefault(name) ?? "" };
        if (UnitedRe().IsMatch(name)) parts.Add("utd");
        if (UtdRe().IsMatch(name)) parts.Add("united");
        var c = r.InLeague ? site.Comp(r.League) : null;
        if (c is not null)
        {
            var league = FoldText(c.Name);
            var country = CountryDisplay(c.Country);
            var label = Names.PrimaryComps.Concat(Names.TableComps).FirstOrDefault(x => x.Id == r.League.ToString())?.Label;
            parts.AddRange([league, Initials(league.Split(' ')), FoldText(Names.ShortNames.GetValueOrDefault(r.League)), FoldText(label),
                Names.LeagueAliases.GetValueOrDefault(r.League) ?? "", FoldText(country), Names.CountryAliases.GetValueOrDefault(c.Country) ?? "",
                (Names.FlagCodes.GetValueOrDefault(country) ?? "").Replace("gb-", "")]);
        }
        return " " + string.Join(' ', parts.Where(p => p.Length > 0)) + " ";
    }

    public sealed record Choices(string Filter, IReadOnlySet<string> Excluded, string Search, string Sort);

    // The table's rows, highest first on the chosen column, and whether they span several leagues
    // (then each row names its league, and the list sits in a box that scrolls).
    public static (List<Club> Rows, bool Wide) Rows(SiteDoc site, List<Club> all, List<Country> countries, Dictionary<int, HashSet<int>> cups, Choices ch)
    {
        var ids = FilterLeagues(ch.Filter, countries);
        var words = FoldText(ch.Search).Split(' ', StringSplitOptions.RemoveEmptyEntries);
        IEnumerable<Club> rows;
        if (words.Length > 0)
            rows = all.Where(r => { var text = SearchText(site, r); return words.All(w => text.Contains(" " + w)); });
        else
        {
            if (IsCupFilter(ch.Filter))
            {
                var teams = CupTeams(ch.Filter, cups);
                rows = all.Where(r => teams.Contains(r.Team));
            }
            else
            {
                // clubs playing in a tracked league this season
                var active = all.Where(r => r.InLeague);
                rows = ids is null ? active : active.Where(r => ids.Contains(r.League));
            }
            rows = rows.Where(r => !IsExcluded(site, ch.Excluded, r.League));
        }
        var sorted = rows.OrderByDescending(r => r.Value(ch.Sort) ?? -1e9).ToList();
        return (sorted, ids is null || ids.Count > 1);
    }

    public static readonly MenuTitles ClubTitles = new(
        "All leagues", c => $"All {c} clubs", r => $"All clubs in {r}",
        "Clubs in this season's Champions League, Europa League or Conference League",
        n => $"Clubs in the {n} league phase",
        "Clubs still in a domestic cup (clubs yet to enter aren't counted)",
        n => $"Clubs still in the {n} (clubs yet to enter aren't counted)");

    // how many clubs each choice shows, with the exclusions applied
    public static Func<string, int> Counts(SiteDoc site, List<Club> all, List<Country> countries, Dictionary<int, HashSet<int>> cups, IReadOnlySet<string> ex)
    {
        var counts = new Dictionary<int, int>();
        var total = 0;
        foreach (var r in all)
            if (r.InLeague && !IsExcluded(site, ex, r.League)) { counts[r.League] = counts.GetValueOrDefault(r.League) + 1; total++; }
        return value =>
        {
            if (value == "all") return total;
            if (IsCupFilter(value))
            {
                var teams = CupTeams(value, cups);
                return all.Count(r => teams.Contains(r.Team) && !IsExcluded(site, ex, r.League));
            }
            return (FilterLeagues(value, countries) ?? []).Sum(id => counts.GetValueOrDefault(id));
        };
    }

    // ---- The menu as the page draws it: All, the cups, the big five countries, then the rest by
    // region. A group opens on the choice inside it.
    public static FilterMenuModel Menu(SiteDoc site, List<Country> countries, string f, Func<string, int>? countOf, MenuTitles titles, IReadOnlyList<int>? intl = null)
    {
        intl ??= [];
        var names = new Dictionary<string, string>();
        Chip MakeChip(string value, string label, string title, bool group = false, bool hasActive = false, string? full = null)
        {
            names[value] = full ?? label;
            return new(value, label, full ?? label, title, countOf?.Invoke(value), f == value, group, hasActive);
        }
        var fLeague = Digits(f) && int.TryParse(f, out var fl) ? fl : (int?)null;
        var activeCountry = f.StartsWith("c:") ? countries.FirstOrDefault(c => c.Name == f[2..]) : countries.FirstOrDefault(c => fLeague is { } l && c.Leagues.Contains(l));
        var activeRegion = f.StartsWith("r:") ? f[2..] : activeCountry?.Region;

        // A country: one league = a plain chip; several = a chip that opens its leagues
        MenuNode CountryNode(Country c)
        {
            if (c.Leagues.Count == 1) return new(MakeChip(c.Leagues[0].ToString(), c.Name, $"{c.Name} · {site.LeagueName(c.Leagues[0])}"));
            var chip = MakeChip($"c:{c.Name}", c.Name, titles.Country(c.Name), group: true, hasActive: fLeague is { } l && c.Leagues.Contains(l));
            return new(chip, Open: activeCountry == c,
                Children: c.Leagues.Select(id => new MenuNode(MakeChip(id.ToString(), site.LeagueName(id), site.LeagueName(id), full: $"{c.Name} · {site.LeagueName(id)}"))).ToList());
        }
        MenuNode CupNode(char key, string label, string title, IReadOnlyList<int> ids, Func<string, string> each) =>
            new(MakeChip($"{key}:all", label, title, group: true, hasActive: f.StartsWith($"{key}:") && f != $"{key}:all"),
                Open: f.StartsWith($"{key}:"),
                Children: ids.Select(lid => new MenuNode(MakeChip($"{key}:{lid}", site.LeagueName(lid), each(site.LeagueName(lid))))).ToList());

        var nodes = new List<MenuNode> { new(MakeChip("all", "All", titles.All)), CupNode('e', "European cups", titles.Euro, Names.EuroCups, titles.Cup) };
        if (titles.Intl is not null && intl.Count > 0) nodes.Add(CupNode('i', "Internationals", titles.Intl, intl, titles.Cup));
        if (titles.Domestic is not null) nodes.Add(CupNode('k', "Domestic cups", titles.Domestic, Names.DomesticCups, titles.DomesticCup!));
        nodes.Add(new(null, Sep: true));
        nodes.AddRange(countries.Where(c => c.Region is null).Select(CountryNode));
        nodes.Add(new(null, Sep: true));
        foreach (var region in Names.Regions)
        {
            var members = countries.Where(c => c.Region == region).ToList();
            if (members.Count == 0) continue;
            var chip = MakeChip($"r:{region}", Names.RegionLabel(region), titles.Region(region), group: true, hasActive: activeRegion == region && f != $"r:{region}");
            nodes.Add(new(chip, Region: true, Open: activeRegion == region, Children: members.Select(CountryNode).ToList()));
        }
        return new(nodes, names.GetValueOrDefault(f) ?? "All", countOf?.Invoke(f));
    }

    [GeneratedRegex("[̀-ͯ]")] private static partial Regex MarkRe();
    [GeneratedRegex("[^a-z0-9]+")] private static partial Regex NotWordRe();
    [GeneratedRegex(@"\bunited\b")] private static partial Regex UnitedRe();
    [GeneratedRegex(@"\butd\b")] private static partial Regex UtdRe();
}
