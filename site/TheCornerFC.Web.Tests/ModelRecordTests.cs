using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/changes.test.ts, for the parts of it The Model uses: the same cases and the same answers
public class ModelRecordTests
{
    static ModelDoc.Result Result(double delta = -0.00076, double[]? interval = null, string evaluation = "backtest", string metric = "log_loss", int? n = 44383, bool noInterval = false) =>
        new("result", evaluation, metric, delta, n, 0.9936, 0.99284, noInterval ? null : interval ?? [-0.00115, -0.00039]);
    static ModelDoc.Change Change(string id, string status = "Rejected", string stage = "Tested and rejected", bool deployed = false, string? deployedOn = null,
        string model = "match", List<ModelDoc.Result>? results = null) =>
        new(id, $"Change {id}", model, status, stage, deployed, deployedOn, null, new([]), results ?? [Result()], null);

    [Fact]
    public void A_result_is_better_or_worse_only_when_its_interval_leaves_zero_out()
    {
        Assert.Equal("better", ModelRecord.Tone(Result()));
        Assert.Equal("worse", ModelRecord.Tone(Result(0.0054, [0.0037, 0.0069])));
        Assert.Equal("unclear", ModelRecord.Tone(Result(-0.00024, [-0.00065, 0.00024])));
        Assert.Equal("unclear", ModelRecord.Tone(Result(-0.00113, noInterval: true)));
        Assert.Equal("better", ModelRecord.Tone(Result(0.01, [0.002, 0.02], metric: "accuracy")));
        Assert.Equal("worse", ModelRecord.Tone(Result(-0.05, [-0.09, -0.01], metric: "roi")));
    }

    [Fact]
    public void A_figure_is_written_with_its_sign_and_a_change_named_shortly()
    {
        Assert.Equal("−0.00076", ModelRecord.Signed(-0.00076));
        Assert.Equal("+0.00540", ModelRecord.Signed(0.0054));
        Assert.Equal("0.00000", ModelRecord.Signed(0));
        Assert.Equal("0.00000", ModelRecord.Signed(-0.0000001));
        Assert.Equal("A7", ModelRecord.ShortId("MC-0007"));
        Assert.Equal("A27", ModelRecord.ShortId("MC-0027"));
    }

    [Fact]
    public void A_change_speaks_through_the_strongest_evidence_it_has_on_a_measure()
    {
        var c = Change("MC-0001", results: [Result(-0.003, evaluation: "development"), Result(), Result(-0.001, evaluation: "prospective"), Result(-0.0004, metric: "brier")]);
        Assert.Equal(-0.001, ModelRecord.Headline(c)!.Delta);
        Assert.Equal(-0.0004, ModelRecord.Headline(c, "brier")!.Delta);
        Assert.Null(ModelRecord.Headline(c, "rps"));
    }

    [Fact]
    public void The_rows_put_proven_gains_first_then_the_unproven_then_the_proven_losses()
    {
        var rows = ModelRecord.DeltaRows([
            Change("MC-0001", results: [Result(0.0054, [0.0037, 0.0069])]),
            Change("MC-0002", results: [Result(-0.0074, [-0.0152, 0.0003], n: 1078)]),
            Change("MC-0003", results: [Result(-0.00076)]),
            Change("MC-0004", results: [Result(-0.0028, [-0.0041, -0.0015])]),
            Change("MC-0005", results: [Result(0.0001, [-0.0001, 0.0003])]),
        ], "log_loss");
        Assert.Equal(["MC-0004", "MC-0003", "MC-0002", "MC-0005", "MC-0001"], rows.Select(r => r.Id));
        Assert.Equal(["better", "better", "unclear", "unclear", "worse"], rows.Select(r => r.Tone));
        Assert.Equal(0.00076, rows[1].Gain);
    }

    [Fact]
    public void A_change_proven_better_by_any_amount_is_ready_listed_first_and_green()
    {
        static ModelDoc.Result Proven(double d, string evaluation = "backtest") => Result(d, [d - 0.0005, d + 0.0005], evaluation);
        var rows = ModelRecord.DeltaRows([
            Change("MC-0001", "Inconclusive", "Tested, not deployed", results: [Proven(-0.0008)]),
            Change("MC-0002", "Testing", "Being tested", results: [Proven(-0.0028)]),
            Change("MC-0003", "Inconclusive", "Tested, not deployed", results: [Proven(-0.0031, "prospective")]),
            Change("MC-0004", results: [Proven(-0.02)]),
        ], "log_loss");
        Assert.Equal([("MC-0003", true), ("MC-0002", true), ("MC-0001", true), ("MC-0004", false)], rows.Select(r => (r.Id, r.Ready)));
        Assert.Equal(["Ready: proven on new matches", "Ready on the historical test; being confirmed on new matches", "Ready on the historical test",
            "Proven on this test, but rejected: see why on its page"], rows.Select(r => r.ReadyNote));
        Assert.Equal(["ready", "ready", "ready", "none"], rows.Select(r => r.Mark));
    }

    static ModelDoc.LiveRecord Rec(int n = 3000, int weeks = 14, double gain = 0.001, double low = -0.002, double high = 0.004, string? verdict = null) =>
        new(n, weeks, gain, low, high, verdict);
    static readonly ModelDoc.LiveDoc Live = new("P15", "2026-10-14", new(500, 8), 3000, 14, "2027-01-20", new()
    {
        ["MC-0001"] = Rec(gain: 0.0031, low: 0.0004, high: 0.0058, verdict: "better"), ["MC-0002"] = Rec(),
        ["MC-0003"] = Rec(gain: -0.004, low: -0.007, high: -0.001, verdict: "worse"), ["MC-0004"] = Rec(120, 1),
        ["MC-0005"] = Rec(gain: 0.0006, low: 0.0001, high: 0.0011, verdict: "better"),
    }, new() { ["MC-0006"] = "Testing chose no setting, so there is nothing to run" });

    [Fact]
    public void The_live_record_adds_matches_gain_and_a_call_made_only_by_the_watching_method()
    {
        var unproven = Result(-0.0005, [-0.001, 0.0002]);
        var rows = ModelRecord.DeltaRows(new[] { "MC-0001", "MC-0002", "MC-0003", "MC-0004", "MC-0005", "MC-0006" }
            .Select(id => Change(id, "Inconclusive", "Tested, not deployed", results: [unproven])).ToList(), "log_loss", Live);
        var by = rows.ToDictionary(r => r.Id);
        Assert.Equal((true, "ready", "Ready: proven on live matches"), (by["MC-0001"].Ready, by["MC-0001"].Mark, by["MC-0001"].ReadyNote));
        Assert.Equal(("none", "Not proven either way yet"), (by["MC-0002"].Mark, by["MC-0002"].LiveText));
        Assert.Equal(("worse", "Proven worse on live matches"), (by["MC-0003"].Mark, by["MC-0003"].LiveText));
        Assert.Equal("Too early: needs 500 matches and 8 weeks", by["MC-0004"].LiveText);
        Assert.Equal(("ready", "Proven better on live matches"), (by["MC-0005"].Mark, by["MC-0005"].LiveText));
        Assert.Equal(("Not run live", "Testing chose no setting, so there is nothing to run"), (by["MC-0006"].LiveText, by["MC-0006"].LiveWhy));
        Assert.Equal("MC-0001", rows[0].Id);
        Assert.Equal((false, "No live record yet"), (ModelRecord.DeltaRows([Change("MC-0001", "Inconclusive", results: [unproven])], "log_loss")[0] is var r ? (r.Ready, r.LiveText) : default));
        // a change already in production is never marked ready by its live record
        Assert.False(ModelRecord.DeltaRows([Change("MC-0001", "Accepted", deployed: true, deployedOn: "2026-09-01", results: [unproven])], "log_loss", Live)[0].Ready);
        // a change with no past result is listed for its live record alone, after those with a past
        var release = ModelRecord.DeltaRows([Change("MC-0001", "Accepted", deployed: true, deployedOn: "2026-10-14", results: []),
            Change("MC-0002", "Inconclusive", results: [unproven]), Change("MC-0007", results: [])], "log_loss", Live);
        Assert.Equal(["MC-0002", "MC-0001"], release.Select(x => x.Id));
        Assert.Equal(((double?)null, (int?)null, false, "none", "In production: checked on live matches", "Proven better on live matches"),
            (release[1].Gain, release[1].N, release[1].Ready, release[1].Mark, release[1].ReadyNote, release[1].LiveText));
        Assert.Empty(ModelRecord.DeltaRows([Change("MC-0001", "Inconclusive", results: [])], "brier", Live)); // the live record is log loss only
    }

    [Fact]
    public void The_improvement_adds_up_only_the_changes_in_production_in_the_order_they_went_live()
    {
        var steps = ModelRecord.Cumulative([
            Change("MC-0003", deployed: true, deployedOn: "2026-11-01", results: [Result(-0.002)]),
            Change("MC-0001", deployed: true, deployedOn: "2026-09-01", results: [Result(-0.00113, noInterval: true)]),
            Change("MC-0002"),
            Change("MC-0004", deployed: true, deployedOn: "2026-09-25", model: "betting", results: []),
            Change("MC-0005", deployed: true, deployedOn: "2026-12-01", results: [Result(-0.01, evaluation: "development")]),
        ]);
        Assert.Equal(["MC-0001", "MC-0003", "MC-0005"], steps.Select(s => s.Id));
        Assert.Equal([-0.00113, -0.002, null], steps.Select(s => s.Delta));
        Assert.Equal(-0.00313, steps[2].Total, 6);
    }

    static ModelDoc.SeriesPoint Month(string m, string source, double n, double ll, double h, double d, double a) => new(m, source, n, ll, h, d, a);

    [Fact]
    public void The_model_is_set_beside_guessing_the_base_rates_of_the_months_before_the_live_record()
    {
        var got = ModelRecord.AgainstBaseRates([Month("2026-08", "backfill", 1000, 0.99, 440, 250, 310), Month("2026-09", "backfill", 1000, 1.0, 460, 230, 310),
            Month("2026-09", "live", 200, 0.96, 100, 40, 60), Month("2026-10", "live", 600, 0.98, 270, 140, 190), Month("2026-10", "backfill", 50, 1.2, 0, 50, 0)])!;
        Assert.Equal([0.44, 0.25, 0.31], got.Rates.Select(r => Math.Round(r, 3)));
        Assert.Equal(800, got.N);
        Assert.Equal((200 * 0.96 + 600 * 0.98) / 800, got.Model, 9);
        Assert.Equal(-(370 * Math.Log(0.44) + 180 * Math.Log(0.25) + 250 * Math.Log(0.31)) / 800, got.Base, 9);
        Assert.Null(ModelRecord.AgainstBaseRates([new("2026-10", "live", 600, 0.98, null, null, null)]));
        Assert.Null(ModelRecord.AgainstBaseRates([Month("2026-10", "live", 600, 0.98, 270, 140, 190)]));
        Assert.Null(ModelRecord.AgainstBaseRates([]));
    }

    [Fact]
    public void The_best_gain_waiting_is_the_largest_proven_one_not_in_production()
    {
        var best = ModelRecord.BestWaiting([
            Change("MC-0001", "Testing", "Being tested", results: [Result(-0.0028, [-0.0041, -0.0015])]),
            Change("MC-0002", "Inconclusive", "Tested, not deployed", results: [Result(-0.0008, [-0.0014, -0.0002])]),
            Change("MC-0003", "Testing", "Being tested", results: [Result(-0.009, evaluation: "development", noInterval: true)]),
            Change("MC-0004", "Accepted", "Deployed to production", deployed: true, deployedOn: "2026-09-01", results: [Result(-0.02)]),
            Change("MC-0005", results: [Result(-0.03)]),
        ])!;
        Assert.Equal(("MC-0001", (double?)0.0028), (best.Id, best.Gain));
        Assert.Null(ModelRecord.BestWaiting([Change("MC-0005")]));
    }
}
