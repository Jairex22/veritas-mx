using System.Text;
using Gpv.Sqi.Models;
using Gpv.Sqi.OData;
using Xunit;

namespace Gpv.Sqi.Tests;

public class ParserTests
{
    private static byte[] B(string s) => Encoding.UTF8.GetBytes(s);

    [Fact]
    public void V4Value()
    {
        var (rows, next) = ODataPayloadParser.Parse(B("{\"@odata.context\":\"x\",\"value\":[{\"Identifier\":\"A\",\"@odata.etag\":\"1\"}]}"));
        Assert.Single(rows);
        Assert.Equal("{\"Identifier\":\"A\"}", rows[0].ToJsonString());
        Assert.Null(next);
    }

    [Fact]
    public void V2ResultsAndNext()
    {
        var (rows, next) = ODataPayloadParser.Parse(B("{\"d\":{\"results\":[{\"a\":1,\"__metadata\":{}}],\"__next\":\"http://x/n\"}}"));
        Assert.Equal("{\"a\":1}", rows[0].ToJsonString());
        Assert.Equal("http://x/n", next);
    }

    [Fact]
    public void EmptyValueIsValid() => Assert.Empty(ODataPayloadParser.Parse(B("{\"value\":[]}")).Rows);

    [Fact]
    public void NullValuesPreserved()
    {
        var rows = ODataPayloadParser.Parse(B("{\"value\":[{\"WorkOrder\":null}]}")).Rows;
        Assert.True(rows[0].ContainsKey("WorkOrder"));
        Assert.Null(rows[0]["WorkOrder"]);
    }

    [Fact]
    public void InvalidJson() => Assert.Throws<PayloadException>(() => ODataPayloadParser.Parse(B("<html>Error</html>")));

    [Theory]
    [InlineData("[]")]
    [InlineData("{\"items\":[]}")]
    [InlineData("{\"value\":{}}")]
    [InlineData("{\"value\":[1,2]}")]
    [InlineData("{\"error\":{\"message\":\"x\"}}")]
    [InlineData("{\"d\":\"text\"}")]
    public void UnexpectedStructures(string raw) => Assert.Throws<PayloadException>(() => ODataPayloadParser.Parse(B(raw)));
}

public class MetadataTests
{
    [Fact]
    public void ParseFixture()
    {
        var meta = MetadataParser.Parse(TestHelpers.MetadataBytes);
        Assert.Equal("4", meta.OdataVersion);
        Assert.Contains("SMT", meta.EntitySets.Keys);
        var smt = meta.PropertiesFor("SMT")!;
        Assert.Equal("Edm.DateTimeOffset", smt["EventDate"].EdmType);
        Assert.Equal("Edm.Guid", smt["ODataKey"].EdmType);
        foreach (var e in Entities.Names)
        {
            var c = meta.CompareWithExpected()[e];
            Assert.True((bool)c["present"]!);
            Assert.Empty((List<string>)c["missing"]!);
        }
    }

    [Fact]
    public void V3Detection()
    {
        var xml = "<edmx:Edmx Version=\"1.0\" xmlns:edmx=\"http://schemas.microsoft.com/ado/2007/06/edmx\">" +
                  "<edmx:DataServices xmlns:m=\"http://schemas.microsoft.com/ado/2007/08/dataservices/metadata\" m:DataServiceVersion=\"3.0\">" +
                  "<Schema xmlns=\"http://schemas.microsoft.com/ado/2009/11/edm\" Namespace=\"N\"><EntityType Name=\"SMT\"><Property Name=\"Identifier\" Type=\"Edm.String\"/></EntityType>" +
                  "<EntityContainer Name=\"C\"><EntitySet Name=\"SMT\" EntityType=\"N.SMT\"/></EntityContainer></Schema></edmx:DataServices></edmx:Edmx>";
        var meta = MetadataParser.Parse(Encoding.UTF8.GetBytes(xml));
        Assert.Equal("3", meta.OdataVersion);
        Assert.Contains("EventDate", (List<string>)meta.CompareWithExpected()["SMT"]["missing"]!);
    }

    [Theory]
    [InlineData("<?xml version=\"1.0\"?><!DOCTYPE x [<!ENTITY a \"b\">]><x>&a;</x>")]
    [InlineData("not xml")]
    [InlineData("<root/>")]
    public void RejectsDoctypeAndGarbage(string xml) => Assert.Throws<MetadataException>(() => MetadataParser.Parse(Encoding.UTF8.GetBytes(xml)));
}

public class FilterTests
{
    private const string Base = "http://srv:6065/odata/";

    [Fact]
    public void EscapeQuotes() => Assert.Equal("'O''Brien'", ODataFilterBuilder.EscapeStringLiteral("O'Brien"));

    [Fact]
    public void InjectionAttemptStaysInsideLiteral()
    {
        var evil = "X' or 1 eq 1 or Identifier eq '";
        var url = ODataFilterBuilder.BuildQueryUrl(Base, new QuerySpec("SMT", [new Filter("Identifier", "eq", evil)]), null, "4");
        var decoded = Uri.UnescapeDataString(url.Split("$filter=")[1].Split('&')[0]);
        Assert.Equal("Identifier eq 'X'' or 1 eq 1 or Identifier eq '''", decoded);
        Assert.DoesNotContain(" ", url);
        Assert.DoesNotContain("'", url);
    }

    [Fact]
    public void ControlCharsAndLength()
    {
        Assert.Throws<FilterException>(() => ODataFilterBuilder.EscapeStringLiteral("A\nB"));
        Assert.Throws<FilterException>(() => ODataFilterBuilder.EscapeStringLiteral(new string('A', 500)));
    }

    [Fact]
    public void UnauthorizedFieldEntityOperator()
    {
        Assert.Throws<FilterException>(() => ODataFilterBuilder.BuildQueryUrl(Base, new QuerySpec("SMT", [new Filter("Attempts", "eq", 1)]), null, "4"));
        Assert.Throws<FilterException>(() => ODataFilterBuilder.BuildQueryUrl(Base, new QuerySpec("ProductivityOverTime"), null, "4"));
        Assert.Throws<FilterException>(() => ODataFilterBuilder.BuildQueryUrl(Base, new QuerySpec("SMT", [new Filter("Identifier", "substringof", "x")]), null, "4"));
    }

    [Fact]
    public void FieldMustExistInMetadata()
    {
        var props = Entities.Smt.Where(kv => kv.Key != "Batch").ToDictionary(kv => kv.Key, kv => kv.Value);
        Assert.Throws<FilterException>(() => ODataFilterBuilder.BuildQueryUrl(Base, new QuerySpec("SMT", [new Filter("Batch", "eq", "B")]), props, "4"));
    }

    [Fact]
    public void TypedLiterals()
    {
        var dt = new DateTimeOffset(2026, 11, 4, 21, 11, 8, TimeSpan.Zero);
        Assert.Equal("2026-11-04T21:11:08Z", ODataFilterBuilder.FormatLiteral(dt, "Edm.DateTimeOffset", "4"));
        Assert.Equal("datetimeoffset'2026-11-04T21:11:08Z'", ODataFilterBuilder.FormatLiteral(dt, "Edm.DateTimeOffset", "3"));
        Assert.Equal("2026-11-04T21:11:08Z", ODataFilterBuilder.FormatLiteral(dt.ToOffset(TimeSpan.FromHours(-6)), "Edm.DateTimeOffset", "4"));
        const string g = "29a17d43-6e47-2f1b-0035-08df3a9d40d6";
        Assert.Equal(g, ODataFilterBuilder.FormatLiteral(g, "Edm.Guid", "4"));
        Assert.Equal($"guid'{g}'", ODataFilterBuilder.FormatLiteral(g, "Edm.Guid", "2"));
        Assert.Throws<FilterException>(() => ODataFilterBuilder.FormatLiteral("not-a-guid' or 1 eq 1", "Edm.Guid", "4"));
        Assert.Throws<FilterException>(() => ODataFilterBuilder.FormatLiteral(new DateTime(2026, 1, 1), "Edm.DateTimeOffset", "4"));
    }

    [Fact]
    public void InOperatorLimited()
    {
        var ids = Enumerable.Range(0, 11).Select(i => $"00000000-0000-4000-8000-{i:000000000000}").ToList();
        Assert.Throws<FilterException>(() => ODataFilterBuilder.BuildQueryUrl(Base, new QuerySpec("QualityHistory", [new Filter("DefectID", "in", ids)]), null, "4"));
        var url = ODataFilterBuilder.BuildQueryUrl(Base, new QuerySpec("QualityHistory", [new Filter("DefectID", "in", ids.Take(2).ToList())]), null, "4");
        Assert.Contains("%20or%20", url);
    }

    [Fact]
    public void FullUrlShape()
    {
        var url = ODataFilterBuilder.BuildQueryUrl(Base, new QuerySpec("SMT", [new Filter("Identifier", "eq", "W07632100028")], [("EventDate", "asc")], 5), null, "4");
        Assert.StartsWith("http://srv:6065/odata/SMT?$filter=", url);
        Assert.Contains("$orderby=EventDate%20asc", url);
        Assert.Contains("$top=5", url);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(5000)]
    public void TopBounds(int top) =>
        Assert.Throws<FilterException>(() => ODataFilterBuilder.BuildQueryUrl(Base, new QuerySpec("SMT", top: top), null, "4"));
}
