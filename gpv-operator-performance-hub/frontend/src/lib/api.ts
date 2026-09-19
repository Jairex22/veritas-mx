const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const TOKEN_KEY = "gpv_token";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(
      "No fue posible comunicarse con el servidor. Verifica tu conexión o que el backend esté corriendo.",
      0
    );
  }

  if (response.status === 401) {
    clearToken();
    throw new ApiError("Tu sesión expiró. Inicia sesión nuevamente.", 401);
  }

  if (!response.ok) {
    let detail = "Ocurrió un error inesperado. Intenta de nuevo en unos minutos.";
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      // respuesta sin cuerpo JSON
    }
    throw new ApiError(detail, response.status);
  }

  if (response.headers.get("content-type")?.includes("text/csv")) {
    return (await response.text()) as unknown as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
};

export { API_BASE_URL };
