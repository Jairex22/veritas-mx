using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace GPV.ProductTimeFlow.Shared;

/// <summary>Opciones JSON comunes a la API y sus clientes (enums como texto).</summary>
public static class TimeFlowJson
{
    public static JsonSerializerOptions Options { get; } = Create();

    public static JsonSerializerOptions Create()
    {
        var o = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        o.Converters.Add(new JsonStringEnumConverter());
        return o;
    }
}

public sealed class ApiException(HttpStatusCode status, string message, IReadOnlyList<string> errors) : Exception(message)
{
    public HttpStatusCode Status { get; } = status;
    public IReadOnlyList<string> Errors { get; } = errors;
}

/// <summary>
/// Cliente tipado de la API REST de TimeFlow. Lo usa la app móvil (.NET MAUI) y las pruebas de integración,
/// así ambos ejercitan exactamente el mismo contrato.
/// </summary>
public sealed class TimeFlowApiClient(HttpClient http)
{
    private static readonly JsonSerializerOptions Json = TimeFlowJson.Options;

    public HttpClient Http => http;

    public void SetToken(string? token) =>
        http.DefaultRequestHeaders.Authorization = token is null ? null : new AuthenticationHeaderValue("Bearer", token);

    public Task<LoginResponse> LoginAsync(LoginRequest request, CancellationToken ct = default) => Post<LoginResponse>("api/v1/auth/login", request, ct);
    public Task<UserProfileDto> MeAsync(CancellationToken ct = default) => Get<UserProfileDto>("api/v1/me", ct);
    public Task<DashboardDto> DashboardAsync(CancellationToken ct = default) => Get<DashboardDto>("api/v1/dashboard", ct);

    public Task<PagedResult<RequestSummaryDto>> ListRequestsAsync(RequestQuery q, CancellationToken ct = default)
    {
        var qs = new List<string> { $"scope={q.Scope}", $"page={q.Page}", $"pageSize={q.PageSize}" };
        if (q.Status is not null) qs.Add($"status={q.Status}");
        if (q.Kind is not null) qs.Add($"kind={q.Kind}");
        if (q.From is not null) qs.Add($"from={q.From:yyyy-MM-dd}");
        if (q.To is not null) qs.Add($"to={q.To:yyyy-MM-dd}");
        if (q.EmployeeId is not null) qs.Add($"employeeId={q.EmployeeId}");
        if (!string.IsNullOrWhiteSpace(q.Search)) qs.Add($"search={Uri.EscapeDataString(q.Search)}");
        if (!string.IsNullOrWhiteSpace(q.Bucket)) qs.Add($"bucket={q.Bucket}");
        return Get<PagedResult<RequestSummaryDto>>("api/v1/requests?" + string.Join('&', qs), ct);
    }

    public Task<RequestDetailDto> GetRequestAsync(Guid id, CancellationToken ct = default) => Get<RequestDetailDto>($"api/v1/requests/{id}", ct);
    public Task<RequestDetailDto> CreateRequestAsync(RequestInput input, CancellationToken ct = default) => Post<RequestDetailDto>("api/v1/requests", input, ct);
    public Task<RequestDetailDto> UpdateRequestAsync(Guid id, RequestInput input, CancellationToken ct = default) => Send<RequestDetailDto>(HttpMethod.Put, $"api/v1/requests/{id}", input, ct);
    public Task<WorkflowResultDto> SubmitAsync(Guid id, SubmitInput input, CancellationToken ct = default) => Post<WorkflowResultDto>($"api/v1/requests/{id}/submit", input, ct);
    public Task<WorkflowResultDto> DecideAsync(Guid id, DecisionInput input, CancellationToken ct = default) => Post<WorkflowResultDto>($"api/v1/requests/{id}/decision", input, ct);
    public Task<WorkflowResultDto> AdministrativeAsync(Guid id, AdministrativeInput input, CancellationToken ct = default) => Post<WorkflowResultDto>($"api/v1/requests/{id}/administrative", input, ct);
    public Task<WorkflowResultDto> CancelAsync(Guid id, CancelInput input, CancellationToken ct = default) => Post<WorkflowResultDto>($"api/v1/requests/{id}/cancel", input, ct);

    public async Task<AttachmentDto> UploadAttachmentAsync(Guid id, Stream content, string fileName, string contentType, CancellationToken ct = default)
    {
        using var form = new MultipartFormDataContent();
        var file = new StreamContent(content);
        file.Headers.ContentType = new MediaTypeHeaderValue(contentType);
        form.Add(file, "file", fileName);
        using var response = await http.PostAsync($"api/v1/requests/{id}/attachments", form, ct);
        return await Read<AttachmentDto>(response, ct);
    }

    public Task<byte[]> DownloadPdfAsync(Guid id, CancellationToken ct = default) => Bytes($"api/v1/requests/{id}/pdf", ct);
    public Task<byte[]> DownloadAttachmentAsync(Guid attachmentId, CancellationToken ct = default) => Bytes($"api/v1/attachments/{attachmentId}", ct);

    public Task<byte[]> ExportExcelAsync(ExportFilter f, CancellationToken ct = default)
    {
        var qs = new List<string> { $"set={f.Set}" };
        if (f.Kind is not null) qs.Add($"kind={f.Kind}");
        if (f.EmployeeId is not null) qs.Add($"employeeId={f.EmployeeId}");
        if (f.From is not null) qs.Add($"from={f.From:yyyy-MM-dd}");
        if (f.To is not null) qs.Add($"to={f.To:yyyy-MM-dd}");
        return Bytes("api/v1/exports/requests.xlsx?" + string.Join('&', qs), ct);
    }

    public Task<VacationBalanceDto> VacationBalanceAsync(CancellationToken ct = default) => Get<VacationBalanceDto>("api/v1/vacations/balance", ct);
    public Task<VacationPreviewDto> VacationPreviewAsync(VacationPreviewRequest r, CancellationToken ct = default) => Post<VacationPreviewDto>("api/v1/vacations/preview", r, ct);
    public Task<OvertimePreviewDto> OvertimePreviewAsync(OvertimePreviewRequest r, CancellationToken ct = default) => Post<OvertimePreviewDto>("api/v1/overtime/preview", r, ct);
    public Task<OvertimeMonthlySummaryDto> OvertimeSummaryAsync(int year, int month, CancellationToken ct = default) => Get<OvertimeMonthlySummaryDto>($"api/v1/overtime/summary?year={year}&month={month}", ct);
    public Task<IReadOnlyList<CalendarEventDto>> CalendarAsync(DateOnly from, DateOnly to, CalendarScope scope, CancellationToken ct = default) =>
        Get<IReadOnlyList<CalendarEventDto>>($"api/v1/calendar?from={from:yyyy-MM-dd}&to={to:yyyy-MM-dd}&scope={scope}", ct);
    public Task<IReadOnlyList<LeaveCategoryDto>> LeaveCategoriesAsync(RequestKind kind, CancellationToken ct = default) => Get<IReadOnlyList<LeaveCategoryDto>>($"api/v1/catalogs/leave-categories?kind={kind}", ct);
    public Task<PagedResult<NotificationDto>> NotificationsAsync(bool unreadOnly = false, int page = 1, CancellationToken ct = default) =>
        Get<PagedResult<NotificationDto>>($"api/v1/notifications?unreadOnly={unreadOnly}&page={page}", ct);
    public Task<int> UnreadCountAsync(CancellationToken ct = default) => Get<int>("api/v1/notifications/unread-count", ct);
    public async Task MarkNotificationReadAsync(Guid id, CancellationToken ct = default) { using var r = await http.PostAsync($"api/v1/notifications/{id}/read", null, ct); await Ensure(r, ct); }

    // ── Infraestructura HTTP ──
    private async Task<T> Get<T>(string url, CancellationToken ct) { using var r = await http.GetAsync(url, ct); return await Read<T>(r, ct); }
    private Task<T> Post<T>(string url, object body, CancellationToken ct) => Send<T>(HttpMethod.Post, url, body, ct);
    private async Task<T> Send<T>(HttpMethod method, string url, object body, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(method, url) { Content = JsonContent.Create(body, body.GetType(), options: Json) };
        using var r = await http.SendAsync(req, ct);
        return await Read<T>(r, ct);
    }
    private async Task<byte[]> Bytes(string url, CancellationToken ct) { using var r = await http.GetAsync(url, ct); await Ensure(r, ct); return await r.Content.ReadAsByteArrayAsync(ct); }

    private static async Task<T> Read<T>(HttpResponseMessage r, CancellationToken ct)
    {
        await Ensure(r, ct);
        return (await r.Content.ReadFromJsonAsync<T>(Json, ct))!;
    }

    private static async Task Ensure(HttpResponseMessage r, CancellationToken ct)
    {
        if (r.IsSuccessStatusCode) return;
        string message = $"Error {(int)r.StatusCode}";
        var errors = new List<string>();
        try
        {
            using var doc = JsonDocument.Parse(await r.Content.ReadAsStringAsync(ct));
            if (doc.RootElement.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.String) message = d.GetString()!;
            if (doc.RootElement.TryGetProperty("errors", out var e) && e.ValueKind == JsonValueKind.Array) errors.AddRange(e.EnumerateArray().Select(x => x.GetString() ?? ""));
        }
        catch (JsonException) { }
        if (r.StatusCode == HttpStatusCode.Unauthorized) message = "Tu sesión expiró. Inicia sesión de nuevo.";
        throw new ApiException(r.StatusCode, message, errors.Count > 0 ? errors : [message]);
    }
}
