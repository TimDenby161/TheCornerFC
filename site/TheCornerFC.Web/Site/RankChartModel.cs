namespace TheCornerFC.Web.Site;

// What the season rank chart (_RankChart) is drawn from
public sealed record RankChartModel(List<PlayerPage.ChartPoint> Points, string Name);
