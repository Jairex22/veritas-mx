using System.Text.Json.Nodes;
using Gpv.Sqi.Analytics;
using Gpv.Sqi.Infrastructure;
using Xunit;

namespace Gpv.Sqi.Tests;

public class DefectTests
{
    [Fact]
    public void MirionFodCountedOnce()
    {
        var defects = Defects.Group(TestHelpers.Quality, TestHelpers.History, true);
        var d = Assert.Single(defects);
        Assert.Equal(3, d["history_entries"]);
        Assert.Equal("Closed", d["status"]);
        Assert.Equal("CLOSED", d["classification"]);
        Assert.Equal("SMT REPAIR", d["closed_operation"]);
        Assert.Equal("AOI-3D-PC-L3", d["closed_workstation"]);
        Assert.Equal("40846", d["closed_operator"]);
        Assert.Equal("FOD", d["comment"]);
        Assert.Equal("SMT Line 01", d["line_registered"]);
        Assert.Contains((List<string>)d["notes"]!, n => n.Contains("False"));
    }

    [Fact]
    public void HistoryRowsNeverCountedAsDefects()
    {
        var q = Enumerable.Repeat(TestHelpers.Quality[0], 3).ToList();
        var h = Enumerable.Range(0, 4).SelectMany(_ => TestHelpers.History).ToList();
        Assert.Equal(1, Defects.Summarize(Defects.Group(q, h, true))["unique_defects"]);
    }

    [Fact]
    public void DefectIdCaseInsensitive()
    {
        var q2 = TestHelpers.Quality[0].Clone();
        q2["DefectID"] = q2.Str("DefectID")!.ToUpperInvariant();
        Assert.Single(Defects.Group([TestHelpers.Quality[0], q2], TestHelpers.History, true));
    }

    [Fact]
    public void HistoryUnavailableMarksIncomplete() =>
        Assert.Equal("HISTORY_INCOMPLETE", Defects.Group(TestHelpers.Quality, [], false)[0]["classification"]);

    [Fact]
    public void ClosedWithoutClosureHistory()
    {
        var h = TestHelpers.History.Where(x => x.Str("DefectHistoryStatus") != "Closed").ToList();
        Assert.Equal("HISTORY_INCOMPLETE", Defects.Group(TestHelpers.Quality, h, true)[0]["classification"]);
    }

    [Fact]
    public void OpenAndUnknown()
    {
        var open = TestHelpers.Quality[0].Clone(); open["DefectStatus"] = "Open";
        var unknown = TestHelpers.Quality[0].Clone(); unknown["DefectStatus"] = null;
        Assert.Equal("ACTIVE", Defects.Group([open], [], true)[0]["classification"]);
        Assert.Equal("UNKNOWN_STATUS", Defects.Group([unknown], [], true)[0]["classification"]);
    }

    [Fact]
    public void NullsTolerated()
    {
        var d = Defects.Group([new JsonObject { ["DefectID"] = null, ["DateCreated"] = null }], [], true);
        Assert.Single(d);
        Assert.Null(d[0]["time_to_close_min"]);
    }

    [Fact]
    public void TimeToCloseComputed() =>
        Assert.Equal(218.37, Defects.Group(TestHelpers.Quality, TestHelpers.History, true)[0]["time_to_close_min"]);
}

public class TimelineTests
{
    [Fact]
    public void ChronologicalAndNullsLast()
    {
        var noDate = TestHelpers.Smt[0].Clone(); noDate["EventDate"] = null; noDate["OperationName"] = "SIN FECHA";
        var smt = TestHelpers.Smt.AsEnumerable().Reverse().Append(noDate).ToList();
        var tl = Timeline.Build(smt, TestHelpers.Quality, TestHelpers.History);
        Assert.Equal("SIN FECHA", tl[^1]["title"]);
        Assert.False((bool)tl[^1]["time_verified"]!);
        var ops = tl.Where(t => (string)t["kind"]! == "SMT_EVENT" && t["time"] is not null).Select(t => (string)t["title"]!).ToList();
        Assert.Equal(["SMT Post-Reflow AOI Top", "SMT Post-Reflow AOI Top", "SMT REPAIR", "QA SMT"], ops);
    }

    [Fact]
    public void MixedOffsetsSortedByInstant()
    {
        var a = TestHelpers.Smt[0].Clone(); a["EventDate"] = "2026-11-04T21:00:00Z"; a["OperationName"] = "A";
        var b = TestHelpers.Smt[0].Clone(); b["EventDate"] = "2026-11-04T14:00:00-06:00"; b["OperationName"] = "B";
        Assert.Equal(["B", "A"], Timeline.Build([a, b], [], []).Select(t => (string)t["title"]!));
    }

    [Fact]
    public void DefectCountedOnceInTimeline()
    {
        var q = TestHelpers.Quality.Concat(TestHelpers.Quality).ToList();
        Assert.Equal(1, Timeline.Build(TestHelpers.Smt, q, TestHelpers.History).Count(t => (string)t["kind"]! == "DEFECT_CREATED"));
    }
}

public class ReworkTests
{
    private static readonly List<string> Kw = ["REPAIR"];
    private static HashSet<string> Cats(IEnumerable<Dictionary<string, object?>> a) => a.Select(x => (string)x["category"]!).ToHashSet();

    [Fact]
    public void MirionRules()
    {
        var defects = Defects.Group(TestHelpers.Quality, TestHelpers.History, true);
        var alerts = ReworkRules.Evaluate("W07632100028", TestHelpers.Smt, defects, Kw, new Dictionary<string, List<string>>());
        var cats = Cats(alerts);
        foreach (var c in new[] { "REPEATED_OPERATION", "REPAIR_RECORDED", "POSSIBLE_REWORK", "POST_REPAIR_EVENTS", "DEFECT_CLOSED", "LOOP_NOT_CONFIRMABLE" })
            Assert.Contains(c, cats);
        Assert.DoesNotContain("CONFIRMED_LOOP", cats);   // dos AOI no prueban un bucle
        Assert.DoesNotContain("DUPLICATE_EVENT", cats);  // horas distintas
        var rep = alerts.First(a => (string)a["category"]! == "REPEATED_OPERATION");
        Assert.Equal(["SMT#1", "SMT#2"], (List<string>)rep["evidence"]!);
    }

    [Fact]
    public void DuplicateEvent()
    {
        var alerts = ReworkRules.Evaluate("X", [TestHelpers.Smt[0], TestHelpers.Smt[0].Clone()], [], Kw, new Dictionary<string, List<string>>());
        Assert.Contains("DUPLICATE_EVENT", Cats(alerts));
        Assert.DoesNotContain("REPEATED_OPERATION", Cats(alerts));
    }

    [Fact]
    public void ConfirmedLoopOnlyWithAuthorizedFlow()
    {
        var flow = new Dictionary<string, List<string>> { ["MR.48.SM"] = ["SMT Post-Reflow AOI Top", "SMT REPAIR", "QA SMT"] };
        var back = TestHelpers.Smt[0].Clone(); back["EventDate"] = "2026-11-04T15:40:00-06:00";
        var smt = TestHelpers.Smt.Append(back).ToList();
        Assert.Contains("CONFIRMED_LOOP", Cats(ReworkRules.Evaluate("W", smt, [], Kw, flow)));
        Assert.DoesNotContain("CONFIRMED_LOOP", Cats(ReworkRules.Evaluate("W", smt, [], Kw, new Dictionary<string, List<string>>())));
    }

    [Fact]
    public void NoAlertsForCleanFlow()
    {
        var clean = new[] { "SPI", "P&P", "AOI", "QA" }.Select((op, i) =>
        {
            var r = TestHelpers.Smt[0].Clone(); r["OperationName"] = op; r["EventDate"] = $"2026-11-04T1{i}:00:00-06:00"; return r;
        }).ToList();
        Assert.Empty(ReworkRules.Evaluate("C", clean, [], Kw, new Dictionary<string, List<string>>()));
    }
}
