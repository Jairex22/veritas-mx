using System.Net;
using System.Net.Http.Json;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Shared;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace GPV.ProductTimeFlow.IntegrationTests.Infrastructure;

/// <summary>
/// API real (Program) sobre SQLite en un directorio temporal propio. Una instancia por clase de prueba (IClassFixture).
/// </summary>
public sealed class TimeFlowApiFactory : WebApplicationFactory<Program>
{
    public const string Password = "Demo#TimeFlow2026";
    public const string Domain = "demo.timeflow.example";
    public const string Ana = "ana.empleada@" + Domain;
    public const string Laura = "laura.jefa@" + Domain;
    public const string Carlos = "carlos.superior@" + Domain;
    public const string Sofia = "registro.admin@" + Domain;
    public const string Admin = "admin.producto@" + Domain;
    public const string Patricia = "patricia.direccion@" + Domain;
    public const string Daniela = "daniela.jefa@" + Domain;

    private int _dayCounter;
    private int _employeeCounter;

    public string DataRoot { get; } = Path.Combine(Path.GetTempPath(), $"tf-tests-{Guid.NewGuid():N}");

    public IReadOnlyDictionary<string, string?> Settings => new Dictionary<string, string?>
    {
        ["TimeFlow:Mode"] = "Demo",
        ["TimeFlow:DataRoot"] = DataRoot,
        ["TimeFlow:PublicBaseUrl"] = "https://localhost",
        ["Database:Provider"] = "Sqlite",
        ["Database:AutoMigrate"] = "true",
        ["Demo:SyntheticEmployees"] = "12",
        ["Demo:SeedSampleRequests"] = "false",
        ["Email:Provider"] = "Mock",
        ["Email:ProcessorEnabled"] = "false",
        ["Authentication:Mode"] = "LocalDemo",
        ["RateLimiting:LoginPermitsPerMinute"] = "1000",
        ["RateLimiting:ApiPermitsPerMinute"] = "100000",
        ["Serilog:MinimumLevel:Default"] = "Warning",
    };

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        Directory.CreateDirectory(DataRoot);
        // UseSetting: disponible desde el inicio de Program (se lee antes de Build); AddInMemoryCollection: máxima prioridad.
        foreach (var (key, value) in Settings) builder.UseSetting(key, value);
        builder.ConfigureAppConfiguration(c => c.AddInMemoryCollection(Settings));
    }

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        if (!disposing) return;
        SqliteConnection.ClearAllPools();
        try { Directory.Delete(DataRoot, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }

    // ── Utilidades ──────────────────────────────────────────────────────────

    public static DateOnly TodayMexico =>
        DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, TimeZoneInfo.FindSystemTimeZoneById("America/Mexico_City")));

    /// <summary>Fecha única por llamada (futuro cercano) para evitar traslapes entre pruebas de la misma clase.</summary>
    public DateOnly NextOvertimeDate() => TodayMexico.AddDays(2 + Interlocked.Increment(ref _dayCounter));

    public static RequestInput Overtime(DateOnly date, int startHour = 18, int hours = 2) => new()
    {
        Kind = RequestKind.Overtime, StartDate = date, StartTime = new TimeOnly(startHour, 0), EndTime = new TimeOnly((startHour + hours) % 24, 0),
        Reason = "Cierre de entregables del sprint", Project = "Plataforma de configuración", Activity = "Pruebas de regresión y documentación"
    };

    public TimeFlowApiClient Anonymous() => new(CreateClient());

    public async Task<TimeFlowApiClient> LoginAsync(string email)
    {
        var client = new TimeFlowApiClient(CreateClient());
        var login = await client.LoginAsync(new LoginRequest { Email = email, Password = Password });
        client.SetToken(login.AccessToken);
        return client;
    }

    /// <summary>
    /// Varios clientes HTTP independientes (p. ej. pestañas o dispositivos) con la misma sesión. Se inicia sesión una sola vez:
    /// los inicios de sesión simultáneos de una misma cuenta fallan con 500 (ver AuthenticationTests, BUG documentado).
    /// </summary>
    public async Task<TimeFlowApiClient[]> SessionsAsync(string email, int count)
    {
        var first = await LoginAsync(email);
        var token = first.Http.DefaultRequestHeaders.Authorization!.Parameter;
        return [first, .. Enumerable.Range(1, count - 1).Select(_ => { var c = new TimeFlowApiClient(CreateClient()); c.SetToken(token); return c; })];
    }

    public async Task<T> WithDbAsync<T>(Func<ITimeFlowDbContext, Task<T>> work)
    {
        await using var scope = Services.CreateAsyncScope();
        return await work(scope.ServiceProvider.GetRequiredService<ITimeFlowDbContext>());
    }

    public Task<int> EmployeeIdAsync(string email) =>
        WithDbAsync(db => db.Employees.Where(e => e.NormalizedEmail == email).Select(e => e.Id).SingleAsync());

    /// <summary>Crea un empleado nuevo vía la API de administración (contraseña DEMO) y devuelve su correo.</summary>
    public async Task<string> CreateEmployeeAsync(string? supervisorEmail = Daniela, string? managerEmail = Patricia, UserRole roles = UserRole.Employee)
    {
        var n = Interlocked.Increment(ref _employeeCounter);
        var tag = Guid.NewGuid().ToString("N")[..6];
        var email = $"prueba.{tag}{n}@{Domain}";
        var admin = await LoginAsync(Admin);
        var department = await WithDbAsync(db => db.Departments.Where(d => d.Code == "PROD").Select(d => d.Id).SingleAsync());
        var input = new EmployeeInput
        {
            EmployeeNumber = $"T-{tag}{n}".ToUpperInvariant(), FullName = $"Persona Prueba {tag}", Email = email, DepartmentId = department,
            SupervisorId = supervisorEmail is null ? null : await EmployeeIdAsync(supervisorEmail),
            ManagerId = managerEmail is null ? null : await EmployeeIdAsync(managerEmail),
            Roles = roles, HireDate = TodayMexico.AddYears(-2)
        };
        using var response = await admin.Http.PostAsJsonAsync("api/v1/admin/employees", input, TimeFlowJson.Options);
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return email;
    }
}
