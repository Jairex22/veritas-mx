using Gpv.Sqi.Models;

namespace Gpv.Sqi.OData;

/// <summary>Interfaz común del cliente OData real y la fuente de demostración.</summary>
public interface IDataSource
{
    Task<QueryResult> ExecuteAsync(QuerySpec spec, CancellationToken ct = default);
    Task<(QueryResult Result, ODataMetadata? Metadata)> FetchMetadataAsync(CancellationToken ct = default);
    QueryResult? PolicyCheck(string entity);
    Dictionary<string, object?>? LastMetadataStatus { get; }
}
