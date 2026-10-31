namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>
/// Lectura de parámetros de la URL. Se usa en lugar de [SupplyParameterFromQuery] para no depender de que
/// BlazorWebView registre su proveedor; Routes.razor recrea la página en cada cambio de URL (@key).
/// </summary>
public static class QueryString
{
    public static string? Get(string uri, string name)
    {
        var q = uri.IndexOf('?');
        if (q < 0) return null;
        var hash = uri.IndexOf('#', q);
        var query = hash < 0 ? uri[(q + 1)..] : uri[(q + 1)..hash];
        foreach (var pair in query.Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var eq = pair.IndexOf('=');
            var key = Uri.UnescapeDataString((eq < 0 ? pair : pair[..eq]).Replace('+', ' '));
            if (!key.Equals(name, StringComparison.OrdinalIgnoreCase)) continue;
            var value = eq < 0 ? "" : Uri.UnescapeDataString(pair[(eq + 1)..].Replace('+', ' '));
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }
        return null;
    }
}
