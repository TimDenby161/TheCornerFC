using TheCornerFC.Web.Site;

namespace TheCornerFC.Web.Tests;

public class TimesTests
{
    [Fact]
    public void A_visitor_without_a_cookie_or_with_a_bad_one_gets_uk_time_until_the_page_sets_it()
    {
        Assert.Equal(new ZoneChoice("Europe/London", false), ZoneChoice.From(null));
        Assert.Equal(new ZoneChoice("Europe/London", false), ZoneChoice.From("Mars/Olympus"));
        Assert.Equal(new ZoneChoice("America/New_York", false), ZoneChoice.From("America/New_York"));
        Assert.Equal(new ZoneChoice("Europe/London", true), ZoneChoice.From("off"));
    }

    [Fact]
    public void Writes_an_instant_in_the_visitors_zone()
    {
        var kickoff = DateTimeOffset.Parse("2026-10-17T14:00:00Z");
        Assert.Equal("15:00", Times.Show(kickoff, "Europe/London", "time"));
        Assert.Equal("10:00", Times.Show(kickoff, "America/New_York", "time"));
        Assert.Equal("9:05", Times.Show(DateTimeOffset.Parse("2026-10-17T08:05:00Z"), "Europe/London", "time"));
        Assert.Equal("Sat 17 Oct", Times.Show(kickoff, "Europe/London", "day"));
        Assert.Equal("18 Oct", Times.Show(DateTimeOffset.Parse("2026-10-17T23:30:00Z"), "Asia/Tokyo", "short"));
    }
}
