const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

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

export async function register(data: Record<string, unknown>) {
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
  return response.json();
}

export async function approveRegistration(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/registrations/${id}/approve`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Failed to approve registration");
  return response.json();
}

export async function rejectRegistration(id: string, reason?: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/registrations/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason || null }),
  });
  if (!response.ok) throw new Error("Failed to reject registration");
  return response.json();
}

export async function getDashboardStats() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/dashboard/stats`);
  if (!response.ok) throw new Error("Failed to fetch dashboard stats");
  return response.json();
}

export async function getRecentActivity() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/dashboard/recent-activity`);
  if (!response.ok) throw new Error("Failed to fetch recent activity");
  return response.json();
}

export async function getAllRegistrations() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/registrations`);
  if (!response.ok) throw new Error("Failed to fetch registrations");
  return response.json();
}

export async function getAllUsers(params: { role?: string; status?: string; search?: string; page?: number; per_page?: number } = {}) {
  const query = new URLSearchParams();
  if (params.role) query.set("role", params.role);
  if (params.status) query.set("status", params.status);
  if (params.search) query.set("search", params.search);
  if (params.page) query.set("page", String(params.page));
  if (params.per_page) query.set("per_page", String(params.per_page));
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/users?${query.toString()}`);
  if (!response.ok) throw new Error("Failed to fetch users");
  return response.json();
}

export async function getUserDetail(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/users/${id}`);
  if (!response.ok) throw new Error("Failed to fetch user detail");
  return response.json();
}

export async function disableUser(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/users/${id}/disable`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to disable user");
  return response.json();
}

export async function enableUser(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/users/${id}/enable`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to enable user");
  return response.json();
}

export async function getAuditLogs(params: { action?: string; page?: number; per_page?: number } = {}) {
  const query = new URLSearchParams();
  if (params.action) query.set("action", params.action);
  if (params.page) query.set("page", String(params.page));
  if (params.per_page) query.set("per_page", String(params.per_page));
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/audit-logs?${query.toString()}`);
  if (!response.ok) throw new Error("Failed to fetch audit logs");
  return response.json();
}

export async function getSecurityStats() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/security/stats`);
  if (!response.ok) throw new Error("Failed to fetch security stats");
  return response.json();
}

export async function getUserEmails(userId: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/users/${userId}/emails`);
  if (!response.ok) throw new Error("Failed to fetch user email history");
  return response.json();
}

export async function resendEmail(notificationId: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/emails/${notificationId}/resend`, {
    method: "POST",
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.detail || "Failed to resend email");
  }
  return response.json();
}

// ─── Patient API Functions ───────────────────────────────────────────────────

export async function getPatientProfile() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/profile`);
  if (!response.ok) throw new Error("Failed to fetch patient profile");
  return response.json();
}

export async function getPatientDashboardSummary() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/dashboard/summary`);
  if (!response.ok) throw new Error("Failed to fetch dashboard summary");
  return response.json();
}

export async function getPatientMedicalRecords() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/medical-records`);
  if (!response.ok) throw new Error("Failed to fetch medical records");
  return response.json();
}

export async function getPatientMedicalRecordDetail(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/medical-records/${id}`);
  if (!response.ok) throw new Error("Failed to fetch medical record detail");
  return response.json();
}

export async function getPatientLabReports() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/lab-reports`);
  if (!response.ok) throw new Error("Failed to fetch lab reports");
  return response.json();
}

export async function getPatientLabReportDetail(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/lab-reports/${id}`);
  if (!response.ok) throw new Error("Failed to fetch lab report detail");
  return response.json();
}

export async function getPatientPrescriptions() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/prescriptions`);
  if (!response.ok) throw new Error("Failed to fetch prescriptions");
  return response.json();
}

export async function getPatientConsultations() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/consultations`);
  if (!response.ok) throw new Error("Failed to fetch consultations");
  return response.json();
}

export async function getPatientAppointments() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/appointments`);
  if (!response.ok) throw new Error("Failed to fetch appointments");
  return response.json();
}

export async function getPatientNotifications() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/notifications`);
  if (!response.ok) throw new Error("Failed to fetch notifications");
  return response.json();
}

export async function markNotificationRead(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/notifications/${id}/read`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to mark notification as read");
  return response.json();
}

export async function clearNotifications() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/notifications/clear`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to clear notifications");
  return response.json();
}

export async function getPatientSecurity() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/security`);
  if (!response.ok) throw new Error("Failed to fetch security info");
  return response.json();
}

// ─── Doctor API Functions ────────────────────────────────────────────────────

export async function getDoctorProfile() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/profile`);
  if (!response.ok) throw new Error("Failed to fetch doctor profile");
  return response.json();
}

export async function getDoctorDashboardSummary() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/dashboard/summary`);
  if (!response.ok) throw new Error("Failed to fetch dashboard summary");
  return response.json();
}

export async function getDoctorPatients() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/patients`);
  if (!response.ok) throw new Error("Failed to fetch patients");
  return response.json();
}

export async function getDoctorPatientDetail(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/patients/${id}`);
  if (!response.ok) throw new Error("Failed to fetch patient details");
  return response.json();
}

export async function createDiagnosis(patientId: string, data: any) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/patients/${patientId}/diagnosis`, {
    method: "POST", body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error("Failed to create diagnosis");
  return response.json();
}

export async function createPrescription(patientId: string, data: any) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/patients/${patientId}/prescription`, {
    method: "POST", body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error("Failed to create prescription");
  return response.json();
}

export async function getDoctorReports() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/reports`);
  if (!response.ok) throw new Error("Failed to fetch reports");
  return response.json();
}

export async function reviewLabReport(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/reports/${id}/review`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to review report");
  return response.json();
}

export async function getDoctorDocuments() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/documents`);
  if (!response.ok) throw new Error("Failed to fetch documents");
  return response.json();
}

export async function createMedicalDocument(data: any) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/documents`, {
    method: "POST", body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error("Failed to upload document");
  return response.json();
}

export async function getDoctorAppointments() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/appointments`);
  if (!response.ok) throw new Error("Failed to fetch appointments");
  return response.json();
}

export async function updateAppointmentStatus(id: string, action: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/appointments/${id}/${action}`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to update appointment");
  return response.json();
}

export async function getDoctorNotifications() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/notifications`);
  if (!response.ok) throw new Error("Failed to fetch notifications");
  return response.json();
}

export async function markDoctorNotificationRead(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/notifications/${id}/read`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to mark notification as read");
  return response.json();
}

export async function clearDoctorNotifications() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/notifications/clear`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to clear notifications");
  return response.json();
}
