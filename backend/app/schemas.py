from datetime import datetime, date
from typing import Any, Optional
from pydantic import BaseModel, EmailStr, Field

class RegistrationRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=8)
    confirm_password: str
    role: str
    gender: str
    date_of_birth: str # Format: YYYY-MM-DD
    blood_group: Optional[str] = None
    specialization: Optional[str] = None

class LoginRequest(BaseModel):
    user_id: str
    password: str

class RegistrationResponse(BaseModel):
    message: str

class LoginResponse(BaseModel):
    access_token: str
    user_id: str
    public_user_id: str
    email: str
    full_name: str
    role: str
    permissions: list[str]

class PendingRegistration(BaseModel):
    id: str
    full_name: str
    email: str
    role: str
    gender: str
    date_of_birth: str # Needs to be decrypted for admin to view
    blood_group: Optional[str] = None
    specialization: Optional[str] = None
    created_at: datetime
    status: str

class AdminActionRequest(BaseModel):
    action: str # "approve" or "reject"

class AdminActionResponse(BaseModel):
    message: str
    user_id: Optional[str] = None
    email_sent: Optional[bool] = None

# Kept from previous schema for existing integrations
class ConsentActionRequest(BaseModel):
    patient_id: str
    subject_user_id: str
    subject_role: str
    status: str
    scope: dict[str, Any] = Field(default_factory=dict)

class UploadRecordRequest(BaseModel):
    patient_id: str
    record_type: str
    storage_reference: str
    encrypted_key_reference: str
    key_version: int
    blockchain_tx_hash: str | None = None

class AuditLogRequest(BaseModel):
    action_key: str
    resource_type: str | None = None
    resource_id: str | None = None
    success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

class RejectRequest(BaseModel):
    reason: Optional[str] = None

class DashboardStats(BaseModel):
    total_users: int
    total_patients: int
    total_doctors: int
    total_nurses: int
    total_lab_technicians: int
    pending_requests: int
    approved_users: int
    rejected_users: int
    disabled_users: int
    active_sessions: int
    pqc_keys_generated: int

class UserDetail(BaseModel):
    id: str
    user_id: Optional[str] = None
    full_name: str
    email: str
    role: str
    gender: str
    date_of_birth: Optional[str] = None
    blood_group: Optional[str] = None
    specialization: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    has_mlkem_keys: bool = False
    has_mldsa_keys: bool = False
    created_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None

class AuditLogEntry(BaseModel):
    id: str
    admin_user_id: Optional[str] = None
    action: str
    target_public_user_id: Optional[str] = None
    details: Optional[dict] = None
    created_at: Optional[datetime] = None

class SecurityStats(BaseModel):
    failed_login_attempts_24h: int
    disabled_accounts: int
    active_sessions: int
    total_pqc_keypairs: int
    active_crypto_identities: int

class PatientProfile(BaseModel):
    id: str
    user_id: Optional[str] = None
    full_name: str
    email: str
    role: str
    gender: str
    date_of_birth: Optional[str] = None
    blood_group: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None

class PatientDashboardSummary(BaseModel):
    full_name: str
    user_id: Optional[str] = None
    blood_group: Optional[str] = None
    assigned_doctor: Optional[str] = None
    latest_diagnosis: Optional[str] = None
    current_treatment: Optional[str] = None
    latest_prescription: Optional[str] = None
    total_reports: int = 0
    pending_reports: int = 0
    latest_report: Optional[str] = None
    upcoming_appointment: Optional[dict] = None
    previous_visit: Optional[dict] = None
    recent_activities: list = []

class DiagnosisRecord(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    symptoms: Optional[str] = None
    doctor_notes: Optional[str] = None
    recommended_tests: Optional[str] = None
    visit_date: Optional[date] = None
    doctor_name: Optional[str] = None
    created_at: Optional[datetime] = None

class LabReportItem(BaseModel):
    id: str
    report_name: str
    report_type: str
    report_id_public: Optional[str] = None
    findings: Optional[str] = None
    normal_range: Optional[str] = None
    status: str
    uploaded_by_name: Optional[str] = None
    upload_date: Optional[datetime] = None

class PrescriptionRecord(BaseModel):
    id: str
    medicine_name: str
    dosage: str
    frequency: str
    duration: str
    instructions: Optional[str] = None
    prescribed_date: Optional[date] = None
    doctor_name: Optional[str] = None

class ConsultationRecord(BaseModel):
    id: str
    consultation_date: Optional[date] = None
    symptoms: Optional[str] = None
    diagnosis_summary: Optional[str] = None
    doctor_notes: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_specialization: Optional[str] = None

class AppointmentRecord(BaseModel):
    id: str
    doctor_name: Optional[str] = None
    department: Optional[str] = None
    appointment_date: Optional[date] = None
    appointment_time: Optional[str] = None
    status: str
    notes: Optional[str] = None

class NotificationItem(BaseModel):
    id: str
    notification_type: str
    title: str
    body: str
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

class PatientSecurityInfo(BaseModel):
    user_id: Optional[str] = None
    account_status: str
    last_login: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    active_sessions: int = 0
    pqc_protection_enabled: bool = False
    account_created: Optional[datetime] = None

class DoctorProfile(BaseModel):
    id: str
    user_id: Optional[str] = None
    full_name: str
    email: str
    role: str
    gender: str
    specialization: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

class DoctorDashboardSummary(BaseModel):
    total_assigned_patients: int = 0
    todays_appointments: int = 0
    pending_reports: int = 0
    recent_diagnoses: int = 0
    recent_activities: list = []

class DoctorPatientListItem(BaseModel):
    id: str
    user_id: Optional[str] = None
    full_name: str
    gender: str
    blood_group: Optional[str] = None
    last_visit_date: Optional[date] = None
    status: str

class CreateDiagnosisRequest(BaseModel):
    title: str
    description: Optional[str] = None
    symptoms: Optional[str] = None
    doctor_notes: Optional[str] = None
    recommended_tests: Optional[str] = None
    visit_date: date

class CreatePrescriptionRequest(BaseModel):
    medicine_name: str
    dosage: str
    frequency: str
    duration: str
    instructions: Optional[str] = None
    prescribed_date: date

class CreateConsultationRequest(BaseModel):
    consultation_date: date
    symptoms: Optional[str] = None
    diagnosis_summary: Optional[str] = None
    doctor_notes: Optional[str] = None

class MedicalDocumentItem(BaseModel):
    id: str
    document_name: str
    document_type: str
    patient_name: Optional[str] = None
    upload_date: Optional[datetime] = None
    status: str

class CreateDocumentRequest(BaseModel):
    patient_id: str
    document_name: str
    document_type: str
    content: Optional[str] = None
    status: str = "Final"

class DoctorAppointmentItem(BaseModel):
    id: str
    patient_name: Optional[str] = None
    patient_id_public: Optional[str] = None
    department: Optional[str] = None
    appointment_date: Optional[date] = None
    appointment_time: Optional[str] = None
    status: str
    notes: Optional[str] = None
