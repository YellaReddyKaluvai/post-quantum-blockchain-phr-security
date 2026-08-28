const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

// FastAPI returns `detail` as a plain string for HTTPException, but as an
// array of {msg, loc} objects for Pydantic validation (422) errors. Always
// route through this so a validation failure never renders as
// "[object Object]" in the UI.
function extractErrorDetail(err: unknown, fallback: string): string {
  const detail = (err as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d))).join("; ");
  }
  return fallback;
}

// Cookie names shared with the backend (see backend/app/security.py SESSION_COOKIE_NAME)
// and the Next.js middleware. Keep these three in sync when renaming.
export const TOKEN_COOKIE = "quantumcare_token";
export const ROLE_COOKIE = "quantumcare_role";
export const USER_ID_COOKIE = "quantumcare_user_id";

export function setAuthCookies(accessToken: string, role: string, userId: string) {
  const secure = typeof window !== "undefined" && window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${TOKEN_COOKIE}=${accessToken}; Path=/; SameSite=Lax${secure}`;
  document.cookie = `${ROLE_COOKIE}=${encodeURIComponent(role)}; Path=/; SameSite=Lax${secure}`;
  document.cookie = `${USER_ID_COOKIE}=${encodeURIComponent(userId)}; Path=/; SameSite=Lax${secure}`;
}

export function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

export function getAuthToken(): string | null {
  return getCookie(TOKEN_COOKIE);
}

export function clearAuthCookies() {
  [TOKEN_COOKIE, ROLE_COOKIE, USER_ID_COOKIE].forEach((name) => {
    document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`;
  });
}

// Sessions expire after 30 minutes. Without this, an expired token surfaced as
// an empty list or a blank card — indistinguishable from "you have no data" —
// so the app looked broken rather than logged out. Redirect once, with a note
// explaining why, and preserve where they were so they land back there.
let redirectingToLogin = false;

function handleSessionExpired() {
  if (typeof window === "undefined" || redirectingToLogin) return;
  redirectingToLogin = true;
  clearAuthCookies();
  const from = window.location.pathname + window.location.search;
  const params = new URLSearchParams({ reason: "expired" });
  // Only round-trip in-app paths, never an absolute URL from elsewhere.
  if (from.startsWith("/") && !from.startsWith("//") && !from.startsWith("/login")) {
    params.set("from", from);
  }
  window.location.replace(`/login?${params.toString()}`);
}

export class SessionExpiredError extends Error {
  constructor() {
    super("Your session has expired. Please sign in again.");
    this.name = "SessionExpiredError";
  }
}

async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(url, { ...options, headers });

  // 401 means the token is gone or expired. 403 is a genuine permission
  // decision and must NOT be treated as expiry — that would bounce a user to
  // login for something they simply aren't allowed to do.
  if (response.status === 401) {
    handleSessionExpired();
    throw new SessionExpiredError();
  }

  return response;
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
  const expire = "; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;";
  for (const name of [TOKEN_COOKIE, ROLE_COOKIE, USER_ID_COOKIE]) {
    document.cookie = `${name}=${expire}`;
  }
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(ROLE_COOKIE);
    localStorage.removeItem(USER_ID_COOKIE);
    localStorage.removeItem(TOKEN_COOKIE);
  }
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

export async function getBlockchainStatus() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/blockchain/status`);
  if (!response.ok) throw new Error("Failed to fetch blockchain status");
  return response.json();
}

export async function getStorageStatus() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/admin/storage/status`);
  if (!response.ok) throw new Error("Failed to fetch storage status");
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

export async function downloadPatientLabReport(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/lab-reports/${id}/download`);
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.detail || "Failed to securely decrypt and download lab report");
  }
  return response.blob();
}

export async function verifyPatientLabReport(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/lab-reports/${id}/verify`);
  if (!response.ok) throw new Error("Failed to verify lab report");
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

export async function getPatientVitals() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/vitals`);
  if (!response.ok) throw new Error("Failed to fetch vitals");
  return response.json();
}

export async function getAvailableDoctors() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/doctors`);
  if (!response.ok) throw new Error("Failed to fetch doctors");
  return response.json();
}

export async function createPatientAppointment(data: {
  doctor_id: string;
  department: string;
  appointment_date: string;
  appointment_time: string;
  notes?: string;
}) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/patient/appointments`, {
    method: "POST",
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.detail?.[0]?.msg || err?.detail || "Failed to book appointment");
  }
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

export async function searchDoctorPatients(query: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/patients/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) throw new Error("Failed to search patients");
  return response.json();
}

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

function extractErrorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ") || fallback;
  }
  return fallback;
}

export async function createDiagnosis(patientId: string, data: Record<string, unknown>) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/patients/${patientId}/diagnosis`, {
    method: "POST", body: JSON.stringify(data)
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(err, "Failed to create diagnosis"));
  }
  return response.json();
}

export async function createPrescription(patientId: string, data: Record<string, unknown>) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/patients/${patientId}/prescription`, {
    method: "POST", body: JSON.stringify(data)
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(err, "Failed to create prescription"));
  }
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

export async function downloadDoctorLabReport(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/reports/${id}/download`);
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.detail || "Failed to securely decrypt and download lab report");
  }
  return response.blob();
}

export async function downloadLabTechReport(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/reports/${id}/download`);
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorDetail(err, "Failed to decrypt and open the report"));
  }
  return response.blob();
}

export async function verifyDoctorLabReport(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/reports/${id}/verify`);
  if (!response.ok) throw new Error("Failed to verify lab report");
  return response.json();
}

export async function getDoctorLabPanels() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/lab-panels`);
  if (!response.ok) throw new Error("Failed to fetch investigation panels");
  return response.json();
}

export async function getDoctorLabRequests(status?: string) {
  const query = status ? `?status_filter=${encodeURIComponent(status)}` : "";
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/requests${query}`);
  if (!response.ok) throw new Error("Failed to fetch lab test requests");
  return response.json();
}

export async function requestLabTest(data: {
  patient_id: string;
  panel_code: string;
  test_name?: string;
  priority?: string;
  clinical_notes?: string;
}) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/requests`, {
    method: "POST",
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorDetail(err, "Failed to request laboratory test"));
  }
  return response.json();
}

export async function getDoctorDocuments() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/doctor/documents`);
  if (!response.ok) throw new Error("Failed to fetch documents");
  return response.json();
}

export async function createMedicalDocument(data: Record<string, unknown>) {
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

// ─── Lab Technician API Functions ───────────────────────────────────────────

export async function getLabTechProfile() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/profile`);
  if (!response.ok) throw new Error("Failed to fetch lab tech profile");
  return response.json();
}

export async function getLabTechDashboardSummary() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/dashboard/summary`);
  if (!response.ok) throw new Error("Failed to fetch lab dashboard summary");
  return response.json();
}

export async function getLabTestRequests() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/requests`);
  if (!response.ok) throw new Error("Failed to fetch lab test requests");
  return response.json();
}

export async function updateLabTestRequestStatus(id: string, status: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/requests/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status })
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorDetail(err, "Failed to update test request status"));
  }
  return response.json();
}

export async function getLabTestRequestDetail(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/requests/${id}`);
  if (!response.ok) throw new Error("Failed to fetch test request detail");
  return response.json();
}

export async function getLabReportTemplates() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/report-templates`);
  if (!response.ok) throw new Error("Failed to fetch report templates");
  return response.json();
}

export async function getLabReportTemplate(panelCode: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/report-templates/${panelCode}`);
  if (!response.ok) throw new Error("Failed to fetch report template");
  return response.json();
}

export async function searchPatientsForLab(query: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/patients/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) throw new Error("Failed to search patients");
  return response.json();
}

export async function createStructuredLabReport(data: {
  request_id?: string;
  patient_id?: string;
  panel_code: string;
  values: Record<string, unknown>;
  remarks?: string;
}) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/reports/create`, {
    method: "POST",
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorDetail(err, "Failed to finalize the laboratory report"));
  }
  return response.json();
}


export async function getLabTechReports() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/reports`);
  if (!response.ok) throw new Error("Failed to fetch lab reports");
  return response.json();
}

export async function getLabTechReportDetail(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/reports/${id}`);
  if (!response.ok) throw new Error("Failed to fetch lab report details");
  return response.json();
}

export async function uploadImagingReport(data: Record<string, unknown>) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/imaging/upload`, {
    method: "POST",
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error("Failed to upload imaging report");
  return response.json();
}


export async function getImagingReports() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/imaging`);
  if (!response.ok) throw new Error("Failed to fetch imaging reports");
  return response.json();
}

// Images are encrypted at rest and are not included in the list response, so
// they are decrypted one at a time, only when actually viewed.
export async function getImagingImage(id: string): Promise<{ image_data: string; encrypted: boolean }> {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/imaging/${id}/image`);
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(err, "Failed to decrypt image"));
  }
  return response.json();
}

export async function getLabTechNotifications() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/notifications`);
  if (!response.ok) throw new Error("Failed to fetch notifications");
  return response.json();
}

export async function markLabNotificationRead(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/notifications/${id}/read`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to mark notification as read");
  return response.json();
}

export async function clearLabNotifications() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/lab-tech/notifications/clear`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to clear notifications");
  return response.json();
}

// ─── Nurse ────────────────────────────────────────────────────────────────

export async function getNurseProfile() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/profile`);
  if (!response.ok) throw new Error("Failed to fetch profile");
  return response.json();
}

export async function getNurseDashboardSummary() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/dashboard/summary`);
  if (!response.ok) throw new Error("Failed to fetch dashboard summary");
  return response.json();
}

export async function getNursePatients() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/patients`);
  if (!response.ok) throw new Error("Failed to fetch patients");
  return response.json();
}

export async function searchNursePatients(query: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/patients/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) throw new Error("Failed to search patients");
  return response.json();
}

export async function getNursePatientDetail(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/patients/${id}`);
  if (!response.ok) throw new Error("Failed to fetch patient details");
  return response.json();
}

export async function recordPatientVitals(patientId: string, data: Record<string, unknown>) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/patients/${patientId}/vitals`, {
    method: "POST", body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(err, "Failed to record vitals"));
  }
  return response.json();
}

export async function addNursingNote(patientId: string, data: Record<string, unknown>) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/patients/${patientId}/notes`, {
    method: "POST", body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(err, "Failed to add note"));
  }
  return response.json();
}

export async function administerMedication(patientId: string, prescriptionId: string, data: Record<string, unknown>) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/patients/${patientId}/medications/${prescriptionId}/administer`, {
    method: "POST", body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(err, "Failed to record administration"));
  }
  return response.json();
}

export async function getNurseNotifications() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/notifications`);
  if (!response.ok) throw new Error("Failed to fetch notifications");
  return response.json();
}

export async function markNurseNotificationRead(id: string) {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/notifications/${id}/read`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to mark notification as read");
  return response.json();
}

export async function clearNurseNotifications() {
  const response = await fetchWithAuth(`${backendBaseUrl}/api/nurse/notifications/clear`, { method: "POST" });
  if (!response.ok) throw new Error("Failed to clear notifications");
  return response.json();
}


