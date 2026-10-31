using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using GPV.ProductTimeFlow.Shared;

// Uso: dotnet run --project tests/LoadTests -c Release -- <baseUrl> <usuariosVirtuales> <segundos> [pidApi]
// Ejemplo: dotnet run --project tests/LoadTests -c Release -- http://localhost:5201 200 120 12345
var baseUrl = args.Length > 0 ? args[0].TrimEnd('/') + "/" : "http://localhost:5201/";
var vus = args.Length > 1 ? int.Parse(args[1]) : 200;
var seconds = args.Length > 2 ? int.Parse(args[2]) : 60;
int? apiPid = args.Length > 3 ? int.Parse(args[3]) : null;
const string Password = "Demo#TimeFlow2026";

var handler = new SocketsHttpHandler { MaxConnectionsPerServer = 1000, PooledConnectionLifetime = TimeSpan.FromMinutes(5) };
var http = new HttpClient(handler) { BaseAddress = new Uri(baseUrl), Timeout = TimeSpan.FromSeconds(30) };
var samples = new ConcurrentDictionary<string, ConcurrentBag<double>>();
var errors = new ConcurrentDictionary<string, int>();
var resources = new ConcurrentBag<(double CpuPct, double RamMb)>();

void Record(string name, double ms, bool ok, string? reason = null)
{
    samples.GetOrAdd(name, _ => []).Add(ms);
    if (!ok) errors.AddOrUpdate($"{name}: {reason}", 1, (_, c) => c + 1);
}

async Task<HttpResponseMessage?> Timed(string name, Func<Task<HttpResponseMessage>> call)
{
    var sw = Stopwatch.StartNew();
    try
    {
        var r = await call();
        sw.Stop();
        var ok = (int)r.StatusCode < 500 && r.StatusCode != System.Net.HttpStatusCode.TooManyRequests;
        Record(name, sw.Elapsed.TotalMilliseconds, ok, ok ? null : ((int)r.StatusCode).ToString());
        return r;
    }
    catch (Exception ex) { sw.Stop(); Record(name, sw.Elapsed.TotalMilliseconds, false, ex.GetType().Name); return null; }
}

Console.WriteLine($"GPV Product TimeFlow · prueba de carga · {vus} usuarios virtuales · {seconds}s · {baseUrl}");

// Cuentas: el administrador DEMO obtiene la lista de empleados sintéticos (todas comparten la contraseña DEMO).
var adminLogin = await http.PostAsJsonAsync("api/v1/auth/login", new LoginRequest { Email = "admin.producto@demo.timeflow.example", Password = Password }, TimeFlowJson.Options);
adminLogin.EnsureSuccessStatusCode();
var admin = (await adminLogin.Content.ReadFromJsonAsync<LoginResponse>(TimeFlowJson.Options))!;
using var adminReq = new HttpRequestMessage(HttpMethod.Get, "api/v1/admin/employees?pageSize=200");
adminReq.Headers.Authorization = new AuthenticationHeaderValue("Bearer", admin.AccessToken);
var employees = (await (await http.SendAsync(adminReq)).Content.ReadFromJsonAsync<PagedResult<EmployeeDto>>(TimeFlowJson.Options))!.Items
    .Where(e => e.IsActive).Select(e => e.Email).ToList();
Console.WriteLine($"Cuentas disponibles: {employees.Count}");

// Fase 1: inicio de sesión concurrente
var tokens = new ConcurrentDictionary<int, string>();
await Parallel.ForEachAsync(Enumerable.Range(0, vus), new ParallelOptions { MaxDegreeOfParallelism = vus }, async (i, ct) =>
{
    var email = employees[i % employees.Count];
    var r = await Timed("POST /auth/login", () => http.PostAsJsonAsync("api/v1/auth/login", new LoginRequest { Email = email, Password = Password }, TimeFlowJson.Options, ct));
    if (r?.IsSuccessStatusCode == true) tokens[i] = (await r.Content.ReadFromJsonAsync<LoginResponse>(TimeFlowJson.Options, ct))!.AccessToken;
});
Console.WriteLine($"Sesiones iniciadas: {tokens.Count}/{vus}");

// Monitor de recursos del proceso de la API (si se proporcionó el PID)
using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(seconds));
var monitor = Task.Run(async () =>
{
    if (apiPid is null) return;
    var p = Process.GetProcessById(apiPid.Value);
    var lastCpu = p.TotalProcessorTime; var lastT = DateTime.UtcNow;
    while (!cts.IsCancellationRequested)
    {
        await Task.Delay(1000);
        p.Refresh();
        var cpu = p.TotalProcessorTime; var now = DateTime.UtcNow;
        resources.Add(((cpu - lastCpu).TotalMilliseconds / (now - lastT).TotalMilliseconds / Environment.ProcessorCount * 100, p.WorkingSet64 / 1024.0 / 1024.0));
        lastCpu = cpu; lastT = now;
    }
});

// Fase 2: mezcla de operaciones comunes durante N segundos (cada usuario espera 0.5–2 s entre acciones)
var total = Stopwatch.StartNew();
var today = DateOnly.FromDateTime(DateTime.Today);
await Parallel.ForEachAsync(tokens, new ParallelOptions { MaxDegreeOfParallelism = vus }, async (kv, _) =>
{
    var rnd = new Random(kv.Key);
    while (!cts.IsCancellationRequested)
    {
        HttpRequestMessage Req(HttpMethod m, string url, object? body = null)
        {
            var q = new HttpRequestMessage(m, url);
            q.Headers.Authorization = new AuthenticationHeaderValue("Bearer", kv.Value);
            if (body is not null) q.Content = JsonContent.Create(body, body.GetType(), options: TimeFlowJson.Options);
            return q;
        }
        var op = rnd.Next(100);
        (string Name, Func<HttpRequestMessage> Make) action = op switch
        {
            < 25 => ("GET /dashboard", () => Req(HttpMethod.Get, "api/v1/dashboard")),
            < 45 => ("GET /requests", () => Req(HttpMethod.Get, "api/v1/requests?scope=Mine&pageSize=20")),
            < 60 => ("GET /notifications", () => Req(HttpMethod.Get, "api/v1/notifications/unread-count")),
            < 72 => ("GET /calendar", () => Req(HttpMethod.Get, $"api/v1/calendar?from={today:yyyy-MM-01}&to={today.AddDays(30):yyyy-MM-dd}&scope=Team")),
            < 84 => ("GET /vacations/balance", () => Req(HttpMethod.Get, "api/v1/vacations/balance")),
            < 94 => ("POST /overtime/preview", () => Req(HttpMethod.Post, "api/v1/overtime/preview", new OvertimePreviewRequest { Date = today.AddDays(-rnd.Next(1, 20)), Start = new TimeOnly(18, 0), End = new TimeOnly(20, 0) })),
            _ => ("POST /requests (borrador)", () => Req(HttpMethod.Post, "api/v1/requests", new RequestInput
            {
                Kind = RequestKind.Overtime, StartDate = today.AddDays(-rnd.Next(1, 28)), StartTime = new TimeOnly(rnd.Next(0, 6), 0), EndTime = new TimeOnly(rnd.Next(0, 6), 30),
                Reason = "Carga sintética", Project = "Prueba de carga", Activity = "Operación generada por la prueba de carga."
            }))
        };
        using var resp = await Timed(action.Name, () => http.SendAsync(action.Make()));
        try { await Task.Delay(rnd.Next(500, 2000), cts.Token); } catch (TaskCanceledException) { }
    }
});
total.Stop();
await monitor;

// Fase 3: aprobaciones concurrentes (jefa directa) + intento de doble aprobación sobre las mismas solicitudes
var laura = (await (await http.PostAsJsonAsync("api/v1/auth/login", new LoginRequest { Email = "laura.jefa@demo.timeflow.example", Password = Password }, TimeFlowJson.Options))
    .Content.ReadFromJsonAsync<LoginResponse>(TimeFlowJson.Options))!.AccessToken;
var client = new TimeFlowApiClient(new HttpClient(handler, false) { BaseAddress = new Uri(baseUrl) });
client.SetToken(laura);
var inbox = await client.ListRequestsAsync(new RequestQuery { Scope = RequestScope.ApprovalInbox, PageSize = 50 });
var signature = Convert.ToBase64String(MinimalPng());
var doubleApprovals = 0;
await Parallel.ForEachAsync(inbox.Items, async (r, _) =>
{
    var tasks = Enumerable.Range(0, 2).Select(_ => Timed("POST /decision (aprobación)", () =>
    {
        var q = new HttpRequestMessage(HttpMethod.Post, $"api/v1/requests/{r.Id}/decision")
        {
            Content = JsonContent.Create(new DecisionInput { Decision = ApprovalDecisionType.Approve, ExpectedVersion = r.Version, SignatureConsent = true, SignaturePngBase64 = signature, IdempotencyKey = Guid.NewGuid().ToString("N") }, options: TimeFlowJson.Options)
        };
        q.Headers.Authorization = new AuthenticationHeaderValue("Bearer", laura);
        return http.SendAsync(q);
    })).ToList();
    var results = await Task.WhenAll(tasks);
    if (results.Count(x => x?.IsSuccessStatusCode == true) > 1) Interlocked.Increment(ref doubleApprovals);
});

// Informe
static double P(List<double> s, double p) => s.Count == 0 ? 0 : s[Math.Min(s.Count - 1, (int)Math.Ceiling(p / 100 * s.Count) - 1)];
var report = new System.Text.StringBuilder();
report.AppendLine($"## Resultado de carga · {DateTime.UtcNow:yyyy-MM-dd HH:mm} UTC");
report.AppendLine($"- Usuarios virtuales: {vus} · Duración fase mixta: {total.Elapsed.TotalSeconds:0} s · Destino: {baseUrl}");
report.AppendLine();
report.AppendLine("| Operación | Solicitudes | p50 (ms) | p95 (ms) | p99 (ms) | Máx (ms) |");
report.AppendLine("|---|---:|---:|---:|---:|---:|");
var all = new List<double>();
foreach (var (name, bag) in samples.OrderBy(k => k.Key))
{
    var s = bag.OrderBy(x => x).ToList();
    all.AddRange(s);
    report.AppendLine($"| {name} | {s.Count} | {P(s, 50):0} | {P(s, 95):0} | {P(s, 99):0} | {s.Last():0} |");
}
all.Sort();
var errorCount = errors.Values.Sum();
var mixed = samples.Where(k => !k.Key.Contains("login") && !k.Key.Contains("decision")).Sum(k => k.Value.Count);
report.AppendLine($"| **Total** | {all.Count} | {P(all, 50):0} | {P(all, 95):0} | {P(all, 99):0} | {(all.Count > 0 ? all[^1] : 0):0} |");
report.AppendLine();
report.AppendLine($"- Throughput fase mixta: {mixed / total.Elapsed.TotalSeconds:0.0} solicitudes/s");
report.AppendLine($"- Errores atribuibles a la aplicación (5xx, 429, timeouts): {errorCount} ({(all.Count == 0 ? 0 : errorCount * 100.0 / all.Count):0.00} %)");
foreach (var (k, v) in errors) report.AppendLine($"  - {k}: {v}");
report.AppendLine($"- Aprobaciones concurrentes: {inbox.Items.Count} solicitudes × 2 intentos simultáneos · dobles aprobaciones detectadas: {doubleApprovals}");
if (!resources.IsEmpty)
    report.AppendLine($"- Proceso API: CPU promedio {resources.Average(r => r.CpuPct):0.0} % (máx {resources.Max(r => r.CpuPct):0.0} %) de {Environment.ProcessorCount} núcleos · RAM máx {resources.Max(r => r.RamMb):0} MB");
Console.WriteLine(report);
File.WriteAllText($"load-result-{DateTime.UtcNow:yyyyMMddHHmm}.md", report.ToString());
return doubleApprovals == 0 ? 0 : 2;

static byte[] MinimalPng()
{
    // PNG gris 300x80 válido (mayor a 200 bytes) generado sin dependencias.
    var w = 300; var h = 80;
    var raw = new byte[(w + 1) * h];
    for (var y = 0; y < h; y++) for (var x = 0; x < w; x++) raw[y * (w + 1) + 1 + x] = (byte)(Math.Abs(y - 40 - 20 * Math.Sin(x / 15.0)) < 2 ? 20 : 255);
    using var z = new MemoryStream();
    using (var zs = new System.IO.Compression.ZLibStream(z, System.IO.Compression.CompressionLevel.Fastest, true)) zs.Write(raw);
    using var png = new MemoryStream();
    png.Write([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
    void Chunk(string t, byte[] d)
    {
        var len = BitConverter.GetBytes(d.Length); Array.Reverse(len); png.Write(len);
        var td = System.Text.Encoding.ASCII.GetBytes(t).Concat(d).ToArray(); png.Write(td);
        uint c = 0xFFFFFFFF; foreach (var b in td) { c ^= b; for (var k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1; }
        var crc = BitConverter.GetBytes(~c); Array.Reverse(crc); png.Write(crc);
    }
    var ihdr = new byte[13]; var wb = BitConverter.GetBytes(w); Array.Reverse(wb); var hb = BitConverter.GetBytes(h); Array.Reverse(hb);
    wb.CopyTo(ihdr, 0); hb.CopyTo(ihdr, 4); ihdr[8] = 8; ihdr[9] = 0;
    Chunk("IHDR", ihdr); Chunk("IDAT", z.ToArray()); Chunk("IEND", []);
    return png.ToArray();
}
