using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Gpv.Sqi.Config;

public sealed class ConfigException(string message) : Exception(message);

/// <summary>
/// Configuración. Precedencia: valores por defecto &lt; config.json &lt; ajustes guardados en SQLite
/// (solo claves de EditableKeys). Las banderas de seguridad solo se cambian en config.json.
/// </summary>
public sealed class AppConfig
{
    public const string AppVersion = "1.1.0";

    public const string DefaultsJson = """
    {
      "app": {"name": "GPV SMT Quality Intelligence", "site": "GPV Americas E-MXG", "display_utc_offset": "-06:00"},
      "server": {"host": "127.0.0.1", "port": 8765, "open_browser": true},
      "mode": "demo",
      "odata": {
        "base_url": "http://10.62.54.10:6065/odata/",
        "auth_method": "none",
        "credential_source": "env",
        "credential_target": "GPV_SMT_QI_FactoryLogix",
        "timeout_seconds": 10,
        "connect_timeout_seconds": 5,
        "max_concurrent_requests": 1,
        "max_retries": 0,
        "backoff_seconds": 2.0,
        "max_response_mb": 20,
        "max_pages": 1,
        "metadata_ttl_minutes": 1440,
        "use_select": true
      },
      "security": {"live_mode_approved": false, "allow_basic_auth_over_http": false},
      "protection": {"cooldown_seconds": 60, "result_cache_seconds": 60, "min_interval_ms": 1000},
      "pulse": {"auto_refresh_enabled": false, "refresh_interval_seconds": 300, "max_events": 200, "shifts": []},
      "quality": {"default_window_hours": 4, "max_defects": 200, "max_closetime_lookups": 10},
      "trace": {"max_smt_events": 100, "max_quality_rows": 50, "max_history_rows": 200},
      "rework": {"repair_keywords": ["REPAIR", "REWORK", "REPARACION", "REPARACIÓN"], "process_flows": {}, "max_batch_events": 500},
      "paths": {"database": "database/gpv_sqi.sqlite3", "logs": "logs"}
    }
    """;

    public static readonly Dictionary<string, string> EditableKeys = new()
    {
        ["mode"] = "str",
        ["odata.base_url"] = "str",
        ["odata.auth_method"] = "str",
        ["odata.credential_source"] = "str",
        ["odata.timeout_seconds"] = "float",
        ["odata.max_retries"] = "int",
        ["odata.backoff_seconds"] = "float",
        ["odata.max_concurrent_requests"] = "int",
        ["pulse.auto_refresh_enabled"] = "bool",
        ["pulse.refresh_interval_seconds"] = "int",
        ["pulse.max_events"] = "int",
        ["quality.default_window_hours"] = "int",
        ["rework.repair_keywords"] = "list",
        ["protection.cooldown_seconds"] = "int",
        ["protection.result_cache_seconds"] = "int",
        ["protection.min_interval_ms"] = "int",
    };

    private static readonly Dictionary<string, (double Lo, double Hi)> Limits = new()
    {
        ["odata.timeout_seconds"] = (1, 60),
        ["odata.max_retries"] = (0, 2),
        ["odata.backoff_seconds"] = (0.5, 30),
        ["odata.max_concurrent_requests"] = (1, 2),
        ["pulse.refresh_interval_seconds"] = (300, 3600),
        ["pulse.max_events"] = (10, 1000),
        ["quality.default_window_hours"] = (1, 168),
        ["protection.cooldown_seconds"] = (0, 600),
        ["protection.result_cache_seconds"] = (0, 600),
        ["protection.min_interval_ms"] = (0, 10000),
    };

    private static readonly Dictionary<string, string[]> Choices = new()
    {
        ["mode"] = ["demo", "live"],
        ["odata.auth_method"] = ["none", "basic"],
        ["odata.credential_source"] = ["env", "windows_credential_manager"],
    };

    public JsonObject Root { get; }
    /// <summary>Carpeta base para rutas relativas (base de datos, logs).</summary>
    public string BaseDirectory { get; init; } = AppContext.BaseDirectory;

    public AppConfig(JsonObject root) { Root = root; }

    public static AppConfig Defaults() => new(JsonNode.Parse(DefaultsJson)!.AsObject());

    public AppConfig Clone() => new(Root.DeepClone().AsObject()) { BaseDirectory = BaseDirectory };

    // ------------------------------------------------------------------ acceso
    public JsonNode? Node(string dotted)
    {
        JsonNode? cur = Root;
        foreach (var part in dotted.Split('.'))
        {
            if (cur is not JsonObject o || !o.TryGetPropertyValue(part, out cur)) return null;
        }
        return cur;
    }

    public string Str(string path) => Node(path)?.GetValue<object>()?.ToString() ?? "";
    public bool Bool(string path) => Node(path) is JsonValue v && v.TryGetValue<bool>(out var b) && b;
    public double Num(string path)
    {
        var n = Node(path);
        if (n is JsonValue v && TryNumber(v, out var d)) return d;
        throw new ConfigException($"{path}: se esperaba número");
    }
    public int Int(string path) => (int)Num(path);

    /// <summary>Número opcional: si la clave no existe (config.json antiguo) usa el valor por defecto.</summary>
    public double NumOr(string path, double fallback) => Node(path) is JsonValue v && TryNumber(v, out var d) ? d : fallback;
    public bool BoolOr(string path, bool fallback) => Node(path) is JsonValue v && v.TryGetValue<bool>(out var b) ? b : fallback;

    /// <summary>Lee un número de un JsonValue leído de JSON (JsonElement) o creado en memoria (int, long, double, decimal).</summary>
    public static bool TryNumber(JsonValue v, out double value)
    {
        value = 0;
        if (v.TryGetValue<bool>(out _)) return false;
        if (v.TryGetValue<double>(out var d)) { value = d; return true; }
        if (v.TryGetValue<int>(out var i)) { value = i; return true; }
        if (v.TryGetValue<long>(out var l)) { value = l; return true; }
        if (v.TryGetValue<decimal>(out var m)) { value = (double)m; return true; }
        if (v.TryGetValue<float>(out var f)) { value = f; return true; }
        if (v.TryGetValue<JsonElement>(out var el) && el.ValueKind == JsonValueKind.Number) { value = el.GetDouble(); return true; }
        return false;
    }
    public List<string> StrList(string path) => Node(path) is JsonArray a
        ? a.Select(x => x?.ToString() ?? "").Where(x => x.Length > 0).ToList() : [];
    public string Mode => Str("mode");

    public void Set(string dotted, JsonNode? value)
    {
        var parts = dotted.Split('.');
        var cur = Root;
        foreach (var p in parts[..^1])
        {
            if (cur[p] is not JsonObject next) { next = new JsonObject(); cur[p] = next; }
            cur = next;
        }
        cur[parts[^1]] = value?.DeepClone();
    }

    public Dictionary<string, List<string>> ProcessFlows() =>
        Node("rework.process_flows") is JsonObject o
            ? o.Where(kv => !kv.Key.StartsWith('_') && kv.Value is JsonArray)
               .ToDictionary(kv => kv.Key, kv => kv.Value!.AsArray().Select(x => x!.ToString()).ToList())
            : [];

    public string ResolvePath(string key)
    {
        var p = Str($"paths.{key}");
        return Path.IsPathRooted(p) ? p : Path.GetFullPath(Path.Combine(BaseDirectory, p));
    }

    // ------------------------------------------------------------------ carga
    public static JsonObject DeepMerge(JsonObject baseObj, JsonObject over)
    {
        var outObj = baseObj.DeepClone().AsObject();
        foreach (var (k, v) in over)
        {
            if (k.StartsWith('_')) continue;   // claves de comentario
            if (v is JsonObject vo && outObj[k] is JsonObject bo) outObj[k] = DeepMerge(bo, vo);
            else outObj[k] = v?.DeepClone();
        }
        return outObj;
    }

    public static AppConfig Load(string? path, string? baseDirectory = null)
    {
        var cfg = Defaults();
        var root = cfg.Root;
        if (path is not null && File.Exists(path))
        {
            JsonNode? user;
            try
            {
                user = JsonNode.Parse(File.ReadAllText(path), documentOptions: new JsonDocumentOptions { CommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true });
            }
            catch (Exception ex) when (ex is JsonException or IOException)
            {
                throw new ConfigException($"No se pudo leer {Path.GetFileName(path)}: {ex.Message}");
            }
            if (user is not JsonObject uo) throw new ConfigException($"{Path.GetFileName(path)} debe contener un objeto JSON");
            if (ContainsPasswordValue(uo))
                throw new ConfigException("config.json no debe contener contraseñas. Use variables de entorno o el Administrador de credenciales de Windows.");
            root = DeepMerge(root, uo);
        }
        return new AppConfig(root) { BaseDirectory = baseDirectory ?? (path is null ? AppContext.BaseDirectory : Path.GetDirectoryName(Path.GetFullPath(path))!) };
    }

    private static bool ContainsPasswordValue(JsonNode? node) => node switch
    {
        JsonObject o => o.Any(kv => (kv.Key.Contains("password", StringComparison.OrdinalIgnoreCase)
                                     && kv.Value is JsonValue v && v.TryGetValue<string>(out var s) && s.Length > 0)
                                    || ContainsPasswordValue(kv.Value)),
        JsonArray a => a.Any(ContainsPasswordValue),
        _ => false,
    };

    // ------------------------------------------------------------------ edición
    public static JsonNode ValidateSetting(string key, JsonNode? value)
    {
        if (!EditableKeys.TryGetValue(key, out var kind)) throw new ConfigException($"La clave {key} no es editable desde la interfaz");
        JsonNode result;
        var v = value as JsonValue;
        switch (kind)
        {
            case "bool":
                if (v is null || !v.TryGetValue<bool>(out var b)) throw new ConfigException($"{key}: se esperaba verdadero/falso");
                result = JsonValue.Create(b);
                break;
            case "int":
            case "float":
            {
                double d;
                if (v is null || v.TryGetValue<bool>(out _)) throw new ConfigException($"{key}: se esperaba número");
                if (TryNumber(v, out var dd)) d = dd;
                else if (v.TryGetValue<string>(out var s) && double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var ds)) d = ds;
                else throw new ConfigException($"{key}: valor inválido");
                if (kind == "int") d = Math.Truncate(d);
                CheckLimits(key, d);
                result = kind == "int" ? JsonValue.Create((int)d) : JsonValue.Create(d);
                break;
            }
            case "str":
            {
                if (v is null || !v.TryGetValue<string>(out var s)) throw new ConfigException($"{key}: se esperaba texto");
                s = s.Trim();
                if (Choices.TryGetValue(key, out var choices) && !choices.Contains(s))
                    throw new ConfigException($"{key}: valores permitidos ({string.Join(", ", choices)})");
                if (key == "odata.base_url")
                {
                    if (!(s.StartsWith("http://") || s.StartsWith("https://")) || s.Length > 300)
                        throw new ConfigException("La URL base debe iniciar con http:// o https://");
                    if (s.IndexOfAny(['?', '#', '@', ' ']) >= 0) throw new ConfigException("La URL base no puede contener ?, #, @ ni espacios");
                    if (!s.EndsWith('/')) s += "/";
                }
                result = JsonValue.Create(s);
                break;
            }
            case "list":
            {
                if (value is not JsonArray arr || arr.Any(x => x is not JsonValue xv || !xv.TryGetValue<string>(out _)))
                    throw new ConfigException($"{key}: se esperaba lista de textos");
                result = new JsonArray(arr.Select(x => x!.GetValue<string>().Trim()).Where(x => x.Length > 0).Take(20)
                    .Select(x => (JsonNode?)JsonValue.Create(x)).ToArray());
                break;
            }
            default: throw new ConfigException($"{key}: tipo desconocido");
        }
        return result;
    }

    private static void CheckLimits(string key, double d)
    {
        if (Limits.TryGetValue(key, out var lim) && (d < lim.Lo || d > lim.Hi))
            throw new ConfigException($"{key}: debe estar entre {Infrastructure.Json.Num(lim.Lo)} y {Infrastructure.Json.Num(lim.Hi)}");
    }

    public AppConfig WithOverrides(IReadOnlyDictionary<string, JsonNode?> overrides)
    {
        var copy = Clone();
        foreach (var (k, v) in overrides)
        {
            try { copy.Set(k, ValidateSetting(k, v)); }
            catch (ConfigException) { /* overrides inválidos u obsoletos se ignoran */ }
        }
        return copy;
    }

    /// <summary>Vista segura para la UI (sin secretos).</summary>
    public Dictionary<string, object?> PublicView() => new()
    {
        ["app"] = Node("app")?.DeepClone(),
        ["mode"] = Mode,
        ["odata"] = new JsonObject(new[] { "base_url", "auth_method", "credential_source", "timeout_seconds", "max_retries",
            "backoff_seconds", "max_concurrent_requests" }.Select(k => KeyValuePair.Create(k, Node($"odata.{k}")?.DeepClone()))),
        ["security"] = Node("security")?.DeepClone(),
        ["pulse"] = Node("pulse")?.DeepClone(),
        ["quality"] = Node("quality")?.DeepClone(),
        ["protection"] = Node("protection")?.DeepClone(),
        ["rework"] = new Dictionary<string, object?>
        {
            ["repair_keywords"] = StrList("rework.repair_keywords"),
            ["process_flows_configured"] = ProcessFlows().Keys.OrderBy(x => x, StringComparer.Ordinal).ToList(),
        },
        ["editable_keys"] = EditableKeys.Keys.OrderBy(x => x, StringComparer.Ordinal).ToList(),
        ["version"] = AppVersion,
    };
}
