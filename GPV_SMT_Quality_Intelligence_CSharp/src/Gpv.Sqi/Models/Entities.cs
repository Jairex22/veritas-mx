namespace Gpv.Sqi.Models;

public sealed record PropertyInfo(string Name, string EdmType, bool Verified = true);

/// <summary>
/// Catálogo de entidades y propiedades conocidas de FactoryLogix OData. Los tipos con
/// Verified=false son supuestos de arranque; en modo real se usan los de $metadata.
/// </summary>
public static class Entities
{
    public const string EmptyGuid = "00000000-0000-0000-0000-000000000000";

    private static Dictionary<string, PropertyInfo> Props(params (string Name, string Type, bool Verified)[] items) =>
        items.ToDictionary(i => i.Name, i => new PropertyInfo(i.Name, i.Type, i.Verified));

    public static readonly Dictionary<string, PropertyInfo> Smt = Props(
        ("Customer", "Edm.String", true), ("Assembly", "Edm.String", true), ("AssemblyRevision", "Edm.String", true),
        ("AssemblyDescription", "Edm.String", true), ("Process", "Edm.String", true), ("ProcessRevision", "Edm.String", true),
        ("WorkOrder", "Edm.String", true), ("Batch", "Edm.String", true), ("OperationName", "Edm.String", true),
        ("Attempts", "Edm.Int32", true), ("Placements", "Edm.Int32", true), ("Identifier", "Edm.String", true),
        ("EventDate", "Edm.DateTimeOffset", true), ("ODataKey", "Edm.Guid", true));

    private static readonly string[] QualityStrings =
    [
        "CustomerName", "Assembly", "AssemblyRevision", "AssemblyDescription", "ProcessName", "ProcessRevision", "WorkOrder",
        "BatchName", "BatchStatus", "UnitOfIssue", "Identifier", "Lot", "SourceOperation", "CurrentOperation",
        "CurrentOperationAlias", "Operator", "DefectStatus", "AegisInspectionCode", "AegisInspectionCodeName",
        "AegisCategoryName", "InspectionCode", "DefectPartNumber", "DefectPartDescription", "DefectReference",
        "DefectFootprint", "DefectConnection", "InspectionArea", "InspectionWorkstation", "SourceWorkstation",
        "DefectComment", "SymptomCode", "SymptomCategory", "SymptomDescription", "SymptomStatus", "OperationGroup", "Line",
        "RootCauseDefect", "Location", "ExternalDefectID", "Source",
    ];

    public static readonly Dictionary<string, PropertyInfo> Quality = Props(
        QualityStrings.Select(n => (n, "Edm.String", false))
            .Concat([
                ("DefectID", "Edm.Guid", false), ("BatchQuantity", "Edm.Int32", false), ("CompletedQuantity", "Edm.Int32", false),
                ("DateCreated", "Edm.DateTimeOffset", false), ("InspectionPostedTime", "Edm.DateTimeOffset", false),
                ("Blocked", "Edm.Boolean", false), ("ODataKey", "Edm.Guid", false),
            ]).ToArray());

    public static readonly Dictionary<string, PropertyInfo> QualityHistory = Props(
        ("Identifier", "Edm.String", false), ("DefectID", "Edm.Guid", false), ("DefectStatus", "Edm.String", false),
        ("DefectHistoryTime", "Edm.DateTimeOffset", false), ("DefectHistoryOperation", "Edm.String", false),
        ("DefectHistoryWorkstation", "Edm.String", false), ("DefectHistoryComment", "Edm.String", false),
        ("DefectHistoryOperator", "Edm.String", false), ("DefectHistoryStatus", "Edm.String", false),
        ("Line", "Edm.String", false), ("CurrentOperation", "Edm.String", false), ("SourceOperation", "Edm.String", false),
        ("Batch", "Edm.String", false), ("Assembly", "Edm.String", false), ("DateCreated", "Edm.DateTimeOffset", false),
        ("DefectPartNumber", "Edm.String", false), ("DefectReference", "Edm.String", false), ("ODataKey", "Edm.Guid", false));

    /// <summary>Orden estable: SMT, Quality, QualityHistory.</summary>
    public static readonly IReadOnlyList<string> Names = ["SMT", "Quality", "QualityHistory"];

    public static readonly Dictionary<string, Dictionary<string, PropertyInfo>> Known = new()
    {
        ["SMT"] = Smt, ["Quality"] = Quality, ["QualityHistory"] = QualityHistory,
    };

    /// <summary>Lista blanca de campos filtrables por entidad.</summary>
    public static readonly Dictionary<string, HashSet<string>> Filterable = new()
    {
        ["SMT"] = ["Identifier", "Batch", "Assembly", "Customer", "OperationName", "WorkOrder", "EventDate"],
        ["Quality"] = ["Identifier", "BatchName", "Assembly", "CustomerName", "DefectStatus", "Line", "DateCreated", "DefectID", "SourceOperation"],
        ["QualityHistory"] = ["Identifier", "DefectID", "DefectHistoryTime"],
    };

    public static readonly Dictionary<string, string> DateField = new()
    {
        ["SMT"] = "EventDate", ["Quality"] = "DateCreated", ["QualityHistory"] = "DefectHistoryTime",
    };
}
