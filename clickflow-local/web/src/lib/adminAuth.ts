const TOKEN_KEY = "cf_admin_token";
const BUSINESS_NAME_KEY = "cf_admin_business_name";

export function getAdminToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAdminSession(token: string, businessName: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(BUSINESS_NAME_KEY, businessName);
}

export function getAdminBusinessName(): string | null {
  return localStorage.getItem(BUSINESS_NAME_KEY);
}

export function clearAdminSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(BUSINESS_NAME_KEY);
}
