const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export class ApiError extends Error {
  status: number;
  details?: unknown;
  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    // respuesta sin cuerpo JSON
  }
  if (!res.ok) {
    throw new ApiError(body?.error || "Algo salió mal. Intenta de nuevo.", res.status, body?.details);
  }
  return body as T;
}

export function publicApi(businessSlug: string) {
  const base = `/api/public/business/${encodeURIComponent(businessSlug)}`;
  return {
    getBusiness: () => request(base),
    getCatalog: (query?: string) =>
      request(`${base}/catalog${query ? `?query=${encodeURIComponent(query)}` : ""}`),
    getFaqs: () => request(`${base}/faqs`),
    quote: (lines: unknown) => request(`${base}/quote`, { method: "POST", body: JSON.stringify({ lines }) }),
    chat: (sessionId: string, message: string) =>
      request(`${base}/chat`, { method: "POST", body: JSON.stringify({ sessionId, message }) }),
    createOrder: (payload: unknown) =>
      request(`${base}/requests/order`, { method: "POST", body: JSON.stringify(payload) }),
    createAppointment: (payload: unknown) =>
      request(`${base}/requests/appointment`, { method: "POST", body: JSON.stringify(payload) }),
    createContact: (payload: unknown) =>
      request(`${base}/requests/contact`, { method: "POST", body: JSON.stringify(payload) }),
  };
}

export function adminApi(token: string | null) {
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  return {
    login: (businessSlug: string, email: string, password: string) =>
      request<{ token: string; business: { id: string; slug: string; name: string } }>("/api/admin/login", {
        method: "POST",
        body: JSON.stringify({ businessSlug, email, password }),
      }),
    me: () => request("/api/admin/me", { headers: authHeaders }),
    updateBusiness: (patch: unknown) =>
      request("/api/admin/business", { method: "PUT", headers: authHeaders, body: JSON.stringify(patch) }),
    updateHours: (hours: unknown) =>
      request("/api/admin/business/hours", { method: "PUT", headers: authHeaders, body: JSON.stringify(hours) }),
    addHourException: (exception: unknown) =>
      request("/api/admin/business/hours/exceptions", {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify(exception),
      }),
    deleteHourException: (date: string) =>
      request(`/api/admin/business/hours/exceptions/${encodeURIComponent(date)}`, {
        method: "DELETE",
        headers: authHeaders,
      }),
    pauseAi: (paused: boolean) =>
      request("/api/admin/business/pause-ai", {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ paused }),
      }),
    listCatalog: () => request("/api/admin/catalog", { headers: authHeaders }),
    createCatalogItem: (item: unknown) =>
      request("/api/admin/catalog", { method: "POST", headers: authHeaders, body: JSON.stringify(item) }),
    updateCatalogItem: (id: string, patch: unknown) =>
      request(`/api/admin/catalog/${id}`, { method: "PUT", headers: authHeaders, body: JSON.stringify(patch) }),
    deleteCatalogItem: (id: string) =>
      request(`/api/admin/catalog/${id}`, { method: "DELETE", headers: authHeaders }),
    listFaqs: () => request("/api/admin/faqs", { headers: authHeaders }),
    createFaq: (faq: unknown) =>
      request("/api/admin/faqs", { method: "POST", headers: authHeaders, body: JSON.stringify(faq) }),
    updateFaq: (id: string, patch: unknown) =>
      request(`/api/admin/faqs/${id}`, { method: "PUT", headers: authHeaders, body: JSON.stringify(patch) }),
    deleteFaq: (id: string) => request(`/api/admin/faqs/${id}`, { method: "DELETE", headers: authHeaders }),
    listRequests: (filters?: { status?: string; type?: string }) => {
      const params = new URLSearchParams(filters as Record<string, string>).toString();
      return request(`/api/admin/requests${params ? `?${params}` : ""}`, { headers: authHeaders });
    },
    setRequestStatus: (id: string, status: string, notes?: string) =>
      request(`/api/admin/requests/${id}/status`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ status, notes }),
      }),
    listConversations: () => request("/api/admin/conversations", { headers: authHeaders }),
    getConversationMessages: (id: string) =>
      request(`/api/admin/conversations/${id}/messages`, { headers: authHeaders }),
    pauseForHuman: (id: string, minutes: number) =>
      request(`/api/admin/conversations/${id}/pause-for-human`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ minutes }),
      }),
    listUnanswered: () => request("/api/admin/unanswered-questions", { headers: authHeaders }),
    resolveUnanswered: (id: string) =>
      request(`/api/admin/unanswered-questions/${id}/resolve`, { method: "POST", headers: authHeaders }),
    metrics: () => request("/api/admin/metrics", { headers: authHeaders }),
    aiUsage: () => request("/api/admin/ai-usage", { headers: authHeaders }),
  };
}
