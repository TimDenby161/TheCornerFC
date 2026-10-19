using System.Text.Json;
using System.Text.Json.Serialization;
using TheCornerFC.Web.Data;
using Match = TheCornerFC.Web.Data.Match;

namespace TheCornerFC.Web.Site;

// A match's stored explanation (site_match_detail: predictions.explain(), kept with the match),
// with the model version that made it by name
public sealed record DetailAnswer(Why? Why, DetailAnswer.Version? Model, bool? Locked)
{
    public sealed record Version(string? Name, string? Code);
}

public sealed record Why(
    bool[]? Fallback, double?[] Current, double?[] Baseline, double?[] Match,
    Dictionary<string, double> Margin, [property: JsonPropertyName("exp_diff")] double ExpDiff,
    [property: JsonPropertyName("league_goals")] double LeagueGoals, double? Tendencies,
    double?[] Missing, double?[][]? Lines, bool? Neutral,
    [property: JsonPropertyName("captured_at")] string CapturedAt, string Source,
    [property: JsonPropertyName("injuries_at")] string? InjuriesAt, [property: JsonPropertyName("odds_at")] string? OddsAt, string? Model,
    // a national match: each side's predicted XI, [player, name, role]
    Dictionary<string, JsonElement[][]>? Xi,
    Steps? Steps);

// The arithmetic from the inputs to the chances, with the weights the model used
// (site_matches.worked_steps): home first in every pair
public sealed record Steps(
    [property: JsonPropertyName("now_share")] double? NowShare,
    double?[][] Record, double[] League, double[] Shrunk, double[] Plain,
    [property: JsonPropertyName("open_total")] double? OpenTotal, double[] Base,
    double Scale, double[] Xg, double[] Poisson, double Boost, double[] Chances, string Likely, Steps.Weighting Weights)
{
    public sealed record Weighting(double[] Now, double Shrink, double Open, double[] Draw, double Absence, double Line);
}

// A match's model detail (web/src/lib/matchDetail.ts): everything here sets out what the
// prediction's own explanation holds; none of it is worked out again.
public static class MatchDetail
{
    // a row's value: words, or a moment (shown in the visitor's own time)
    public sealed record When([property: JsonPropertyName("when")] string At);
    public sealed record Row(
        [property: JsonPropertyName("label")] string Label, [property: JsonPropertyName("value")] object Value,
        [property: JsonPropertyName("tip"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? Tip = null,
        [property: JsonPropertyName("teams"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] bool? Teams = null);
    public sealed record Section(
        [property: JsonPropertyName("title")] string Title, [property: JsonPropertyName("rows")] List<Row> Rows,
        [property: JsonPropertyName("unit"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? Unit = null,
        [property: JsonPropertyName("note"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? Note = null);
    public sealed record Detail([property: JsonPropertyName("sections")] List<Section> Sections, [property: JsonPropertyName("notes")] List<string> Notes);

    static readonly Dictionary<string, (string Label, string Tip)> MarginLabels = new()
    {
        ["strength"] = ("Strength gap", "Home minus away match strength (the blend of Current and Baseline Strength), 100 points = 1 goal"),
        ["home_advantage"] = ("Home advantage", "The same for every club: 0.3 goals"),
        ["europe_home"] = ("European tie", "Extra home margin in UEFA club competitions"),
        ["home_edges"] = ("Clubs' home/away record", "The home side's own home edge plus the away side's own away weakness, from past results"),
        ["absences"] = ("Known absences", "Players listed injured, suspended or doubtful, weighted by their recent minutes"),
        ["lineups"] = ("Predicted line-ups", "Predicted XI ratings by line (defence, midfield, attack)"),
    };
    // National team matches: the national ranking's own strengths and home advantage
    static readonly Dictionary<string, (string Label, string Tip)> IntlMarginLabels = new()
    {
        ["strength"] = ("Strength gap", "Home minus away Current Strength (the national team ranking), 100 points = 1 goal"),
        ["home_advantage"] = ("Home advantage", "The same for every national team: 0.5 goals. None at a neutral ground"),
    };
    static readonly Dictionary<string, string> SourceText = new()
    {
        ["prospective"] = "captured before kickoff", ["late_observation"] = "captured after kickoff", ["reconstruction"] = "reconstructed afterwards from pre-match data",
    };
    static string Whole(double v) => Js.Num(Js.RoundInt(v));
    static string? Pair(double? h, double? a, Func<double, string>? f = null)
    {
        f ??= Whole;
        return h is null && a is null ? null : $"{(h is { } x ? f(x) : "–")} · {(a is { } y ? f(y) : "–")}";
    }
    static double? At(double?[]? a, int i) => a is not null && i < a.Length ? a[i] : null;
    static int Pct(double v) => Js.RoundInt(v * 100);

    sealed class Builder
    {
        public readonly List<Section> Sections = [];
        public void Add(string title, IEnumerable<Row?> rows, string? unit = null, string? note = null)
        {
            var kept = rows.Where(r => r is not null).Select(r => r!).ToList();
            if (kept.Any(r => r.Teams != true)) Sections.Add(new(title, kept, unit, note));
        }
    }
    static Row? R(string label, object? value, string tip = "") =>
        value is null || value is "" ? null : new(label, value, tip == "" ? null : tip);

    public static Detail Of(Match m, Why? x, DetailAnswer.Version? modelInfo, string home, string away)
    {
        var finished = ClubData.Finished.Contains(m.Status) && m.Hg is not null;
        var b = new Builder();
        var notes = new List<string>();
        var intl = m.Intl is > 0;

        if (x is not null)
        {
            var missing = (x.Fallback ?? []).Select((f, i) => f ? (i > 0 ? away : home) : null).Where(n => n is not null).ToList();
            b.Add("Strength", [
                new("", $"{home} · {away}", Teams: true),
                R("Current Strength", Pair(At(x.Current, 0), At(x.Current, 1)), "Elo rating now, from recent results"),
                R("Baseline Strength", Pair(At(x.Baseline, 0), At(x.Baseline, 1)), "Long-term level (LT ALGO)"),
                R("Used for this match", Pair(At(x.Match, 0), At(x.Match, 1)), "A blend of Current and Baseline Strength; matches further away lean more on Baseline"),
                x.Steps?.NowShare is { } share ? R("Blend", $"{Pct(share)}% Current · {100 - Pct(share)}% Baseline",
                    $"{Pct(x.Steps.Weights.Now[0])}% Current for a match today, sliding to {Pct(x.Steps.Weights.Now[1])}% for one a year or more away") : null,
            ], note: missing.Count > 0 ? $"No rating history yet for {string.Join(" or ", missing)}: the competition's starting strength was used." : null);
            b.Add("Expected margin", x.Margin.Select(kv =>
            {
                var (label, tip) = intl && IntlMarginLabels.TryGetValue(kv.Key, out var il) ? il : MarginLabels.TryGetValue(kv.Key, out var ml) ? ml : (kv.Key, "");
                return R(label, Cards.SignedGoals(kv.Value), tip);
            }).Append(R("Total", Cards.SignedGoals(x.ExpDiff), "The model's expected home minus away goals")), unit: "goals, + favours home");
            if (x.Steps is not null) WorkedSteps(x.Steps, x.ExpDiff, home, away, b);
        }

        b.Add("Goals", [
            x is not null && intl ? R("Two level sides", $"{Js.ToFixed(x.LeagueGoals, 1)} a game", "The goals a match between two evenly ranked national teams is expected to have; the expected margin moves it from there") : null,
            x is not null && !intl ? R("Competition average", $"{Js.ToFixed(x.LeagueGoals, 1)} a game", "Average goals per game in this competition over the last 12 months") : null,
            x?.Tendencies is { } t ? R("Attack/defence tendencies", $"{Cards.SignedGoals(t)} total", "How much both clubs' attacking and defensive styles move the expected total, against level sides") : null,
            m.HomeXg is { } hx && m.AwayXg is { } ax ? R("Projected total", Js.ToFixed(hx + ax, 1)) : null,
            m.POver25 is { } o && m.PBtts is { } bt ? R("Over 2.5 · both score", $"{Pct(o)}% · {Pct(bt)}%") : null,
        ]);

        var (missH, missA) = x is not null ? (At(x.Missing, 0), At(x.Missing, 1)) : (m.HomeMissing, m.AwayMissing);
        b.Add("Known absences", [R("Missing players", Pair(missH, missA, v => Js.ToFixed(v, 1)),
            "Players listed injured, suspended or doubtful, weighted by their share of recent minutes (1.0 = one ever-present player). – = no injury list")]);

        var xi = m.HomeXi is not null && m.AwayXi is not null;
        var lineRows = new List<Row?>
        {
            xi ? R($"{(finished ? "Starting" : "Predicted")} XI rating", $"{Js.RoundInt(m.HomeXi!.Value)} · {Js.RoundInt(m.AwayXi!.Value)}", "Average player rank (0–100)") : null,
            xi && m.HomeRecentXi is { } hr && m.AwayRecentXi is { } ar ? R("Last 5 XIs", $"{Js.RoundInt(hr)} · {Js.RoundInt(ar)}") : null,
        };
        if (x?.Lines is { } lines)
            lineRows.AddRange(new[] { "DEF", "MID", "FWD" }.Select((k, j) => R($"Model input, {k}", Pair(At(lines.ElementAtOrDefault(0), j + 1), At(lines.ElementAtOrDefault(1), j + 1)),
                "The predicted XI's average rank in this line, as the model used it")));
        b.Add(finished ? "Line-ups" : "Predicted line-ups", lineRows);

        if (m.MHome is { } mh && m.MDraw is { } md && m.PHome is { } ph && m.PDraw is { } pd)
        {
            int[] model = Cards.ShownProbs(ph, pd), market = Cards.ShownProbs(mh, md);
            var diff = model.Select((v, i) => { var d = v - market[i]; return $"{(d > 0 ? "+" : d < 0 ? "−" : "")}{Math.Abs(d)}"; });
            b.Add("Model vs market", [
                R("Model", $"{string.Join(" · ", model)}%"),
                R("Market fair", $"{string.Join(" · ", market)}%", "The average across bookmakers with their margin removed"),
                R("Difference", $"{string.Join(" · ", diff)} pts", "Model probability minus market fair probability, in percentage points. A difference is a disagreement with the market, not a betting edge or proof of value."),
            ], unit: "H · D · A", note: "A disagreement with the market, not a betting edge.");
        }

        if (x is not null)
        {
            var source = SourceText.GetValueOrDefault(x.Source) ?? x.Source;
            b.Add("Data", [
                x.Neutral == true ? R("Venue", "Neutral ground", "No home advantage counted") : null,
                R("Model inputs", new When(x.CapturedAt), $"Inputs {source}"),
                x.Source != "prospective" ? R("Captured", source) : null,
                R("Injury list seen", x.InjuriesAt is { } ia ? new When(ia) : null),
                R("Odds seen", x.OddsAt is { } oa ? new When(oa) : null),
                R("Model version", modelInfo?.Name is { Length: > 0 } vn ? $"{vn}{(modelInfo.Code is { Length: > 0 } code ? $" · {code}" : "")}" : null,
                    x.Model is { } id ? $"Version id {(id.Length > 11 ? id[..11] : id)}" : ""),
            ]);
        }
        else if (m.PHome is not null) notes.Add("No breakdown for this prediction: its captured model inputs aren't available.");
        notes.Add("These are the model's inputs and how much each moved its numbers, not a statement of what will decide the match.");
        return new(b.Sections, notes);
    }

    static string Two(double? v) => v is { } x ? Js.ToFixed(x, 2) : "–";
    static string PctText(double[] p) => $"{string.Join(" · ", Cards.ShownProbs(p[0], p[1]))}%";

    // From each side's goals record to the chances, one step at a time, with the numbers and
    // weights the model used. Every figure is the stored one; the sums only show how they follow
    static void WorkedSteps(Steps s, double expDiff, string home, string away, Builder b)
    {
        double?[] h = s.Record[0], a = s.Record[1];
        var w = s.Weights;
        b.Add("Each side's usual goals", [
            new("", $"{home} · {away}", Teams: true),
            R("Scored", $"{Two(At(h, 0))} · {Two(At(a, 0))}", $"{home} at home and {away} away, over the last 12 months. xG is used instead of goals for any match that has it"),
            R("Conceded", $"{Two(At(h, 1))} · {Two(At(a, 1))}"),
            R("Games", $"{Raw(At(h, 2))} · {Raw(At(a, 2))}"),
            R("Competition average", $"{Two(s.League[0])} home · {Two(s.League[1])} away"),
            R($"Home goals, {home}", $"({Two(s.Shrunk[0])} + {Two(s.Shrunk[1])}) ÷ 2 = {Two(s.Plain[0])}", $"{home}'s scoring at home and {away}'s conceding away, each pulled towards the competition's average"),
            R($"Away goals, {away}", $"({Two(s.Shrunk[2])} + {Two(s.Shrunk[3])}) ÷ 2 = {Two(s.Plain[1])}", $"{away}'s scoring away and {home}'s conceding at home, each pulled towards the competition's average"),
        ], unit: "a game", note: $"Each average counts {Raw(w.Shrink)} games at the competition's average as well as the side's own, so a short record moves the numbers less.");
        if (s.OpenTotal is { } open)
        {
            var records = s.Plain[0] + s.Plain[1];
            b.Add("How open the game is", [
                R("From the goals records", Js.ToFixed(records, 2), "The two numbers above added up"),
                R("From attack and defence", Js.ToFixed(open, 2), "Both clubs' attacking and defensive ratings, for two level sides"),
                R("Blended", $"{Js.RoundInt((1 - w.Open) * 100)}% × {Js.ToFixed(records, 2)} + {Js.RoundInt(w.Open * 100)}% × {Js.ToFixed(open, 2)} = {Js.ToFixed(s.Base[0] + s.Base[1], 2)}"),
                R("Goals before the margin", $"{Two(s.Base[0])} · {Two(s.Base[1])}", "The two sides keep their shares of the total"),
            ], unit: "total goals");
        }
        b.Add("Projected goals", [
            R("Expected margin", Cards.SignedGoals(expDiff), "From the expected margin above"),
            R("Scaled", $"{Two(s.Base[0])} × {Js.ToFixed(s.Scale, 3)} · {Two(s.Base[1])} ÷ {Js.ToFixed(s.Scale, 3)}", "One factor raises the home side's goals and lowers the away side's until the gap between them is the expected margin"),
            R("Projected goals", $"{Two(s.Xg[0])} · {Two(s.Xg[1])}"),
        ]);
        b.Add("Chances", [
            R("From the projected goals", PctText(s.Poisson), "Each side's goals as a Poisson distribution, 0 to 10 goals, every scoreline's chance added up"),
            R("Draw boost", $"× {Js.ToFixed(s.Boost, 3)}", $"Up to × {Raw(w.Draw[0])} in a close game, none once the projected margin reaches {Raw(w.Draw[1])} goals: models like this one under-count draws"),
            R("Final chances", PctText(s.Chances)),
            R("Most likely score", s.Likely),
        ], unit: "H · D · A");
    }

    // a number as JavaScript writes it in a template (`${v}`): 4, 0.5, 1.15, null
    static string Raw(double? v) => v is { } x ? JsNumber(x) : "null";
    static string JsNumber(double x) => x == Math.Floor(x) && Math.Abs(x) < 1e21 ? ((long)x).ToString(System.Globalization.CultureInfo.InvariantCulture)
        : x.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
}
