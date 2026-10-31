namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>Avisos breves (toasts) mostrados por el layout principal.</summary>
public sealed class ToastService
{
    private readonly Lock _gate = new();
    private readonly List<Toast> _items = [];

    public event Action? Changed;

    public IReadOnlyList<Toast> Items
    {
        get { lock (_gate) return [.. _items]; }
    }

    /// <param name="tone">success | info | warning | danger (mismos tonos del sistema de diseño).</param>
    public void Show(string message, string tone = "info", string? link = null, TimeSpan? duration = null)
    {
        var toast = new Toast(Guid.NewGuid(), message, tone, link);
        lock (_gate)
        {
            _items.Add(toast);
            if (_items.Count > 3) _items.RemoveAt(0);
        }
        Changed?.Invoke();
        _ = DismissLaterAsync(toast.Id, duration ?? TimeSpan.FromSeconds(5));
    }

    public void Dismiss(Guid id)
    {
        bool removed;
        lock (_gate) removed = _items.RemoveAll(t => t.Id == id) > 0;
        if (removed) Changed?.Invoke();
    }

    private async Task DismissLaterAsync(Guid id, TimeSpan delay)
    {
        await Task.Delay(delay);
        Dismiss(id);
    }
}

public sealed record Toast(Guid Id, string Message, string Tone, string? Link);
