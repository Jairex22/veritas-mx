using Microsoft.Extensions.DependencyInjection;

namespace GPV.ProductTimeFlow.Application;

public static class DependencyInjection
{
    public static IServiceCollection AddTimeFlowApplication(this IServiceCollection services)
    {
        services.AddSingleton(TimeProvider.System);
        services.AddSingleton<LocalClock>();
        services.AddSingleton<EnvironmentInfo>();
        services.AddScoped<SettingsService>();
        services.AddScoped<AuditWriter>();
        services.AddScoped<ActorGuard>();
        services.AddScoped<RequestRules>();
        services.AddScoped<NotificationDispatcher>();
        services.AddScoped<WorkflowService>();
        services.AddScoped<RequestQueryService>();
        services.AddScoped<VacationService>();
        services.AddScoped<OvertimeService>();
        services.AddScoped<NotificationService>();
        services.AddScoped<EmployeeAdminService>();
        services.AddScoped<SettingsAdminService>();
        services.AddScoped<AuditService>();
        services.AddScoped<EmailMonitorService>();
        services.AddScoped<DocumentService>();
        services.AddScoped<ExportService>();
        services.AddScoped<AuthService>();
        services.AddScoped<HealthService>();
        services.AddScoped<ReminderService>();
        return services;
    }
}
