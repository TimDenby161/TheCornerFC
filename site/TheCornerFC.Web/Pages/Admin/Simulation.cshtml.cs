using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using TheCornerFC.Web.Data;
using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Pages.AdminArea;

// A record of the paper selections as if each had been backed with the same paper stake
// (web/src/routes/(app)/admin/simulation). The administrator's only: the bets are one of their
// documents, not a public row.
public sealed class SimulationModel(Database db) : PageModel
{
    public sealed record Mark(string Text, string Cls);
    public sealed record Line(string Label, int? League, bool On, int Bets, int Pending, string Won, Mark? Profit, Mark? Roi);
    public sealed record Settled(int Id, string Kickoff, string Comp, string When, string? Result, string Match, string? Score, List<(int Id, string Name)> Teams,
        bool Intl, string Pick, string Odds, Mark Outcome, string Sub);

    static readonly MenuTitles Titles = new(
        "All competitions", c => $"All {c} bets", r => $"All bets in {r}",
        "Champions League, Europa League and Conference League bets", n => $"{n} bets", Intl: "Bets on national team matches");

    public Bets.Choices Ch { get; private set; } = new("all", "all", "all");
    public string Filter { get; private set; } = "all";
    public FilterMenuModel? Menu { get; private set; }
    public bool Any { get; private set; }
    public bool Empty { get; private set; }
    public string Stake { get; private set; } = "";
    public string Bank { get; private set; } = "";
    public int MinEdge { get; private set; }
    public double MaxOdds { get; private set; }
    public int Pending { get; private set; }
    public List<(string Label, string Value, string Note, string Extra)> Cards { get; private set; } = [];
    public List<Line> Leagues { get; private set; } = [];
    public List<Line> MarketLines { get; private set; } = [];
    public int SettledCount { get; private set; }
    public List<Settled> SettledBets { get; private set; } = [];

    public async Task<IActionResult> OnGet()
    {
        ViewData["TabHead"] = TabHead.For("Paper Simulation", "bets");
        var siteTask = db.KeptDoc<SiteDoc>("site");
        var docTask = TheCornerFC.Web.Site.Admin.Doc<BetsDoc>(db, Visitor.Of(HttpContext).Token, "bets");
        await Task.WhenAll(siteTask, docTask);
        if (docTask.Result.Refused) return NotFound();
        var site = siteTask.Result;
        var q = Request.Query;
        string Pick(string k, IEnumerable<string> ok, string def) => ok.Contains(q[k].ToString()) ? q[k].ToString() : def;
        Ch = new(Pick("s", ["all", "early", "late"], "all"), Pick("m", ["all", .. Bets.Markets], "all"), Pick("v", ["all", "cautious"], "all"));
        if (docTask.Result.Doc is not { } doc) return Page();
        Any = true;

        var stake = doc.Rules.StakeGbp ?? 10;
        var bank = doc.Rules.Bank ?? 1000;
        var countries = Matchday.CompCountries(site, doc.Bets.Select(b => b.League));
        var intl = doc.Bets.Where(b => b.IsIntl).Select(b => b.League).Distinct().Where(id => site.Comp(id)?.Type == "International").ToList();
        var c = q["c"].ToString();
        Filter = Matchday.KnownFilter(c, site, countries) ? c : "all";
        var scope = Bets.Scope(doc.Bets, Ch);
        // the menu shows how many settled bets each competition, country and region has on those choices
        var done = scope.Where(b => b.Result is "win" or "loss").ToList();
        Menu = ClubTable.Menu(site, countries, Filter, value => Matchday.FilterComps(value, countries, intl) is { } ids ? done.Count(b => ids.Contains(b.League)) : done.Count, Titles, intl);
        var picked = Matchday.FilterComps(Filter, countries, intl);
        var all = picked is not null ? scope.Where(b => picked.Contains(b.League)).ToList() : scope;
        Empty = all.Count == 0;
        var s = Bets.Summarise(all, stake);

        Line LineOf(string label, Bets.Summary x, int? league = null, bool on = false) => new(label, league, on, x.Settled, x.Pending, x.Settled != 0 ? $"{x.Wins}/{x.Settled}" : "–",
            x.Settled != 0 ? new(Bets.SignedGbp(x.Profit), x.Profit > 0 ? "pos" : x.Profit < 0 ? "neg" : "") : null,
            x.Roi is { } roi ? new($"{(roi > 0 ? "+" : "")}{Js.ToFixed(100 * roi, 1)}%", roi > 0 ? "pos" : roi < 0 ? "neg" : "") : null);
        var after = Bets.BankAfter(all, stake, bank);
        Stake = Bets.Gbp(stake);
        Bank = Bets.Gbp(bank);
        MinEdge = Js.RoundInt(doc.Rules.MinEdge * 100);
        MaxOdds = doc.Rules.MaxOdds;
        Pending = s.Pending;
        Cards =
        [
            ("Simulated bank", Bets.Gbp(bank + s.Profit), $"Started with {Bets.Gbp(bank)}{(s.Pending != 0 ? $" · {Bets.Gbp(s.AtRisk)} on {s.Pending} pending" : "")}", ""),
            ("Simulated profit", s.Settled != 0 ? Bets.SignedGbp(s.Profit) : "–",
                s.Staked != 0 && s.Roi is { } r ? $"{Bets.Gbp(s.Staked)} staked · return {(r > 0 ? "+" : "")}{Js.ToFixed(100 * r, 1)}%" : $"{Bets.Gbp(stake)} on every bet",
                s.Settled != 0 ? (s.Profit > 0 ? "pos" : s.Profit < 0 ? "neg" : "") : ""),
            ("Won", s.Settled != 0 ? s.Wins.ToString() : "–", s.Settled != 0 ? $"{Home.PctText((double)s.Wins / s.Settled)} of settled bets" : "Needs settled bets", s.Settled != 0 ? $"of {s.Settled}" : ""),
            ("Beat the closing price", s.Beat is { } beat ? Home.PctText(beat) : "–", "Took better odds than the last price before kickoff. Only means something over a large sample, and is not proof of value on its own", ""),
        ];
        // (leagues level on bets stay in the order of their ids, as on the old site)
        Leagues = all.GroupBy(b => b.League).OrderBy(g => g.Key).Select(g => (Id: g.Key, X: Bets.Summarise(g.ToList(), stake)))
            .OrderByDescending(t => t.X.Settled).ThenByDescending(t => t.X.Placed)
            .Select(t => LineOf(site.CompLabel(t.Id), t.X, t.Id, t.Id.ToString() == Filter)).ToList();
        MarketLines = Bets.Markets.Select(mk => (Mk: mk, X: Bets.Summarise(all.Where(b => b.Market == mk).ToList(), stake))).Where(t => t.X.Placed != 0)
            .Select(t => LineOf(StatsFigures.MarketLabels[t.Mk], t.X)).ToList();
        var settled = all.Where(b => b.Result is not null).OrderByDescending(b => b.At).ThenByDescending(b => b.Id).ToList();
        SettledCount = settled.Count;
        SettledBets = settled.Take(300).Select(b => new Settled(b.Id, b.Kickoff, site.CompLabel(b.League), b.Strategy == "early" ? "Night before" : "Pre-kickoff", b.Result,
            $"{b.Home} v {b.Away}", b.Score, Bets.Teams(b), b.IsIntl, Bets.SelLabels.GetValueOrDefault(b.Selection) ?? b.Selection, Js.ToFixed(b.Odds, 2),
            b.Result == "win" ? new($"Won +{Bets.Gbp(stake * (b.Profit ?? 0))}", "pos") : b.Result == "loss" ? new($"Lost −{Bets.Gbp(stake)}", "neg") : new("Void, stake back", ""),
            $"{Bets.BetProbs(b)}{(b.ClosingOdds is { } co ? $" · closed {Js.ToFixed(co, 2)}" : "")}{(after.TryGetValue(b.Id, out var bk) ? $" · simulated bank {Bets.Gbp(bk)}" : "")}")).ToList();
        return Page();
    }

    // this page with some of its choices changed (a default is left out of the address)
    public Dictionary<string, string> Choices()
    {
        var q = new Dictionary<string, string>();
        if (Filter != "all") q["c"] = Filter;
        if (Ch.Strategy != "all") q["s"] = Ch.Strategy;
        if (Ch.Market != "all") q["m"] = Ch.Market;
        if (Ch.View != "all") q["v"] = Ch.View;
        return q;
    }
    public string Address(string key, string value)
    {
        var q = Choices();
        q[key] = value;
        var kept = q.Where(kv => kv.Value != "all").ToList();
        return kept.Count > 0 ? "?" + Markup.Query(kept) : Request.Path.Value!;
    }
    public Dictionary<string, string> Without(string key) { var q = Choices(); q.Remove(key); return q; }
}
