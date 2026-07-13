const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export interface RegisterPayload {
  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
  role: string;
  gender: string;
  date_of_birth: string;
  blood_group: string | null;
  specialization: string | null;
}

export interface PendingRegistration {
  id: string;
  full_name: string;
  email: string;
  role: string;
  gender: string;
  date_of_birth: string;
  blood_group: string | null;
  specialization: string | null;
  created_at: string;
  status: string;
}

export interface AdminActionResponse {
  message: string;
  user_id?: string;
}

export function setAuthCookies(accessToken: string, role: string, userId: string) {
  const secure = typeof window !== "undefined" && window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `aegis_access_token=${accessToken}; Path=/; SameSite=Lax${secure}`;
  document.cookie = `aegis_role=${encodeURIComponent(role)}; Path=/; SameSite=Lax${secure}`;
  document.cookie = `aegis_user_id=${encodeURIComponent(userId)}; Path=/; SameSite=Lax${secure}`;
}

export function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

export function getAuthToken(): string | null {
  return getCookie("aegis_access_token");
}

async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(url, { ...options, headers });
}

export async function register(data: RegisterPayload) {
  const response = await fetch(`${backendBaseUrl}/api/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.detail || "Registration failed");
  }
  return response.json();
}

export async function login(user_id: string, password: string) {
  const response = await fetch(`${backendBaseUrl}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id, password }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.detail || "Login failed");
  }
  return response.json();
}

export async function logout() {
  try {
    await fetchWithAuth(`${backendBaseUrl}/api/logout`, { method: "POST" });
  } catch (e) {
    console.error("Logout API failed", e);
  }
  document.cookie = "aegis_access_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;";
  document.cookie = "aegis_role=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;";
  document.cookie = "aegis_user_id=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;";
}

export async function getProfile() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/auth/me`);
  if (!response.ok) throw new Error("Failed to fetch profile");
  return response.json();
}

export async function getAdminPending() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/registrations/pending`);
  if (!response.ok) throw new Error("Failed to fetch pending registrations");
  return response.json() as Promise<PendingRegistration[]>;
}

export async function approveRegistration(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/registrations/${id}/approve`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Failed to approve registration");
  return response.json() as Promise<AdminActionResponse>;
}

export async function rejectRegistration(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/registrations/${id}/reject`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Failed to reject registration");
  return response.json();
}
