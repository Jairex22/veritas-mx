using System.Net;
using System.Net.Http.Json;
using GPV.ProductTimeFlow.IntegrationTests.Infrastructure;
using GPV.ProductTimeFlow.Shared;
using Microsoft.AspNetCore.Mvc;

namespace GPV.ProductTimeFlow.IntegrationTests;

public class AuthenticationTests(TimeFlowApiFactory factory) : IClassFixture<TimeFlowApiFactory>
{
    private static async Task<(HttpStatusCode Status, ProblemDetails? Problem)> RawLoginAsync(HttpClient http, string email, string password)
    {
        using var r = await http.PostAsJsonAsync("api/v1/auth/login", new LoginRequest { Email = email, Password = password });
        var problem = r.IsSuccessStatusCode ? null : await r.Content.ReadFromJsonAsync<ProblemDetails>();
        return (r.StatusCode, problem);
    }

    [Fact]
    public async Task Login_with_valid_credentials_returns_token_and_profile()
    {
        var client = factory.Anonymous();
        var login = await client.LoginAsync(new LoginRequest { Email = TimeFlowApiFactory.Ana, Password = TimeFlowApiFactory.Password });
        Assert.False(string.IsNullOrWhiteSpace(login.AccessToken));
        Assert.True(login.ExpiresAtUtc > DateTime.UtcNow);
        Assert.Equal(TimeFlowApiFactory.Ana, login.Profile.Email);
        Assert.Equal("Laura Hernández Vega", login.Profile.SupervisorName);
        Assert.Equal("Carlos Mendoza Ríos", login.Profile.ManagerName);

        client.SetToken(login.AccessToken);
        var me = await client.MeAsync();
        Assert.Equal(login.Profile.EmployeeId, me.EmployeeId);
    }

    [Fact]
    public async Task Wrong_password_and_unknown_user_get_the_same_generic_401()
    {
        using var http = factory.CreateClient();
        var wrong = await RawLoginAsync(http, TimeFlowApiFactory.Laura, "incorrecta-123");
        var unknown = await RawLoginAsync(http, "no.existe@" + TimeFlowApiFactory.Domain, "incorrecta-123");

        Assert.Equal(HttpStatusCode.Unauthorized, wrong.Status);
        Assert.Equal(HttpStatusCode.Unauthorized, unknown.Status);
        Assert.Equal(wrong.Problem!.Detail, unknown.Problem!.Detail);
        Assert.Equal("Correo o contraseña incorrectos.", wrong.Problem.Detail);

        // Un fallo aislado no bloquea: la contraseña correcta sigue funcionando.
        var ok = await RawLoginAsync(http, TimeFlowApiFactory.Laura, TimeFlowApiFactory.Password);
        Assert.Equal(HttpStatusCode.OK, ok.Status);
    }

    [Fact]
    public async Task Account_is_locked_after_five_failures_with_423()
    {
        var email = await factory.CreateEmployeeAsync(); // cuenta dedicada: no afecta a otras pruebas
        using var http = factory.CreateClient();
        Assert.Equal(HttpStatusCode.OK, (await RawLoginAsync(http, email, TimeFlowApiFactory.Password)).Status);

        for (var i = 1; i <= 4; i++)
            Assert.Equal(HttpStatusCode.Unauthorized, (await RawLoginAsync(http, email, $"mala-{i}")).Status);

        var fifth = await RawLoginAsync(http, email, "mala-5");
        Assert.Equal((HttpStatusCode)423, fifth.Status);

        // Bloqueada incluso con la contraseña correcta.
        var correct = await RawLoginAsync(http, email, TimeFlowApiFactory.Password);
        Assert.Equal((HttpStatusCode)423, correct.Status);
        Assert.Contains("bloqueada", correct.Problem!.Detail);

        var locked = await factory.WithDbAsync(db => Task.FromResult(db.Users.Single(u => u.Employee!.NormalizedEmail == email).LockoutEndUtc));
        Assert.NotNull(locked);
        Assert.True(locked > DateTime.UtcNow.AddMinutes(10));
    }

    [Fact]
    public async Task Parallel_logins_of_the_same_account_all_succeed()
    {
        var results = await Task.WhenAll(Enumerable.Range(0, 10).Select(async _ =>
        {
            using var http = factory.CreateClient();
            return (await RawLoginAsync(http, TimeFlowApiFactory.Carlos, TimeFlowApiFactory.Password)).Status;
        }));
        Assert.All(results, s => Assert.Equal(HttpStatusCode.OK, s));
    }

    [Fact]
    public async Task Unauthenticated_requests_get_401()
    {
        using var http = factory.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await http.GetAsync("api/v1/requests")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await http.GetAsync("api/v1/me")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await http.GetAsync("api/v1/admin/employees")).StatusCode);

        http.DefaultRequestHeaders.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", "token.invalido.xyz");
        Assert.Equal(HttpStatusCode.Unauthorized, (await http.GetAsync("api/v1/requests")).StatusCode);
    }

    [Fact]
    public async Task Typed_client_maps_401_to_api_exception()
    {
        var client = factory.Anonymous();
        await ApiAssert.FailsWithAsync(HttpStatusCode.Unauthorized, () => client.ListRequestsAsync(new RequestQuery()));
    }
}
