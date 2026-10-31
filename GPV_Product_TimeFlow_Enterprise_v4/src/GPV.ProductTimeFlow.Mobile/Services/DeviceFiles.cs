using Microsoft.Extensions.Logging;
using Microsoft.Maui.ApplicationModel;
using Microsoft.Maui.Devices;
using Microsoft.Maui.Storage;

namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>Archivo elegido por el usuario, ya validado (extensión y tamaño) y leído en memoria.</summary>
public sealed record PickedFile(string FileName, string ContentType, byte[] Content);

/// <summary>Acceso a archivos del dispositivo: selector de adjuntos y apertura de PDF/adjuntos descargados.</summary>
public sealed class DeviceFiles(ILogger<DeviceFiles> logger)
{
    /// <summary>Mismo límite que la API (TimeFlowOptions.MaxAttachmentBytes).</summary>
    public const long MaxAttachmentBytes = 10 * 1024 * 1024;

    /// <summary>Mismas extensiones que acepta la API (WorkflowService.AllowedExtensions).</summary>
    public static readonly IReadOnlyDictionary<string, string> AllowedTypes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        [".pdf"] = "application/pdf",
        [".png"] = "image/png",
        [".jpg"] = "image/jpeg",
        [".jpeg"] = "image/jpeg",
        [".docx"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        [".xlsx"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    };

    public const string AllowedTypesLabel = "PDF, PNG, JPG, DOCX o XLSX · máximo 10 MB";

    private static readonly FilePickerFileType PickerTypes = new(new Dictionary<DevicePlatform, IEnumerable<string>>
    {
        [DevicePlatform.Android] = AllowedTypes.Values.Distinct().ToArray(),
        [DevicePlatform.iOS] =
        [
            "com.adobe.pdf", "public.png", "public.jpeg",
            "org.openxmlformats.wordprocessingml.document", "org.openxmlformats.spreadsheetml.sheet",
        ],
        [DevicePlatform.WinUI] = AllowedTypes.Keys.ToArray(),
    });

    /// <summary>
    /// Abre el selector del sistema. Devuelve null si el usuario canceló.
    /// Lanza <see cref="UserFacingException"/> con un mensaje en español si el archivo no es válido.
    /// </summary>
    public async Task<PickedFile?> PickAttachmentAsync(CancellationToken ct = default)
    {
        var result = await FilePicker.Default.PickAsync(new PickOptions { PickerTitle = "Selecciona un archivo", FileTypes = PickerTypes });
        if (result is null) return null;

        var extension = Path.GetExtension(result.FileName);
        if (!AllowedTypes.TryGetValue(extension, out var contentType))
            throw new UserFacingException($"Tipo de archivo no permitido. Usa {AllowedTypesLabel}.");

        // Se copia a memoria con límite: en Android el stream del ContentResolver no siempre expone Length.
        await using var source = await result.OpenReadAsync();
        using var buffer = new MemoryStream();
        var chunk = new byte[81920];
        int read;
        while ((read = await source.ReadAsync(chunk, ct)) > 0)
        {
            if (buffer.Length + read > MaxAttachmentBytes)
                throw new UserFacingException("El archivo supera el máximo permitido de 10 MB.");
            buffer.Write(chunk, 0, read);
        }
        if (buffer.Length == 0) throw new UserFacingException("El archivo está vacío.");

        return new PickedFile(result.FileName, contentType, buffer.ToArray());
    }

    /// <summary>Guarda el archivo en la caché de la app y lo abre con el visor del sistema.</summary>
    public async Task OpenAsync(byte[] content, string fileName, string contentType, CancellationToken ct = default)
    {
        var safeName = string.Concat(fileName.Select(c => Path.GetInvalidFileNameChars().Contains(c) || c is '/' or '\\' ? '_' : c));
        if (string.IsNullOrWhiteSpace(safeName)) safeName = "documento";
        var folder = Path.Combine(FileSystem.Current.CacheDirectory, "documentos");
        Directory.CreateDirectory(folder);
        var path = Path.Combine(folder, safeName);
        await File.WriteAllBytesAsync(path, content, ct);
        logger.LogDebug("Documento guardado en caché: {File}", safeName);

        await MainThread.InvokeOnMainThreadAsync(() =>
            Launcher.Default.OpenAsync(new OpenFileRequest(safeName, new ReadOnlyFile(path, contentType))));
    }

    public static string ContentTypeFor(string fileName) =>
        AllowedTypes.TryGetValue(Path.GetExtension(fileName), out var type) ? type : "application/octet-stream";
}
