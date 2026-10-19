using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

// web/src/lib/stats.test.ts, for the C# site: the same cases and the same answers
public class StatsTests
{
    static StatsDoc.Stats Part(int n, double correct) => new()
    {
        N = n, Live = n / 2, Rated = n, Correct = correct, Exact = 0.1, HomeRate = 0.45, LogLoss = 1, Brier = 0.6, GoalError = 0.9,
        RatingAvg = 3, RatingCounts = [0, 0, n, 0, 0], FactorAvgs = new() { ["winner"] = 3 }, Calibration = [[n, 0.05, 0.1], [0, null, null]],
    };
    static StatsDoc.MarketPair WithOdds(int n, double ll) => new(n, ll, ll - 0.02, 0.5, 0.52);

    [Fact]
    public void One_competition_comes_back_as_it_is_and_none_gives_nothing()
    {
        var a = Part(10, 0.5);
        Assert.Same(a, StatsFigures.Merge([a]));
        Assert.Null(StatsFigures.Merge([]));
    }

    [Fact]
    public void Counts_add_up_and_averages_are_weighted_by_matches()
    {
        var m = StatsFigures.Merge([Part(100, 0.6), Part(300, 0.4)])!;
        Assert.Equal(400, m.N);
        Assert.Equal(200, m.Live);
        Assert.Equal(0.45, m.Correct!.Value, 9);
        Assert.Equal([0, 0, 400, 0, 0], m.RatingCounts!);
        Assert.Equal(3, m.RatingAvg);
        Assert.Equal(3, m.FactorAvgs!["winner"]);
    }

    [Fact]
    public void The_market_comparison_merges_over_the_competitions_that_have_one_by_matches_with_odds()
    {
        var m = StatsFigures.Merge([Part(100, 0.5) with { Market = WithOdds(50, 1) }, Part(100, 0.5) with { Market = WithOdds(150, 0.96) }, Part(100, 0.5)])!;
        Assert.Equal(200, m.Market!.N);
        Assert.Equal(0.97, m.Market.ModelLl!.Value, 9);
        Assert.Null(StatsFigures.Merge([Part(1, 0.5), Part(1, 0.5)])!.Market);
    }

    [Fact]
    public void Each_calibration_band_merges_by_its_calls_an_empty_band_staying_empty()
    {
        var m = StatsFigures.Merge([Part(100, 0.5), Part(300, 0.5) with { Calibration = [[300, 0.07, 0.02], [0, null, null]] }])!;
        Assert.Equal(400, m.Calibration![0][0]);
        Assert.Equal(0.065, m.Calibration[0][1]!.Value, 9);
        Assert.Equal(0.04, m.Calibration[0][2]!.Value, 9);
        Assert.Equal([0, null, null], m.Calibration[1]);
    }

    [Fact]
    public void The_bet_markets_merge_the_opening_comparison_over_matches_that_have_one()
    {
        static Dictionary<string, StatsDoc.MarketStats> Mk(int n, int openN) => new() { ["1X2"] = new(n, 1, 0.98, openN, openN != 0 ? 1.02 : null, openN != 0 ? 1 : null) };
        var m = StatsFigures.Merge([Part(10, 0.5) with { Markets = Mk(100, 40) }, Part(10, 0.5) with { Markets = Mk(50, 0) }])!;
        Assert.Equal((150, 40), (m.Markets!["1X2"].N, m.Markets["1X2"].OpenN));
        Assert.Equal(1.02, m.Markets["1X2"].ModelOpenLl!.Value, 9);
    }

    [Fact]
    public void A_share_is_written_as_a_percentage()
    {
        Assert.Equal("53.0%", Home.PctText(0.5298));
        Assert.Equal("34%", Home.PctText(0.337, 0));
    }
}
