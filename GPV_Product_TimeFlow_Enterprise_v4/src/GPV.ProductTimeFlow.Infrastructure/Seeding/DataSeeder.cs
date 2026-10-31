using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace GPV.ProductTimeFlow.Infrastructure.Seeding;

/// <summary>
/// Datos de referencia (siempre) y datos SINTÉTICOS de demostración (solo en modo DEMO).
/// Ningún nombre, correo o firma corresponde a personas reales. Dominio reservado: demo.timeflow.example.
/// </summary>
public sealed class DataSeeder(IServiceProvider services, ILogger<DataSeeder> logger)
{
    public const string DemoDomain = "demo.timeflow.example";

    public static readonly (string Email, string Name, string Role)[] DemoAccounts =
    [
        ("ana.empleada@" + DemoDomain, "Ana Torres Lozano", "Empleado"),
        ("laura.jefa@" + DemoDomain, "Laura Hernández Vega", "Jefa directa"),
        ("carlos.superior@" + DemoDomain, "Carlos Mendoza Ríos", "Jefe superior"),
        ("admin.producto@" + DemoDomain, "Miguel Ángel Ortiz Paredes", "Administrador de Producto"),
        ("registro.admin@" + DemoDomain, "Sofía Ramírez Castro", "Registro administrativo"),
        ("patricia.direccion@" + DemoDomain, "Patricia Salgado Núñez", "Jefe superior (Dirección)"),
    ];

    public async Task SeedReferenceDataAsync(CancellationToken ct = default)
    {
        using var scope = services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<ITimeFlowDbContext>();
        if (!await db.RequestTypes.AnyAsync(ct))
        {
            db.RequestTypes.AddRange(
                new RequestType { Kind = RequestKind.Overtime, Name = "Tiempo extra", Description = "Solicitud de horas adicionales a la jornada." },
                new RequestType { Kind = RequestKind.Vacation, Name = "Vacaciones", Description = "Días de vacaciones con descuento de saldo." },
                new RequestType { Kind = RequestKind.PaidLeave, Name = "Permiso con goce de sueldo", Description = "Ausencia autorizada con goce." },
                new RequestType { Kind = RequestKind.UnpaidLeave, Name = "Permiso sin goce de sueldo", Description = "Ausencia autorizada sin goce. No aplica descuentos desde la aplicación." });
        }
        if (!await db.LeaveCategories.AnyAsync(ct))
        {
            foreach (var n in new[] { "Cita médica", "Trámite personal", "Fallecimiento de familiar", "Matrimonio", "Nacimiento o adopción", "Capacitación externa" })
                db.LeaveCategories.Add(new LeaveCategory { Name = n, AppliesTo = RequestKind.PaidLeave, RequiresAttachment = n is "Fallecimiento de familiar" or "Matrimonio" });
            foreach (var n in new[] { "Asunto personal", "Viaje personal", "Trámite extraordinario", "Otro" })
                db.LeaveCategories.Add(new LeaveCategory { Name = n, AppliesTo = RequestKind.UnpaidLeave });
        }
        if (!await db.Holidays.AnyAsync(ct))
        {
            // Descansos obligatorios (LFT art. 74). Configurables: validar calendario oficial con RH cada año.
            (int Y, int M, int D, string N)[] holidays =
            [
                (2026, 1, 1, "Año Nuevo"), (2026, 2, 2, "Día de la Constitución"), (2026, 3, 16, "Natalicio de Benito Juárez"),
                (2026, 5, 1, "Día del Trabajo"), (2026, 9, 16, "Día de la Independencia"), (2026, 11, 16, "Día de la Revolución"), (2026, 12, 25, "Navidad"),
                (2027, 1, 1, "Año Nuevo"), (2027, 2, 1, "Día de la Constitución"), (2027, 3, 15, "Natalicio de Benito Juárez"),
                (2027, 5, 1, "Día del Trabajo"), (2027, 9, 16, "Día de la Independencia"), (2027, 11, 15, "Día de la Revolución"), (2027, 12, 25, "Navidad"),
            ];
            foreach (var h in holidays) db.Holidays.Add(new Holiday { Date = new DateOnly(h.Y, h.M, h.D), Name = h.N });
        }
        if (!await db.SystemSettings.AnyAsync(s => s.Key.StartsWith("Policy."), ct))
            await scope.ServiceProvider.GetRequiredService<SettingsService>().SavePolicyAsync(new PolicySettingsDto(), "Sistema", ct);
        if (!await db.Departments.AnyAsync(ct))
        {
            db.Departments.Add(new Department { Code = "PROD", Name = "Producto" });
            db.Departments.Add(new Department { Code = "ADMP", Name = "Administración de Personal" });
        }
        await db.SaveChangesAsync(ct);
    }

    public async Task SeedDemoAsync(CancellationToken ct = default)
    {
        using var scope = services.CreateScope();
        var sp = scope.ServiceProvider;
        var db = sp.GetRequiredService<ITimeFlowDbContext>();
        if (await db.Employees.AnyAsync(ct)) return;
        var demo = sp.GetRequiredService<IOptions<DemoOptions>>().Value;
        var passwords = sp.GetRequiredService<IPasswordService>();
        var clock = sp.GetRequiredService<LocalClock>();
        var hash = passwords.Hash(demo.Password);
        logger.LogInformation("Sembrando datos DEMO sintéticos ({Count} empleados)…", demo.SyntheticEmployees);

        var prod = await db.Departments.FirstAsync(d => d.Code == "PROD", ct);
        var admp = await db.Departments.FirstAsync(d => d.Code == "ADMP", ct);
        var positions = new[] { "Director(a) de Producto", "Gerente de Ingeniería de Producto", "Líder de Producto", "Ingeniero(a) de Producto",
            "Diseñador(a) UX", "Analista de Calidad de Producto", "Especialista en Documentación Técnica", "Analista de Registro Administrativo", "Administrador(a) de Sistemas de Producto" }
            .Select(n => new Position { Name = n }).ToList();
        db.Positions.AddRange(positions);
        await db.SaveChangesAsync(ct);
        Position Pos(string n) => positions.First(p => p.Name == n);

        var today = clock.Today;
        var all = new List<Employee>();
        Employee Add(string number, string name, string email, Department dept, string area, Position pos, UserRole roles, int years)
        {
            var e = new Employee
            {
                EmployeeNumber = number, FullName = name, Email = email, NormalizedEmail = email.ToLowerInvariant(), Department = dept, Area = area,
                Position = pos, HireDate = today.AddYears(-years).AddDays(-37 * (number.Sum(c => c) % 8)), IsSynthetic = true,
                User = new UserAccount { Roles = roles | UserRole.Employee, PasswordHash = hash }
            };
            all.Add(e);
            db.Employees.Add(e);
            return e;
        }

        var patricia = Add("P-0001", "Patricia Salgado Núñez", "patricia.direccion@" + DemoDomain, prod, "Dirección de Producto", Pos("Director(a) de Producto"), UserRole.SeniorManager | UserRole.DirectSupervisor, 12);
        var carlos = Add("P-0002", "Carlos Mendoza Ríos", "carlos.superior@" + DemoDomain, prod, "Ingeniería de Producto", Pos("Gerente de Ingeniería de Producto"), UserRole.SeniorManager | UserRole.DirectSupervisor, 9);
        var laura = Add("P-0003", "Laura Hernández Vega", "laura.jefa@" + DemoDomain, prod, "Ingeniería de Producto", Pos("Líder de Producto"), UserRole.DirectSupervisor, 7);
        var daniela = Add("P-0004", "Daniela Cruz Morales", "daniela.jefa@" + DemoDomain, prod, "Diseño de Producto", Pos("Líder de Producto"), UserRole.DirectSupervisor, 6);
        var valeria = Add("P-0005", "Valeria Gómez Pineda", "valeria.jefa@" + DemoDomain, prod, "Calidad de Producto", Pos("Líder de Producto"), UserRole.DirectSupervisor, 5);
        var fernanda = Add("P-0006", "Fernanda Ruiz Delgado", "fernanda.jefa@" + DemoDomain, prod, "Documentación Técnica", Pos("Líder de Producto"), UserRole.DirectSupervisor, 4);
        var admin = Add("P-0007", "Miguel Ángel Ortiz Paredes", "admin.producto@" + DemoDomain, prod, "Sistemas de Producto", Pos("Administrador(a) de Sistemas de Producto"), UserRole.ProductAdmin, 3);
        var sofia = Add("A-0001", "Sofía Ramírez Castro", "registro.admin@" + DemoDomain, admp, "Registro administrativo", Pos("Analista de Registro Administrativo"), UserRole.AdministrativeRegistrar, 4);
        var ana = Add("P-0100", "Ana Torres Lozano", "ana.empleada@" + DemoDomain, prod, "Ingeniería de Producto", Pos("Ingeniero(a) de Producto"), UserRole.None, 3);

        var supervisors = new[] { (laura, "Ingeniería de Producto", "Ingeniero(a) de Producto"), (daniela, "Diseño de Producto", "Diseñador(a) UX"),
            (valeria, "Calidad de Producto", "Analista de Calidad de Producto"), (fernanda, "Documentación Técnica", "Especialista en Documentación Técnica") };
        string[] first = ["Alejandro", "Andrea", "Arturo", "Beatriz", "Bruno", "Camila", "César", "Diana", "Diego", "Elena", "Emilio", "Estefanía", "Fabiola", "Gabriel",
            "Gloria", "Héctor", "Isabel", "Iván", "Jimena", "Jorge", "Karla", "Leonardo", "Lucía", "Manuel", "Mariana", "Mauricio", "Natalia", "Óscar", "Paola", "Pablo",
            "Regina", "Ricardo", "Rodrigo", "Sandra", "Santiago", "Ximena", "Tomás", "Úrsula", "Víctor", "Yolanda", "Zaira", "Adrián", "Brenda", "Claudia", "Eduardo"];
        string[] last = ["Aguilar", "Álvarez", "Bautista", "Cano", "Castillo", "Chávez", "Domínguez", "Escobar", "Espinoza", "Flores", "García", "Guerrero", "Gutiérrez",
            "Ibarra", "Jiménez", "Juárez", "León", "López", "Luna", "Martínez", "Medina", "Mejía", "Molina", "Navarro", "Ortega", "Pacheco", "Peña", "Ramos", "Reyes",
            "Rojas", "Salazar", "Sánchez", "Silva", "Soto", "Vargas", "Vázquez", "Velasco", "Zamora"];
        var rnd = new Random(2026);
        var synthetic = new List<(Employee E, Employee Supervisor)>();
        var target = Math.Max(0, demo.SyntheticEmployees - all.Count);
        var usedEmails = new HashSet<string>(all.Select(e => e.NormalizedEmail));
        for (var i = 0; i < target; i++)
        {
            var (sup, area, pos) = supervisors[i % supervisors.Length];
            string name, email;
            do
            {
                var f = first[rnd.Next(first.Length)];
                var l1 = last[rnd.Next(last.Length)];
                var l2 = last[rnd.Next(last.Length)];
                name = $"{f} {l1} {l2}";
                email = $"{Slug(f)}.{Slug(l1)}{rnd.Next(10, 99)}@{DemoDomain}";
            } while (!usedEmails.Add(email));
            var e = Add($"P-{1001 + i:D4}", name, email, prod, area, Pos(pos), UserRole.None, rnd.Next(0, 15));
            synthetic.Add((e, sup));
        }
        await db.SaveChangesAsync(ct);

        void Hierarchy(Employee e, Employee? sup, Employee? mgr) =>
            db.ReportingHierarchy.Add(new ReportingHierarchy { EmployeeId = e.Id, DirectSupervisorId = sup?.Id, SeniorManagerId = mgr?.Id, EffectiveFrom = today.AddYears(-1), IsCurrent = true });
        Hierarchy(patricia, null, null);
        Hierarchy(carlos, patricia, null);
        foreach (var s in new[] { laura, daniela, valeria, fernanda }) Hierarchy(s, carlos, patricia);
        Hierarchy(admin, laura, carlos);
        Hierarchy(ana, laura, carlos);
        Hierarchy(sofia, null, null);
        foreach (var (e, sup) in synthetic) Hierarchy(e, sup, carlos);

        foreach (var e in all)
        {
            var years = VacationEntitlementPolicy.CompletedYears(e.HireDate!.Value, today);
            var days = VacationEntitlementPolicy.DaysForYearsOfService(Math.Max(1, years));
            db.VacationBalances.Add(new VacationBalance { EmployeeId = e.Id, PeriodYear = today.Year, EntitledDays = days });
            db.VacationBalances.Add(new VacationBalance { EmployeeId = e.Id, PeriodYear = today.Year + 1, EntitledDays = days });
        }
        await db.SaveChangesAsync(ct);

        if (demo.SeedSampleRequests) await SeedRequestsAsync(sp, ana, laura, carlos, sofia, synthetic, ct);
        logger.LogInformation("Datos DEMO listos.");
    }

    private async Task SeedRequestsAsync(IServiceProvider sp, Employee ana, Employee laura, Employee carlos, Employee sofia,
        List<(Employee E, Employee Supervisor)> synthetic, CancellationToken ct)
    {
        var clock = sp.GetRequiredService<LocalClock>();
        var db = sp.GetRequiredService<ITimeFlowDbContext>();
        var today = clock.Today;
        Actor A(Employee e) => new(e.Id, e.FullName, e.User!.Roles, "127.0.0.1", "seed");
        var categories = await db.LeaveCategories.ToListAsync(ct);
        var paidCat = categories.First(c => c.AppliesTo == RequestKind.PaidLeave && !c.RequiresAttachment).Id;
        var unpaidCat = categories.First(c => c.AppliesTo == RequestKind.UnpaidLeave).Id;
        var sigSeed = 1;

        async Task<Guid> Flow(Employee who, Employee sup, RequestInput input, int stage, bool notify, string? endComment = null)
        {
            // stage: 0 borrador, 1 pendiente jefa, 2 pendiente jefe, 3 pendiente registro, 4 registrada, 5 completada, -1 devuelta, -2 rechazada jefa, -3 rechazada jefe
            using var scope = sp.CreateScope();
            var s = scope.ServiceProvider;
            s.GetRequiredService<NotificationDispatcher>().Suppressed = !notify;
            var wf = s.GetRequiredService<WorkflowService>();
            var id = await wf.CreateDraftAsync(A(who), input, ct);
            if (stage == 0) return id;
            await wf.SubmitAsync(A(who), id, new SubmitInput { IdempotencyKey = Guid.NewGuid().ToString("N") }, ct);
            if (stage == 1) return id;
            var detail = await s.GetRequiredService<RequestQueryService>().GetDetailAsync(A(sup), id, false, ct);
            var decision = stage switch { -1 => ApprovalDecisionType.Return, -2 => ApprovalDecisionType.Reject, _ => ApprovalDecisionType.Approve };
            await wf.DecideAsync(A(sup), id, new DecisionInput
            {
                Decision = decision, SignaturePngBase64 = decision == ApprovalDecisionType.Approve ? SyntheticSignature.Base64(sigSeed++) : null, SignatureConsent = true,
                Comment = decision == ApprovalDecisionType.Approve ? "Autorizado conforme a la planeación del área." : endComment ?? "Favor de complementar la justificación con el detalle de actividades.",
                ExpectedVersion = detail.Summary.Version, IdempotencyKey = Guid.NewGuid().ToString("N")
            }, ct);
            if (stage is 2 or -1 or -2) return id;
            var mdecision = stage == -3 ? ApprovalDecisionType.Reject : ApprovalDecisionType.Approve;
            await wf.DecideAsync(A(carlos), id, new DecisionInput
            {
                Decision = mdecision, SignaturePngBase64 = mdecision == ApprovalDecisionType.Approve ? SyntheticSignature.Base64(sigSeed++) : null, SignatureConsent = true,
                Comment = mdecision == ApprovalDecisionType.Approve ? null : "No es posible autorizar por cierre de entregables del trimestre.",
                ExpectedVersion = detail.Summary.Version, IdempotencyKey = Guid.NewGuid().ToString("N")
            }, ct);
            if (stage is 3 or -3) return id;
            await wf.AdministrativeAsync(A(sofia), id, new AdministrativeInput { Action = AdministrativeAction.Register, ExternalReference = $"REG-{today:yyyyMM}-{sigSeed:D3}" }, ct);
            if (stage == 4) return id;
            await wf.AdministrativeAsync(A(sofia), id, new AdministrativeInput { Action = AdministrativeAction.Complete }, ct);
            return id;
        }

        static RequestInput Ot(DateOnly d, int startHour, int hours, string project) => new()
        {
            Kind = RequestKind.Overtime, StartDate = d, StartTime = new TimeOnly(startHour, 0), EndTime = new TimeOnly((startHour + hours) % 24, 0),
            Reason = "Cierre de entregables del proyecto", Project = project, Activity = "Pruebas de validación y documentación de resultados del sprint."
        };
        static DateOnly NextWorkday(DateOnly d, int add)
        {
            var x = d.AddDays(add);
            while (x.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday) x = x.AddDays(1);
            return x;
        }

        // ── Escenario guiado para las cuentas DEMO ──
        await Flow(ana, laura, Ot(NextWorkday(today, -8), 18, 3, "Plataforma de configuración de producto"), 5, true);
        await Flow(ana, laura, new RequestInput { Kind = RequestKind.Vacation, StartDate = NextWorkday(today, 21), EndDate = NextWorkday(today, 23), Reason = "Vacaciones familiares programadas" }, 1, true);
        await Flow(ana, laura, new RequestInput { Kind = RequestKind.PaidLeave, StartDate = NextWorkday(today, 6), IsFullDay = false, StartTime = new TimeOnly(9, 0), EndTime = new TimeOnly(12, 0),
            Reason = "Cita médica de seguimiento", Justification = "Consulta programada con especialista del IMSS.", LeaveCategoryId = paidCat }, -1, true);
        await Flow(ana, laura, Ot(NextWorkday(today, -3), 19, 2, "Portal de documentación técnica"), 0, true);
        await Flow(ana, laura, new RequestInput { Kind = RequestKind.UnpaidLeave, StartDate = NextWorkday(today, 35), EndDate = NextWorkday(today, 35), IsFullDay = true,
            Reason = "Trámite personal fuera de la ciudad", Justification = "Trámite notarial que requiere presencia en otra entidad.", LeaveCategoryId = unpaidCat }, 2, true);

        // ── Actividad sintética del departamento ──
        var rnd = new Random(77);
        string[] projects = ["Plataforma de configuración de producto", "Portal de documentación técnica", "Validación de prototipos", "Migración de catálogo", "Pruebas de certificación"];
        int[] stages = [1, 1, 1, 2, 2, 3, 3, 4, 5, 5, 5, -1, -2, -3];
        foreach (var (e, sup) in synthetic.Take(90))
        {
            var stage = stages[rnd.Next(stages.Length)];
            var kind = rnd.Next(10);
            RequestInput input = kind switch
            {
                < 5 => Ot(NextWorkday(today, -rnd.Next(1, 25)), 17 + rnd.Next(0, 3), 1 + rnd.Next(0, 3), projects[rnd.Next(projects.Length)]),
                < 8 => new RequestInput { Kind = RequestKind.Vacation, StartDate = NextWorkday(today, 5 + rnd.Next(0, 60)), Reason = "Periodo vacacional" },
                < 9 => new RequestInput { Kind = RequestKind.PaidLeave, StartDate = NextWorkday(today, rnd.Next(1, 30)), IsFullDay = true, Reason = "Trámite personal",
                    Justification = "Trámite oficial en horario laboral.", LeaveCategoryId = paidCat },
                _ => new RequestInput { Kind = RequestKind.UnpaidLeave, StartDate = NextWorkday(today, rnd.Next(5, 40)), IsFullDay = true, Reason = "Asunto personal",
                    Justification = "Asunto familiar que requiere atención durante la jornada.", LeaveCategoryId = unpaidCat },
            };
            if (input.Kind == RequestKind.Vacation) input.EndDate = NextWorkday(input.StartDate, rnd.Next(0, 4));
            if (input.Kind is RequestKind.PaidLeave or RequestKind.UnpaidLeave) input.EndDate = input.StartDate;
            try { await Flow(e, sup, input, stage, false, "La solicitud no cumple con la anticipación requerida por el área."); }
            catch (BusinessRuleException ex) { logger.LogDebug("Solicitud sintética omitida: {Error}", ex.Message); }
        }
    }

    private static string Slug(string s)
    {
        var normalized = s.Normalize(System.Text.NormalizationForm.FormD);
        return new string(normalized.Where(c => char.IsAsciiLetter(c)).ToArray()).ToLowerInvariant();
    }
}
