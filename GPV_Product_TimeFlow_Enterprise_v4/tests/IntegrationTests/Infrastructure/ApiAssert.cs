using System.Net;
using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.IntegrationTests.Infrastructure;

public static class ApiAssert
{
    public static async Task<ApiException> FailsWithAsync(HttpStatusCode expected, Func<Task> call)
    {
        var ex = await Assert.ThrowsAsync<ApiException>(call);
        Assert.True(ex.Status == expected, $"Se esperaba {(int)expected} y se obtuvo {(int)ex.Status}: {ex.Message}");
        return ex;
    }
}
