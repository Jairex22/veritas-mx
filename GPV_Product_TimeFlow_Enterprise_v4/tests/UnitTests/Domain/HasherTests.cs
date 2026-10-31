using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.UnitTests.Domain;

public class HasherTests
{
    private static Request NewRequest()
    {
        var id = Guid.Parse("6f1d2c3b-4a59-4e8f-9b7a-112233445566");
        return new Request
        {
            Id = id, Folio = "TF-2026-000001", EmployeeId = 7, Kind = RequestKind.Vacation, Version = 1,
            Reason = "Vacaciones familiares", IsFullDay = true, TotalDays = 3,
            Periods = [new RequestPeriod { RequestId = id, StartDate = new DateOnly(2026, 4, 6), EndDate = new DateOnly(2026, 4, 8) }],
            Attachments = [new Attachment { Id = Guid.NewGuid(), RequestId = id, Sha256 = "aa" + new string('0', 62) }]
        };
    }

    [Fact]
    public void Content_hash_is_deterministic_and_hex_sha256()
    {
        var h1 = RequestContentHasher.Compute(NewRequest());
        var h2 = RequestContentHasher.Compute(NewRequest());
        Assert.Equal(h1, h2);
        Assert.Equal(64, h1.Length);
        Assert.Matches("^[0-9a-f]{64}$", h1);
    }

    public static TheoryData<string> Mutations => ["reason", "start", "end", "version", "addAttachment", "deleteAttachment", "justification", "days", "category"];

    [Theory]
    [MemberData(nameof(Mutations))]
    public void Content_hash_changes_when_substantive_data_changes(string mutation)
    {
        var baseline = RequestContentHasher.Compute(NewRequest());
        var r = NewRequest();
        switch (mutation)
        {
            case "reason": r.Reason = "Vacaciones familiares (ajuste)"; break;
            case "start": r.Periods[0].StartDate = r.Periods[0].StartDate.AddDays(-1); break;
            case "end": r.Periods[0].EndDate = r.Periods[0].EndDate.AddDays(1); break;
            case "version": r.Version = 2; break;
            case "addAttachment": r.Attachments.Add(new Attachment { Id = Guid.NewGuid(), Sha256 = "bb" + new string('1', 62) }); break;
            case "deleteAttachment": r.Attachments[0].IsDeleted = true; break;
            case "justification": r.Justification = "Nueva justificación"; break;
            case "days": r.TotalDays = 4; break;
            case "category": r.LeaveCategoryId = 3; break;
        }
        Assert.NotEqual(baseline, RequestContentHasher.Compute(r));
    }

    [Fact]
    public void Content_hash_ignores_reason_whitespace_and_attachment_order()
    {
        var a = NewRequest();
        a.Attachments.Add(new Attachment { Id = Guid.NewGuid(), Sha256 = "cc" + new string('2', 62) });
        var b = NewRequest();
        b.Reason = "  Vacaciones familiares  ";
        b.Attachments.Insert(0, new Attachment { Id = Guid.NewGuid(), Sha256 = "cc" + new string('2', 62) });
        Assert.Equal(RequestContentHasher.Compute(a), RequestContentHasher.Compute(b));
    }

    [Fact]
    public void Content_hash_does_not_depend_on_workflow_status()
    {
        var a = NewRequest();
        var b = NewRequest();
        b.Status = RequestStatus.PendingManager;
        Assert.Equal(RequestContentHasher.Compute(a), RequestContentHasher.Compute(b));
    }

    [Fact]
    public void Signature_hash_is_deterministic_and_bound_to_all_inputs()
    {
        var png = new byte[] { 1, 2, 3, 4 };
        var req = Guid.NewGuid();
        var at = new DateTime(2026, 3, 10, 15, 0, 0, DateTimeKind.Utc);
        var h = SignatureHasher.Compute(png, "doc", 5, req, 1, at);

        Assert.Equal(h, SignatureHasher.Compute(png, "doc", 5, req, 1, at));
        Assert.Equal(h, SignatureHasher.Compute(png, "doc", 5, req, 1, DateTime.SpecifyKind(at, DateTimeKind.Unspecified)));
        Assert.NotEqual(h, SignatureHasher.Compute([1, 2, 3, 5], "doc", 5, req, 1, at));
        Assert.NotEqual(h, SignatureHasher.Compute(png, "doc2", 5, req, 1, at));
        Assert.NotEqual(h, SignatureHasher.Compute(png, "doc", 6, req, 1, at));
        Assert.NotEqual(h, SignatureHasher.Compute(png, "doc", 5, Guid.NewGuid(), 1, at));
        Assert.NotEqual(h, SignatureHasher.Compute(png, "doc", 5, req, 2, at));
        Assert.NotEqual(h, SignatureHasher.Compute(png, "doc", 5, req, 1, at.AddSeconds(1)));
    }

    private static List<AuditLog> BuildChain(int count)
    {
        var chain = new List<AuditLog>();
        var previous = "";
        for (var i = 1; i <= count; i++)
        {
            var e = new AuditLog
            {
                Id = i, Sequence = i, OccurredAtUtc = new DateTime(2026, 3, 10, 12, 0, i, DateTimeKind.Utc), ActorEmployeeId = i % 2 == 0 ? i : null,
                ActorName = $"Actor {i}", Action = "request.updated", EntityType = "Request", EntityId = $"E{i}", Details = $"{{\"n\":{i}}}",
                IpAddress = "127.0.0.1", PreviousHash = previous
            };
            e.Hash = AuditHasher.Compute(e);
            previous = e.Hash;
            chain.Add(e);
        }
        return chain;
    }

    private static long? FirstBroken(IEnumerable<AuditLog> chain)
    {
        var previous = "";
        foreach (var e in chain.OrderBy(x => x.Sequence))
        {
            if (e.PreviousHash != previous || AuditHasher.Compute(e) != e.Hash) return e.Id;
            previous = e.Hash;
        }
        return null;
    }

    [Fact]
    public void Audit_chain_links_each_entry_to_the_previous_hash()
    {
        var chain = BuildChain(5);
        Assert.Equal("", chain[0].PreviousHash);
        for (var i = 1; i < chain.Count; i++) Assert.Equal(chain[i - 1].Hash, chain[i].PreviousHash);
        Assert.Equal(chain.Count, chain.Select(c => c.Hash).Distinct().Count());
        Assert.Null(FirstBroken(chain));
    }

    [Fact]
    public void Audit_chain_detects_tampered_details()
    {
        var chain = BuildChain(5);
        chain[2].Details = "x";
        Assert.Equal(3, FirstBroken(chain));
    }

    [Fact]
    public void Audit_chain_detects_deleted_entry()
    {
        var chain = BuildChain(5);
        chain.RemoveAt(1);
        Assert.Equal(3, FirstBroken(chain));
    }

    [Fact]
    public void Audit_chain_detects_recomputed_entry_without_relinking_successor()
    {
        var chain = BuildChain(5);
        chain[1].ActorName = "Intruso";
        chain[1].Hash = AuditHasher.Compute(chain[1]); // el atacante recalcula solo ese registro
        Assert.Equal(3, FirstBroken(chain));
    }
}
