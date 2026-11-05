using System.Text;
using System.Xml;
using System.Xml.Linq;
using Gpv.Sqi.Models;

namespace Gpv.Sqi.OData;

public sealed class MetadataException(string message) : Exception(message);

public sealed class ODataMetadata
{
    public required string OdataVersion { get; init; }          // "4" o "2"/"3"
    public required Dictionary<string, string> EntitySets { get; init; }
    public required Dictionary<string, Dictionary<string, PropertyInfo>> EntityTypes { get; init; }

    public Dictionary<string, PropertyInfo>? PropertiesFor(string entitySet)
    {
        if (!EntitySets.TryGetValue(entitySet, out var typeName)) return null;
        return EntityTypes.GetValueOrDefault(typeName.Split('.')[^1]);
    }

    /// <summary>Compara las entidades autorizadas contra lo que publica el servidor.</summary>
    public Dictionary<string, Dictionary<string, object?>> CompareWithExpected()
    {
        var report = new Dictionary<string, Dictionary<string, object?>>();
        foreach (var entity in Entities.Names)
        {
            var expected = Entities.Known[entity];
            var real = PropertiesFor(entity);
            if (real is null)
            {
                report[entity] = new() { ["present"] = false, ["missing"] = expected.Keys.Order(StringComparer.Ordinal).ToList(),
                    ["extra"] = new List<string>(), ["type_mismatches"] = new List<object>() };
                continue;
            }
            report[entity] = new()
            {
                ["present"] = true,
                ["missing"] = expected.Keys.Except(real.Keys).Order(StringComparer.Ordinal).ToList(),
                ["extra"] = real.Keys.Except(expected.Keys).Order(StringComparer.Ordinal).ToList(),
                ["type_mismatches"] = expected.Where(kv => real.TryGetValue(kv.Key, out var r) && r.EdmType != kv.Value.EdmType)
                    .Select(kv => new Dictionary<string, object?> { ["property"] = kv.Key, ["expected"] = kv.Value.EdmType, ["actual"] = real[kv.Key].EdmType })
                    .ToList(),
                ["properties"] = real.Values.Select(p => new Dictionary<string, object?> { ["name"] = p.Name, ["type"] = p.EdmType }).ToList(),
            };
        }
        return report;
    }
}

/// <summary>Lectura de $metadata (EDMX/CSDL). Se rechazan DOCTYPE/ENTITY (XXE / expansión de entidades).</summary>
public static class MetadataParser
{
    public static ODataMetadata Parse(byte[] xml)
    {
        var head = Encoding.UTF8.GetString(xml, 0, Math.Min(xml.Length, 4096)).ToUpperInvariant();
        if (head.Contains("<!DOCTYPE") || head.Contains("<!ENTITY"))
            throw new MetadataException("El documento $metadata contiene DOCTYPE/ENTITY y fue rechazado");
        XDocument doc;
        try
        {
            using var ms = new MemoryStream(xml);
            using var reader = XmlReader.Create(ms, new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null });
            doc = XDocument.Load(reader);
        }
        catch (XmlException ex) { throw new MetadataException($"$metadata no es XML válido: {ex.Message}"); }
        var root = doc.Root ?? throw new MetadataException("Documento vacío");
        if (root.Name.LocalName != "Edmx") throw new MetadataException("El documento no es un EDMX de OData");

        var version = (string?)root.Attribute("Version") ?? "";
        var odataVersion = "2";
        if (version.StartsWith('4')) odataVersion = "4";
        else
        {
            foreach (var ds in root.Descendants().Where(e => e.Name.LocalName == "DataServices"))
                foreach (var a in ds.Attributes())
                    if (a.Name.LocalName == "DataServiceVersion" && a.Value.StartsWith('3')) odataVersion = "3";
        }

        var types = new Dictionary<string, Dictionary<string, PropertyInfo>>();
        var sets = new Dictionary<string, string>();
        foreach (var el in root.Descendants())
        {
            var name = (string?)el.Attribute("Name");
            if (name is null) continue;
            if (el.Name.LocalName == "EntityType")
            {
                types[name] = el.Elements().Where(c => c.Name.LocalName == "Property" && c.Attribute("Name") is not null)
                    .GroupBy(c => (string)c.Attribute("Name")!)
                    .ToDictionary(g => g.Key, g => new PropertyInfo(g.Key, (string?)g.First().Attribute("Type") ?? "Edm.String", true));
            }
            else if (el.Name.LocalName == "EntitySet")
            {
                sets[name] = (string?)el.Attribute("EntityType") ?? "";
            }
        }
        if (sets.Count == 0) throw new MetadataException("$metadata no contiene EntitySets");
        return new ODataMetadata { OdataVersion = odataVersion, EntitySets = sets, EntityTypes = types };
    }
}
