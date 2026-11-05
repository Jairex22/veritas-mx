using System.Text.Json.Nodes;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;
using Gpv.Sqi.OData;

namespace Gpv.Sqi.Demo;

/// <summary>
/// Fuente de DEMOSTRACIÓN con la misma interfaz que el cliente real. Todas las respuestas llevan data_source="demo".
/// - Caso histórico Mirion W07632100028 (evidencia confirmada por GPV, no producción actual).
/// - Eventos sintéticos relativos a la hora actual con nombres "DEMO".
/// - Inyección de fallos: DEMO-ERR-401, DEMO-ERR-403, DEMO-ERR-500, DEMO-TIMEOUT, DEMO-INVALID-JSON,
///   DEMO-QH-FAIL (SMT y Quality responden, QualityHistory agota el tiempo).
/// </summary>
public sealed class DemoDataSource : IDataSource
{
    public const string QhFailDefect = "dead0000-0000-4000-8000-0000000000fa";

    private static readonly Dictionary<string, (ODataStatus Status, int? Http, string Message)> Faults = new()
    {
        ["DEMO-ERR-401"] = (ODataStatus.AUTH_ERROR, 401, "HTTP 401 simulado"),
        ["DEMO-ERR-403"] = (ODataStatus.FORBIDDEN, 403, "HTTP 403 simulado"),
        ["DEMO-ERR-500"] = (ODataStatus.SERVER_ERROR, 500, "HTTP 500 simulado"),
        ["DEMO-TIMEOUT"] = (ODataStatus.TIMEOUT, null, "Timeout simulado"),
        ["DEMO-INVALID-JSON"] = (ODataStatus.INVALID_RESPONSE, 200, "JSON inválido simulado"),
    };

    private readonly object _gate = new();
    private readonly int _seed;
    private readonly DateTimeOffset? _fixedNow;
    private readonly string _fixturesDir;
    private DateTimeOffset? _generatedFor;
    private Dictionary<string, List<JsonObject>> _synthetic = new();
    public Dictionary<string, List<JsonObject>> Fixtures { get; }
    public Dictionary<string, object?>? LastMetadataStatus { get; private set; }

    public DemoDataSource(string? fixturesDir = null, int seed = 4821, DateTimeOffset? now = null)
    {
        _fixturesDir = fixturesDir ?? Path.Combine(AppContext.BaseDirectory, "fixtures");
        _seed = seed;
        _fixedNow = now;
        Fixtures = new()
        {
            ["SMT"] = Load("mirion_W07632100028_smt.json"),
            ["Quality"] = Load("mirion_W07632100028_quality.json"),
            ["QualityHistory"] = Load("mirion_W07632100028_quality_history.json"),
        };
    }

    private List<JsonObject> Load(string name) => Json.ParseRows(File.ReadAllText(Path.Combine(_fixturesDir, name)));

    // ------------------------------------------------------------ datos sintéticos
    private DateTimeOffset Now() => _fixedNow ?? DateTimeOffset.UtcNow;

    private void EnsureSynthetic()
    {
        var now = Now();
        now = new DateTimeOffset(now.Year, now.Month, now.Day, now.Hour, now.Minute, 0, now.Offset);
        lock (_gate)
        {
            if (_generatedFor is { } g && Math.Abs((now - g).TotalSeconds) < 600) return;
            _synthetic = Generate(now);
            _generatedFor = now;
        }
    }

    private Dictionary<string, List<JsonObject>> Generate(DateTimeOffset now)
    {
        var rnd = new Random(_seed);
        var tz = TimeSpan.FromHours(-6);
        (string Cust, string Asm, string Batch)[] customers =
            [("DEMO Cliente A", "DEMO-ASM-100", "DEMO-B100"), ("DEMO Cliente B", "DEMO-ASM-200", "DEMO-B200"), ("DEMO Cliente C", "DEMO-ASM-300", "DEMO-B300")];
        string[] flow = ["SMT Solder Paste Inspection", "SMT Pick and Place", "SMT Post-Reflow AOI Top", "QA SMT"];
        string[] defectTypes = ["Insufficient Solder", "Tombstone", "Bridging"];
        var smt = new List<JsonObject>(); var quality = new List<JsonObject>(); var history = new List<JsonObject>();
        static string Iso(DateTimeOffset d, TimeSpan tz) => TimeParse.Iso(d.ToOffset(tz));

        for (var i = 1; i <= 60; i++)
        {
            var (cust, asm, batch) = customers[i % 3];
            var ident = $"DEMO-{i:00000}";
            var t = now.AddMinutes(-rnd.Next(1, 171));
            var defect = i % 9 == 0;
            var ops = defect ? flow[..3].Concat(["SMT REPAIR", "SMT Post-Reflow AOI Top", "QA SMT"]).ToArray() : flow;
            for (var j = 0; j < ops.Length; j++)
            {
                smt.Add(new JsonObject
                {
                    ["Customer"] = cust, ["Assembly"] = asm, ["AssemblyRevision"] = asm + "$$A",
                    ["AssemblyDescription"] = "Ensamble de demostración", ["Process"] = "DEMO Process", ["ProcessRevision"] = "1",
                    ["WorkOrder"] = "DEMO-WO-" + batch[^3..], ["Batch"] = batch, ["OperationName"] = ops[j], ["Attempts"] = null,
                    ["Placements"] = null, ["Identifier"] = ident, ["EventDate"] = Iso(t.AddMinutes(2 * j), tz),
                    ["ODataKey"] = Entities.EmptyGuid,
                });
            }
            if (!defect) continue;
            var did = $"d3a0{i:0000}-0000-4000-8000-{i:000000000000}";
            var created = t.AddMinutes(4);
            var status = i % 18 == 0 ? "Open" : "Closed";
            var q = new JsonObject();
            foreach (var k in Entities.Quality.Keys) q[k] = null;
            q["CustomerName"] = cust; q["Assembly"] = asm; q["BatchName"] = batch; q["Identifier"] = ident; q["DefectID"] = did;
            q["DefectStatus"] = status; q["SourceOperation"] = "SMT Post-Reflow AOI Top";
            q["AegisInspectionCodeName"] = defectTypes[rnd.Next(defectTypes.Length)]; q["AegisCategoryName"] = "DEMO Categoría";
            q["DefectReference"] = $"R{rnd.Next(1, 100)}"; q["DefectComment"] = "Defecto de demostración"; q["Line"] = "DEMO Line 1";
            q["DateCreated"] = Iso(created, tz); q["ODataKey"] = Entities.EmptyGuid;
            quality.Add(q);
            JsonObject Hist(string time, string st, string op)
            {
                var h = new JsonObject();
                foreach (var k in Entities.QualityHistory.Keys) h[k] = null;
                h["Identifier"] = ident; h["DefectID"] = did; h["Batch"] = batch; h["Assembly"] = asm;
                h["DateCreated"] = Iso(created, tz); h["SourceOperation"] = "SMT Post-Reflow AOI Top"; h["ODataKey"] = Entities.EmptyGuid;
                h["DefectHistoryTime"] = time; h["DefectHistoryStatus"] = st; h["DefectHistoryOperation"] = op;
                return h;
            }
            history.Add(Hist(Iso(created, tz), "Open", "SMT Post-Reflow AOI Top"));
            if (status == "Closed")
            {
                var h = Hist(Iso(created.AddMinutes(3), tz), "Closed", "SMT REPAIR");
                h["DefectHistoryWorkstation"] = "DEMO-REPAIR-01"; h["DefectHistoryOperator"] = "DEMO-OP";
                history.Add(h);
            }
        }
        return new() { ["SMT"] = smt, ["Quality"] = quality, ["QualityHistory"] = history };
    }

    // ------------------------------------------------------------ interfaz
    public QueryResult? PolicyCheck(string entity) => null;

    public Task<(QueryResult Result, ODataMetadata? Metadata)> FetchMetadataAsync(CancellationToken ct = default)
    {
        var meta = MetadataParser.Parse(File.ReadAllBytes(Path.Combine(_fixturesDir, "metadata_sample.xml")));
        var res = new QueryResult(ODataStatus.OK, "$metadata")
        {
            HttpStatus = 200, ElapsedMs = 3.0, Attempts = 1, QueryDescription = "$metadata (muestra local)", DataSource = "demo",
            FetchedAt = TimeParse.NowUtcIso(),
        };
        LastMetadataStatus = res.ToStatusDict();
        return Task.FromResult<(QueryResult, ODataMetadata?)>((res, meta));
    }

    private static bool Match(JsonObject row, Filter f)
    {
        if (f.Op == "in" && f.Value is IReadOnlyList<string> list) return list.Any(v => Match(row, new Filter(f.Field, "eq", v)));
        var raw = row.Str(f.Field);
        int cmp;
        if (f.Value is DateTimeOffset target)
        {
            var dt = TimeParse.Parse(raw);
            if (dt is null) return false;
            cmp = dt.Value.Value.CompareTo(target);
        }
        else
        {
            if (raw is null) return f.Op == "ne";
            var a = raw; var b = Convert.ToString(f.Value) ?? "";
            if (f.Field is "DefectID" or "ODataKey") { a = a.ToLowerInvariant(); b = b.ToLowerInvariant(); }
            cmp = string.CompareOrdinal(a, b);
        }
        return f.Op switch { "eq" => cmp == 0, "ne" => cmp != 0, "ge" => cmp >= 0, "gt" => cmp > 0, "le" => cmp <= 0, "lt" => cmp < 0, _ => false };
    }

    public Task<QueryResult> ExecuteAsync(QuerySpec spec, CancellationToken ct = default)
    {
        var desc = spec.Describe() + " | DEMO";
        if (!Entities.Known.ContainsKey(spec.Entity))
            return Task.FromResult(new QueryResult(ODataStatus.VALIDATION_ERROR, spec.Entity) { Error = "Entidad no autorizada", QueryDescription = desc, DataSource = "demo" });

        var ident = spec.Filters.FirstOrDefault(f => f.Field == "Identifier" && f.Op == "eq")?.Value as string;
        if (ident is not null && Faults.TryGetValue(ident, out var fault))
            return Task.FromResult(new QueryResult(fault.Status, spec.Entity)
            {
                HttpStatus = fault.Http, Error = fault.Message, Attempts = 1, QueryDescription = desc,
                ElapsedMs = fault.Status == ODataStatus.TIMEOUT ? 10000.0 : 25.0, DataSource = "demo",
            });
        var defectIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var f in spec.Filters.Where(f => f.Field == "DefectID"))
        {
            if (f.Value is IReadOnlyList<string> l) defectIds.UnionWith(l);
            else if (f.Value is string s) defectIds.Add(s);
        }
        if (spec.Entity == "QualityHistory" && defectIds.Contains(QhFailDefect))
            return Task.FromResult(new QueryResult(ODataStatus.TIMEOUT, spec.Entity)
            { Error = "Timeout simulado en QualityHistory", Attempts = 1, ElapsedMs = 10000.0, QueryDescription = desc, DataSource = "demo" });

        EnsureSynthetic();
        // El caso histórico solo aparece en búsquedas por unidad/defecto/batch, nunca en ventanas temporales.
        var targeted = spec.Filters.Any(f => f.Field is "Identifier" or "DefectID" or "Batch" or "BatchName");
        IEnumerable<JsonObject> rows;
        lock (_gate) rows = _synthetic.GetValueOrDefault(spec.Entity, []).ToList();
        if (targeted)
        {
            rows = Fixtures[spec.Entity].Concat(rows);
            if (spec.Entity is "SMT" or "Quality")
            {
                rows = rows.Concat(Fixtures[spec.Entity].Select(r =>
                {
                    var c = r.Clone();
                    c["Identifier"] = "DEMO-QH-FAIL";
                    if (c.ContainsKey("DefectID")) c["DefectID"] = QhFailDefect;
                    return c;
                }));
            }
        }
        foreach (var f in spec.Filters) { var ff = f; rows = rows.Where(r => Match(r, ff)); }
        var list = rows.ToList();
        foreach (var (fld, dir) in Enumerable.Reverse(spec.OrderBy))
        {
            var isDate = fld == Entities.DateField.GetValueOrDefault(spec.Entity) || fld.EndsWith("Time") || fld.EndsWith("Date");
            list = isDate
                ? (dir == "desc"
                    ? list.OrderByDescending(r => TimeParse.Parse(r.Str(fld))?.Value ?? DateTimeOffset.MinValue).ToList()
                    : list.OrderBy(r => TimeParse.Parse(r.Str(fld))?.Value ?? DateTimeOffset.MinValue).ToList())
                : (dir == "desc"
                    ? list.OrderByDescending(r => r.Str(fld) ?? "", StringComparer.Ordinal).ToList()
                    : list.OrderBy(r => r.Str(fld) ?? "", StringComparer.Ordinal).ToList());
        }
        var truncated = list.Count > spec.Top;
        var outRows = list.Take(spec.Top).Select(r => r.Clone()).ToList();
        return Task.FromResult(new QueryResult(outRows.Count > 0 ? ODataStatus.OK : ODataStatus.EMPTY, spec.Entity)
        {
            Rows = outRows, HttpStatus = 200, ElapsedMs = new Random(desc.Length).Next(40, 301), Attempts = 1,
            Timings = new() { ["wait_headers_ms"] = 0, ["download_ms"] = 0, ["parse_ms"] = 0 },
            QueryDescription = desc, DataSource = "demo", Truncated = truncated, FetchedAt = TimeParse.NowUtcIso(),
        });
    }
}
