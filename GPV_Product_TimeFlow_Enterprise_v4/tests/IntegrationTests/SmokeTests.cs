using GPV.ProductTimeFlow.IntegrationTests.Infrastructure;

namespace GPV.ProductTimeFlow.IntegrationTests;

public class SmokeTests(TimeFlowApiFactory factory) : IClassFixture<TimeFlowApiFactory>
{
    [Fact]
    public async Task Api_uses_isolated_temp_data_root_and_small_seed()
    {
        using var client = factory.CreateClient();
        var health = await client.GetAsync("/health");
        health.EnsureSuccessStatusCode();
        Assert.True(File.Exists(Path.Combine(factory.DataRoot, "timeflow.db")), "La BD SQLite debe crearse en el DataRoot temporal");
        var employees = await factory.WithDbAsync(db => Microsoft.EntityFrameworkCore.EntityFrameworkQueryableExtensions.CountAsync(db.Employees));
        Assert.Equal(12, employees);
        var requests = await factory.WithDbAsync(db => Microsoft.EntityFrameworkCore.EntityFrameworkQueryableExtensions.CountAsync(db.Requests));
        Assert.Equal(0, requests);
    }
}
