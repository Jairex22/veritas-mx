using GPV.ProductTimeFlow.Domain;

namespace GPV.ProductTimeFlow.UnitTests.Domain;

public class VacationEntitlementPolicyTests
{
    [Theory]
    [InlineData(0, 12)]
    [InlineData(1, 12)]
    [InlineData(2, 14)]
    [InlineData(3, 16)]
    [InlineData(4, 18)]
    [InlineData(5, 20)]
    [InlineData(6, 22)]
    [InlineData(10, 22)]
    [InlineData(11, 24)]
    [InlineData(15, 24)]
    [InlineData(16, 26)]
    [InlineData(21, 28)]
    public void Days_follow_LFT_2023_table(int years, int expected)
    {
        Assert.Equal(expected, VacationEntitlementPolicy.DaysForYearsOfService(years));
    }

    [Theory]
    [InlineData("2020-06-15", "2026-06-14", 5)]
    [InlineData("2020-06-15", "2026-06-15", 6)]
    [InlineData("2020-06-15", "2026-12-31", 6)]
    [InlineData("2026-06-15", "2026-06-14", 0)]  // aún no ingresa: nunca negativo
    [InlineData("2024-02-29", "2025-02-28", 1)]  // AddYears ajusta 29-feb → 28-feb
    [InlineData("2024-02-29", "2025-02-27", 0)]
    public void CompletedYears_counts_full_anniversaries(string hire, string asOf, int expected)
    {
        Assert.Equal(expected, VacationEntitlementPolicy.CompletedYears(DateOnly.Parse(hire), DateOnly.Parse(asOf)));
    }
}

public class FolioFormatterTests
{
    [Theory]
    [InlineData(2026, 1, "TF-2026-000001")]
    [InlineData(2026, 123456, "TF-2026-123456")]
    [InlineData(2027, 42, "TF-2027-000042")]
    public void Format_pads_sequence_to_six_digits(int year, int seq, string expected)
    {
        var folio = FolioFormatter.Format(year, seq);
        Assert.Equal(expected, folio);
        Assert.True(FolioFormatter.IsValid(folio));
    }

    [Theory]
    [InlineData("")]
    [InlineData("TF-2026-00001")]
    [InlineData("TF-2026-0000001")]
    [InlineData("XX-2026-000001")]
    [InlineData("tf-2026-000001")]
    [InlineData("TF_2026_000001")]
    [InlineData("TF-20A6-000001")]
    [InlineData("TF-2026-00000A")]
    [InlineData("TF-2026/000001")]
    public void IsValid_rejects_malformed_folios(string folio)
    {
        Assert.False(FolioFormatter.IsValid(folio));
    }
}
