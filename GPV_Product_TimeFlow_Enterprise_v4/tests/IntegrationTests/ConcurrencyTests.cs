using System.Net;
using System.Net.Http.Json;
using GPV.ProductTimeFlow.Infrastructure.Seeding;
using GPV.ProductTimeFlow.IntegrationTests.Infrastructure;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;

namespace GPV.ProductTimeFlow.IntegrationTests;

/// <summary>Decisiones simultáneas, doble clic e idempotencia.</summary>
public class ConcurrencyTests(TimeFlowApiFactory factory) : IClassFixture<TimeFlowApiFactory>
{
    private static string Key() => Guid.NewGuid().ToString("N");

    private static DecisionInput Approve(string key, int seed = 1) => new()
    {
        Decision = ApprovalDecisionType.Approve, SignaturePngBase64 = SyntheticSignature.Base64(seed), SignatureConsent = true, ExpectedVersion = 1, IdempotencyKey = key
    };

    private async Task<Guid> SubmittedAsync()
    {
        var ana = await factory.LoginAsync(TimeFlowApiFactory.Ana);
        var draft = await ana.CreateRequestAsync(TimeFlowApiFactory.Overtime(factory.NextOvertimeDate()));
        await ana.SubmitAsync(draft.Summary.Id, new SubmitInput { IdempotencyKey = Key() });
        return draft.Summary.Id;
    }

    private static Task<HttpResponseMessage> PostJson(HttpClient http, string url, object body) =>
        http.PostAsync(url, JsonContent.Create(body, body.GetType(), options: TimeFlowJson.Options));

    [Fact]
    public async Task Two_simultaneous_approvals_with_different_keys_yield_one_success_and_one_conflict()
    {
        var id = await SubmittedAsync();
        var lauras = await factory.SessionsAsync(TimeFlowApiFactory.Laura, 2); // dos pestañas/dispositivos
        var (laura1, laura2) = (lauras[0], lauras[1]);

        var responses = await Task.WhenAll(
            PostJson(laura1.Http, $"api/v1/requests/{id}/decision", Approve(Key(), 1)),
            PostJson(laura2.Http, $"api/v1/requests/{id}/decision", Approve(Key(), 2)));
        var codes = responses.Select(r => r.StatusCode).OrderBy(c => c).ToArray();
        foreach (var r in responses) r.Dispose();

        Assert.Equal([HttpStatusCode.OK, HttpStatusCode.Conflict], codes);
        var decisions = await factory.WithDbAsync(db => db.ApprovalDecisions.CountAsync(d => d.RequestId == id && d.Action == WorkflowAction.SupervisorApprove));
        Assert.Equal(1, decisions);
        var signatures = await factory.WithDbAsync(db => db.ElectronicSignatures.CountAsync(s => s.RequestId == id));
        Assert.Equal(1, signatures);
        var status = await factory.WithDbAsync(db => db.Requests.Where(r => r.Id == id).Select(r => r.Status).SingleAsync());
        Assert.Equal(RequestStatus.PendingManager, status);
    }

    [Fact]
    public async Task Same_idempotency_key_twice_is_reported_as_duplicate()
    {
        var id = await SubmittedAsync();
        var laura = await factory.LoginAsync(TimeFlowApiFactory.Laura);
        var key = Key();

        var first = await laura.DecideAsync(id, Approve(key));
        Assert.False(first.WasDuplicate);
        Assert.Equal(RequestStatus.PendingManager, first.Status);

        var second = await laura.DecideAsync(id, Approve(key));
        Assert.True(second.WasDuplicate);
        Assert.Equal(RequestStatus.PendingManager, second.Status);

        // También mediante el encabezado Idempotency-Key.
        using var viaHeader = new HttpRequestMessage(HttpMethod.Post, $"api/v1/requests/{id}/decision")
        { Content = JsonContent.Create(Approve(Key()), options: TimeFlowJson.Options) };
        viaHeader.Headers.Add("Idempotency-Key", key);
        using var headerResponse = await laura.Http.SendAsync(viaHeader);
        Assert.Equal(HttpStatusCode.OK, headerResponse.StatusCode);
        var dto = await headerResponse.Content.ReadFromJsonAsync<WorkflowResultDto>(TimeFlowJson.Options);
        Assert.True(dto!.WasDuplicate);

        Assert.Equal(1, await factory.WithDbAsync(db => db.ApprovalDecisions.CountAsync(d => d.RequestId == id && d.Action == WorkflowAction.SupervisorApprove)));

        // Otra persona no puede reutilizar la clave de idempotencia ajena.
        var carlos = await factory.LoginAsync(TimeFlowApiFactory.Carlos);
        await ApiAssert.FailsWithAsync(HttpStatusCode.Conflict, () => carlos.DecideAsync(id, Approve(key, 3)));
    }

    [Fact]
    public async Task Ten_parallel_submits_yield_exactly_one_success()
    {
        var ana = await factory.LoginAsync(TimeFlowApiFactory.Ana);
        var draft = await ana.CreateRequestAsync(TimeFlowApiFactory.Overtime(factory.NextOvertimeDate()));
        var id = draft.Summary.Id;

        var clients = await factory.SessionsAsync(TimeFlowApiFactory.Ana, 10);
        var responses = await Task.WhenAll(clients.Select(c => PostJson(c.Http, $"api/v1/requests/{id}/submit", new SubmitInput { IdempotencyKey = Key() })));
        var codes = responses.Select(r => r.StatusCode).ToList();
        foreach (var r in responses) r.Dispose();

        Assert.Equal(1, codes.Count(c => c == HttpStatusCode.OK));
        Assert.All(codes.Where(c => c != HttpStatusCode.OK), c => Assert.Equal(HttpStatusCode.Conflict, c));

        var (submits, steps, status, emails) = await factory.WithDbAsync(async db => (
            await db.ApprovalDecisions.CountAsync(d => d.RequestId == id && d.Action == WorkflowAction.Submit),
            await db.ApprovalSteps.CountAsync(s => s.RequestId == id),
            await db.Requests.Where(r => r.Id == id).Select(r => r.Status).SingleAsync(),
            await db.EmailOutbox.CountAsync(m => m.RequestId == id && m.EventType == "submitted")));
        Assert.Equal(1, submits);
        Assert.Equal(3, steps);
        Assert.Equal(RequestStatus.PendingSupervisor, status);
        Assert.Equal(1, emails);
    }

    [Fact]
    public async Task Parallel_drafts_get_unique_folios()
    {
        var clients = await factory.SessionsAsync(TimeFlowApiFactory.Ana, 6);
        var dates = clients.Select(_ => factory.NextOvertimeDate()).ToArray();
        var results = await Task.WhenAll(clients.Select(async (c, i) =>
        {
            try { return (await c.CreateRequestAsync(TimeFlowApiFactory.Overtime(dates[i]))).Summary.Folio; }
            catch (ApiException ex) when (ex.Status == HttpStatusCode.Conflict) { return null; } // conflicto de secuencia: reintentable, nunca duplicado
        }));
        var folios = results.Where(f => f is not null).ToList();
        Assert.NotEmpty(folios);
        Assert.Equal(folios.Count, folios.Distinct().Count());
        var all = await factory.WithDbAsync(db => db.Requests.Select(r => r.Folio).ToListAsync());
        Assert.Equal(all.Count, all.Distinct().Count());
    }
}
