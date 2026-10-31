using System.Net;
using System.Text.Json;
using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>
/// Endpoints que YA existen en la API (Endpoints.cs) pero que todavía no expone <see cref="TimeFlowApiClient"/>
/// en GPV.ProductTimeFlow.Shared. Usan el mismo HttpClient (BaseAddress + JWT) y traducen errores a <see cref="ApiException"/>.
/// Pendiente: moverlos a TimeFlowApiClient y eliminar esta clase.
/// </summary>
public static class TimeFlowApiClientExtensions
{
    /// <summary>POST api/v1/notifications/read-all</summary>
    public static async Task MarkAllNotificationsReadAsync(this TimeFlowApiClient client, CancellationToken ct = default)
    {
        using var response = await client.Http.PostAsync("api/v1/notifications/read-all", content: null, ct);
        await EnsureAsync(response, ct);
    }

    /// <summary>DELETE api/v1/requests/{id}/attachments/{attachmentId}</summary>
    public static async Task RemoveAttachmentAsync(this TimeFlowApiClient client, Guid requestId, Guid attachmentId, CancellationToken ct = default)
    {
        using var response = await client.Http.DeleteAsync($"api/v1/requests/{requestId}/attachments/{attachmentId}", ct);
        await EnsureAsync(response, ct);
    }

    private static async Task EnsureAsync(HttpResponseMessage response, CancellationToken ct)
    {
        if (response.IsSuccessStatusCode) return;
        var message = $"Error {(int)response.StatusCode}";
        var errors = new List<string>();
        try
        {
            using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync(ct));
            if (doc.RootElement.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.String) message = d.GetString()!;
            if (doc.RootElement.TryGetProperty("errors", out var e) && e.ValueKind == JsonValueKind.Array)
                errors.AddRange(e.EnumerateArray().Select(x => x.GetString() ?? ""));
        }
        catch (JsonException) { }
        if (response.StatusCode == HttpStatusCode.Unauthorized) message = "Tu sesión expiró. Inicia sesión de nuevo.";
        throw new ApiException(response.StatusCode, message, errors.Count > 0 ? errors : [message]);
    }
}
