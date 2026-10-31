using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using GPV.ProductTimeFlow.Infrastructure.Seeding;
using GPV.ProductTimeFlow.IntegrationTests.Infrastructure;
using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.IntegrationTests;

/// <summary>Autorización por recurso (IDOR), adjuntos y verificación pública.</summary>
public class SecurityTests(TimeFlowApiFactory factory) : IClassFixture<TimeFlowApiFactory>
{
    private static string Key() => Guid.NewGuid().ToString("N");
    private static readonly byte[] SmallPdf = System.Text.Encoding.ASCII.GetBytes(
        "%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n");

    private async Task<(TimeFlowApiClient Ana, RequestDetailDto Draft)> AnaDraftAsync()
    {
        var ana = await factory.LoginAsync(TimeFlowApiFactory.Ana);
        return (ana, await ana.CreateRequestAsync(TimeFlowApiFactory.Overtime(factory.NextOvertimeDate())));
    }

    [Fact]
    public async Task Employee_outside_the_chain_cannot_read_or_act_on_anothers_request()
    {
        var (ana, draft) = await AnaDraftAsync();
        var id = draft.Summary.Id;
        var attachment = await ana.UploadAttachmentAsync(id, new MemoryStream(SmallPdf), "constancia.pdf", "application/pdf");
        await ana.SubmitAsync(id, new SubmitInput { IdempotencyKey = Key() });

        var outsider = await factory.LoginAsync(await factory.CreateEmployeeAsync());
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => outsider.GetRequestAsync(id));
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => outsider.UpdateRequestAsync(id, TimeFlowApiFactory.Overtime(draft.Summary.StartDate)));
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => outsider.SubmitAsync(id, new SubmitInput { IdempotencyKey = Key() }));
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => outsider.CancelAsync(id, new CancelInput()));
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => outsider.DecideAsync(id, new DecisionInput
        {
            Decision = ApprovalDecisionType.Approve, SignaturePngBase64 = SyntheticSignature.Base64(1), SignatureConsent = true, ExpectedVersion = 1, IdempotencyKey = Key()
        }));
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => outsider.DownloadPdfAsync(id));
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => outsider.DownloadAttachmentAsync(attachment.Id));
        foreach (var scope in new[] { RequestScope.Mine, RequestScope.ApprovalInbox, RequestScope.TeamHistory })
        {
            var list = await outsider.ListRequestsAsync(new RequestQuery { Scope = scope, PageSize = 100 });
            Assert.DoesNotContain(list.Items, r => r.Id == id);
        }
        // Los alcances globales están reservados a registro administrativo / administración de Producto.
        await ApiAssert.FailsWithAsync(HttpStatusCode.Forbidden, () => outsider.ListRequestsAsync(new RequestQuery { Scope = RequestScope.All }));
        await ApiAssert.FailsWithAsync(HttpStatusCode.Forbidden, () => outsider.ListRequestsAsync(new RequestQuery { Scope = RequestScope.Administrative }));

        // Un líder de otra área (Daniela) tampoco la ve.
        var daniela = await factory.LoginAsync(TimeFlowApiFactory.Daniela);
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => daniela.GetRequestAsync(id));

        // La solicitud sigue intacta.
        Assert.Equal(RequestStatus.PendingSupervisor, (await ana.GetRequestAsync(id)).Summary.Status);
    }

    [Fact]
    public async Task Supervisor_cannot_see_drafts_and_cannot_edit_submitted_requests()
    {
        var (ana, draft) = await AnaDraftAsync();
        var laura = await factory.LoginAsync(TimeFlowApiFactory.Laura);
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => laura.GetRequestAsync(draft.Summary.Id));

        await ana.SubmitAsync(draft.Summary.Id, new SubmitInput { IdempotencyKey = Key() });
        Assert.Equal(RequestStatus.PendingSupervisor, (await laura.GetRequestAsync(draft.Summary.Id)).Summary.Status);
        await ApiAssert.FailsWithAsync(HttpStatusCode.Forbidden, () => laura.UpdateRequestAsync(draft.Summary.Id, TimeFlowApiFactory.Overtime(draft.Summary.StartDate)));
        await ApiAssert.FailsWithAsync(HttpStatusCode.Forbidden, () => laura.SubmitAsync(draft.Summary.Id, new SubmitInput { IdempotencyKey = Key() }));
        await ApiAssert.FailsWithAsync(HttpStatusCode.Conflict, () => ana.UpdateRequestAsync(draft.Summary.Id, TimeFlowApiFactory.Overtime(draft.Summary.StartDate)));
    }

    [Fact]
    public async Task Registrar_cannot_see_request_before_manager_approval()
    {
        var (ana, draft) = await AnaDraftAsync();
        var id = draft.Summary.Id;
        var sofia = await factory.LoginAsync(TimeFlowApiFactory.Sofia);
        await ana.SubmitAsync(id, new SubmitInput { IdempotencyKey = Key() });
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => sofia.GetRequestAsync(id));
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => sofia.AdministrativeAsync(id, new AdministrativeInput { Action = AdministrativeAction.Register }));

        await (await factory.LoginAsync(TimeFlowApiFactory.Laura)).DecideAsync(id, new DecisionInput
            { Decision = ApprovalDecisionType.Approve, SignaturePngBase64 = SyntheticSignature.Base64(1), SignatureConsent = true, ExpectedVersion = 1, IdempotencyKey = Key() });
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => sofia.GetRequestAsync(id));

        await (await factory.LoginAsync(TimeFlowApiFactory.Carlos)).DecideAsync(id, new DecisionInput
            { Decision = ApprovalDecisionType.Approve, SignaturePngBase64 = SyntheticSignature.Base64(2), SignatureConsent = true, ExpectedVersion = 1, IdempotencyKey = Key() });
        var visible = await sofia.GetRequestAsync(id);
        Assert.Equal(RequestStatus.PendingAdministrativeRegistration, visible.Summary.Status);
        Assert.True(visible.Permissions.CanAdminRegister);

        // Ana (sin rol de registro) no puede ejecutar acciones administrativas sobre su propia solicitud.
        await ApiAssert.FailsWithAsync(HttpStatusCode.Forbidden, () => ana.AdministrativeAsync(id, new AdministrativeInput { Action = AdministrativeAction.Register }));
    }

    [Fact]
    public async Task Employee_cannot_use_admin_endpoints()
    {
        var ana = await factory.LoginAsync(TimeFlowApiFactory.Ana);
        Assert.Equal(HttpStatusCode.Forbidden, (await ana.Http.GetAsync("api/v1/admin/employees")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await ana.Http.GetAsync("api/v1/admin/audit/verify")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await ana.Http.GetAsync("api/v1/admin/settings/policy")).StatusCode);
        using var create = await ana.Http.PostAsJsonAsync("api/v1/admin/employees", new EmployeeInput
        {
            EmployeeNumber = "X-1", FullName = "Escalada Indebida", Email = "x1@" + TimeFlowApiFactory.Domain, DepartmentId = 1, Roles = UserRole.ProductAdmin
        }, TimeFlowJson.Options);
        Assert.Equal(HttpStatusCode.Forbidden, create.StatusCode);

        var admin = await factory.LoginAsync(TimeFlowApiFactory.Admin);
        Assert.Equal(HttpStatusCode.OK, (await admin.Http.GetAsync("api/v1/admin/employees")).StatusCode);
        var verify = await admin.Http.GetFromJsonAsync<AuditVerificationDto>("api/v1/admin/audit/verify", TimeFlowJson.Options);
        Assert.True(verify!.IsValid, verify.Message);
    }

    [Fact]
    public async Task Manipulated_attachment_id_returns_404()
    {
        var (ana, draft) = await AnaDraftAsync();
        var uploaded = await ana.UploadAttachmentAsync(draft.Summary.Id, new MemoryStream(SmallPdf), "soporte.pdf", "application/pdf");
        Assert.Equal(SmallPdf, await ana.DownloadAttachmentAsync(uploaded.Id));

        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => ana.DownloadAttachmentAsync(Guid.NewGuid()));
        Assert.Equal(HttpStatusCode.NotFound, (await ana.Http.DeleteAsync($"api/v1/requests/{draft.Summary.Id}/attachments/{Guid.NewGuid()}")).StatusCode);

        // Otro solicitante no puede descargar ni borrar el adjunto de Ana adivinando el id.
        var other = await factory.LoginAsync(await factory.CreateEmployeeAsync());
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => other.DownloadAttachmentAsync(uploaded.Id));
        Assert.Equal(HttpStatusCode.NotFound, (await other.Http.DeleteAsync($"api/v1/requests/{draft.Summary.Id}/attachments/{uploaded.Id}")).StatusCode);
        // Ni adjuntar archivos a su solicitud.
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => other.UploadAttachmentAsync(draft.Summary.Id, new MemoryStream(SmallPdf), "x.pdf", "application/pdf"));
    }

    [Fact]
    public async Task Attachments_are_validated_by_extension_and_magic_bytes()
    {
        var (ana, draft) = await AnaDraftAsync();
        var id = draft.Summary.Id;

        var ok = await ana.UploadAttachmentAsync(id, new MemoryStream(SmallPdf), "constancia.pdf", "application/pdf");
        Assert.Equal("application/pdf", ok.ContentType);
        Assert.Equal(SmallPdf.Length, ok.SizeBytes);
        Assert.Equal(Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(SmallPdf)), ok.Sha256);

        var fake = await ApiAssert.FailsWithAsync(HttpStatusCode.UnprocessableEntity, () =>
            ana.UploadAttachmentAsync(id, new MemoryStream("MZ esto no es un PDF, es un ejecutable disfrazado"u8.ToArray()), "factura.pdf", "application/pdf"));
        Assert.Contains("no corresponde a su extensión", fake.Message);

        var exe = await ApiAssert.FailsWithAsync(HttpStatusCode.UnprocessableEntity, () =>
            ana.UploadAttachmentAsync(id, new MemoryStream([0x4D, 0x5A, 0x90, 0x00, 0x03, 0x00]), "setup.exe", "application/octet-stream"));
        Assert.Contains("Tipo de archivo no permitido", exe.Message);

        await ApiAssert.FailsWithAsync(HttpStatusCode.UnprocessableEntity, () =>
            ana.UploadAttachmentAsync(id, new MemoryStream(SmallPdf), "../../etc/passwd.exe", "application/pdf"));

        var detail = await ana.GetRequestAsync(id);
        Assert.Single(detail.Attachments);
        Assert.Equal("constancia.pdf", detail.Attachments[0].FileName);

        // Los adjuntos se guardan con nombre aleatorio dentro del DataRoot (nunca el nombre original).
        var stored = Directory.GetFiles(Path.Combine(factory.DataRoot, "attachments"), "*", SearchOption.AllDirectories);
        Assert.DoesNotContain(stored, f => Path.GetFileName(f).Contains("constancia"));
    }

    [Fact]
    public async Task Public_verification_returns_no_personal_data_and_requires_correct_code()
    {
        var (ana, draft) = await AnaDraftAsync();
        var id = draft.Summary.Id;
        var anon = factory.Anonymous();

        // Un borrador no es verificable.
        Assert.Equal(HttpStatusCode.NotFound, (await anon.Http.GetAsync($"api/v1/verify/{draft.Summary.Folio}?c={draft.ContentHash[..16]}")).StatusCode);

        await ana.SubmitAsync(id, new SubmitInput { IdempotencyKey = Key() });
        await (await factory.LoginAsync(TimeFlowApiFactory.Laura)).DecideAsync(id, new DecisionInput
            { Decision = ApprovalDecisionType.Approve, SignaturePngBase64 = SyntheticSignature.Base64(5), SignatureConsent = true, ExpectedVersion = 1, IdempotencyKey = Key() });
        var detail = await ana.GetRequestAsync(id);
        var folio = detail.Summary.Folio;

        using var response = await anon.Http.GetAsync($"api/v1/verify/{folio}?c={detail.ContentHash[..16]}");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var json = await response.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(json);
        var props = doc.RootElement.EnumerateObject().Select(p => p.Name.ToLowerInvariant()).ToHashSet();
        Assert.Equal(new HashSet<string> { "folio", "statuslabel", "kindlabel", "contentintact", "validsignatures", "lastdecisionutc", "message" }, props);
        foreach (var pii in new[] { "Ana", "Torres", "Laura", "ana.empleada", TimeFlowApiFactory.Domain, "P-0100", detail.Summary.Reason, "Plataforma" })
            Assert.DoesNotContain(pii, json, StringComparison.OrdinalIgnoreCase);
        var dto = JsonSerializer.Deserialize<VerificationDto>(json, TimeFlowJson.Options)!;
        Assert.Equal(folio, dto.Folio);
        Assert.True(dto.ContentIntact);
        Assert.Equal(1, dto.ValidSignatures);

        Assert.Equal(HttpStatusCode.NotFound, (await anon.Http.GetAsync($"api/v1/verify/{folio}?c=0000000000000000")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await anon.Http.GetAsync($"api/v1/verify/{folio}?c={detail.ContentHash[..8]}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await anon.Http.GetAsync($"api/v1/verify/{folio}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await anon.Http.GetAsync($"api/v1/verify/TF-1999-000001?c={detail.ContentHash[..16]}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await anon.Http.GetAsync($"api/v1/verify/no-es-folio?c={detail.ContentHash[..16]}")).StatusCode);
    }

    [Fact]
    public async Task Responses_include_security_headers()
    {
        var anon = factory.Anonymous();
        using var r = await anon.Http.GetAsync("health");
        Assert.Equal("nosniff", r.Headers.GetValues("X-Content-Type-Options").Single());
        Assert.Equal("DENY", r.Headers.GetValues("X-Frame-Options").Single());
        Assert.Contains("frame-ancestors 'none'", r.Headers.GetValues("Content-Security-Policy").Single());
    }
}
