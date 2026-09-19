import { createContext, useContext, useState, type ReactNode } from "react";
import { api, clearToken, getToken, setToken } from "./api";

interface SessionUser {
  username: string;
  display_name: string;
  role: string;
}

interface AuthContextValue {
  user: SessionUser | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const USER_KEY = "gpv_user";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(() => {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  });

  async function login(username: string, password: string) {
    const response = await api.post<{ access_token: string; display_name: string; role: string; username: string }>(
      "/api/auth/login",
      { username, password }
    );
    setToken(response.access_token);
    const sessionUser = { username: response.username, display_name: response.display_name, role: response.role };
    localStorage.setItem(USER_KEY, JSON.stringify(sessionUser));
    setUser(sessionUser);
  }

  function logout() {
    clearToken();
    localStorage.removeItem(USER_KEY);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user && !!getToken(), login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return ctx;
}
