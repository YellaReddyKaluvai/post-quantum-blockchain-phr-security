from datetime import datetime, date
from typing import Any, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# Roles a member of the public may request during self-registration.
# 'Administrator' is deliberately excluded: admin accounts are provisioned
# out-of-band (seed_admin.py), never through the public registration form.
SELF_REGISTERABLE_ROLES = {"Patient", "Doctor", "Nurse", "Lab Technician"}

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

    @field_validator("role")
    @classmethod
    def role_must_be_self_registerable(cls, v: str) -> str:
        normalized = v.strip().title() if v else v
        # 'Lab Technician'.title() is already correct; guard the rest explicitly.
        if normalized not in SELF_REGISTERABLE_ROLES:
            raise ValueError(
                "Invalid role. Choose one of: " + ", ".join(sorted(SELF_REGISTERABLE_ROLES))
            )
        return normalized

    @model_validator(mode="after")
    def enforce_role_specific_fields(self):
        # Specialization is a clinical field that only applies to Doctors.
        if self.role != "Doctor":
            self.specialization = None
        elif not (self.specialization or "").strip():
            raise ValueError("Specialization is required for the Doctor role.")

        # Blood group is only collected for Patients.
        if self.role != "Patient":
            self.blood_group = None

        return self

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

# The patient dashboard groups its cards into sections; the response is nested
# to match those cards one-for-one so the UI never has to reshape the payload.
class PatientInfoSection(BaseModel):
    name: str
    user_id: Optional[str] = None
    blood_group: Optional[str] = None
    assigned_doctor: Optional[str] = None


class MedicalSummarySection(BaseModel):
    latest_diagnosis: Optional[str] = None
    current_treatment: Optional[str] = None
    latest_prescription: Optional[str] = None


class ReportsSummarySection(BaseModel):
    total: int = 0
    pending: int = 0
    latest_report: Optional[str] = None
    latest_report_date: Optional[datetime] = None


class AppointmentsSummarySection(BaseModel):
    upcoming_date: Optional[date] = None
    upcoming_time: Optional[str] = None
    upcoming_doctor: Optional[str] = None
    upcoming_department: Optional[str] = None
    previous_visit_date: Optional[date] = None
    previous_doctor: Optional[str] = None


class PatientActivityItem(BaseModel):
    title: Optional[str] = None
    # 'description' mirrors the notification body; the dashboard timeline renders
    # this field directly.
    description: Optional[str] = None
    created_at: Optional[datetime] = None


class PatientDashboardSummary(BaseModel):
    full_name: str
    patient_info: PatientInfoSection
    medical_summary: MedicalSummarySection
    reports_summary: ReportsSummarySection
    appointments_summary: AppointmentsSummarySection
    recent_activities: list[PatientActivityItem] = []

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
    patient_name: Optional[str] = None
    patient_user_id: Optional[str] = None
    upload_date: Optional[datetime] = None
    # Audit provenance. Absent values are meaningful — they mean the report
    # genuinely was not anchored or has no cloud copy — so the UI must render
    # them as such rather than substituting a plausible-looking placeholder.
    document_hash: Optional[str] = None
    blockchain_tx_hash: Optional[str] = None
    anchored_on: Optional[str] = None
    ipfs_cid: Optional[str] = None
    s3_key: Optional[str] = None
    kem_algorithm: Optional[str] = None
    signature_algorithm: Optional[str] = None

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

class AvailableDoctorItem(BaseModel):
    id: str
    full_name: str
    specialization: Optional[str] = None

class CreateAppointmentRequest(BaseModel):
    doctor_id: str
    department: str
    appointment_date: date
    appointment_time: str
    notes: Optional[str] = None

    @field_validator("appointment_date")
    @classmethod
    def date_not_in_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("Appointment date cannot be in the past.")
        return v

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

class LabTechProfile(BaseModel):
    id: str
    user_id: Optional[str] = None
    full_name: str
    email: str
    role: str
    gender: str
    department: Optional[str] = "Central Laboratory"
    reports_generated: int = 0
    status: str
    created_at: Optional[datetime] = None

class LabTechDashboardSummary(BaseModel):
    tests_assigned_today: int = 0
    reports_generated_today: int = 0
    pending_test_requests: int = 0
    reports_shared: int = 0
    reports_awaiting_review: int = 0
    recent_activities: list = []

class LabTestRequestItem(BaseModel):
    id: str
    patient_id: str
    patient_name: Optional[str] = None
    patient_user_id: Optional[str] = None
    doctor_id: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_user_id: Optional[str] = None
    test_name: str
    panel_code: Optional[str] = None
    priority: str
    status: str
    clinical_notes: Optional[str] = None
    requested_date: Optional[datetime] = None
    report_id: Optional[str] = None          # set once a report is finalised
    report_no: Optional[str] = None

class CreateLabTestRequest(BaseModel):
    patient_id: str
    panel_code: Optional[str] = None   # which report form the technician should open
    test_name: Optional[str] = None    # defaults to the panel's name when omitted
    priority: str = "Routine"
    clinical_notes: Optional[str] = None

    @model_validator(mode="after")
    def require_panel_or_test_name(self):
        if not (self.panel_code or self.test_name):
            raise ValueError("Either panel_code or test_name must be supplied.")
        return self

class CreateStructuredLabReportRequest(BaseModel):
    """Finalisation payload for a laboratory report.

    ``request_id`` binds the report to the doctor's original test request,
    which is what fixes the patient and referring doctor. ``patient_id`` is
    accepted only for direct (walk-in) reports raised without a request.
    """
    request_id: Optional[str] = None
    patient_id: Optional[str] = None
    panel_code: str
    values: dict[str, Any] = {}
    remarks: Optional[str] = None
    collected_at: Optional[datetime] = None

    @model_validator(mode="after")
    def require_a_subject(self):
        if not (self.request_id or self.patient_id):
            raise ValueError("Either request_id or patient_id must be supplied.")
        return self


class LabPanelSummary(BaseModel):
    code: str
    name: str
    short_name: str
    category: str
    layout: str
    specimen: str


class FinalizedReportResponse(BaseModel):
    status: str
    report_id: str
    report_no: str
    accession: str
    panel_code: str
    patient_user_id: Optional[str] = None
    document_hash: str
    signature_algorithm: Optional[str] = None
    kem_algorithm: Optional[str] = None
    blockchain_tx_hash: Optional[str] = None
    anchored_on: Optional[str] = None
    ipfs_cid: Optional[str] = None
    s3_key: Optional[str] = None
    notified: list[str] = []


class ReportVerification(BaseModel):
    report_id: str
    report_no: Optional[str] = None
    document_hash: Optional[str] = None
    hash_matches: bool
    signature_valid: bool
    # True/False when an on-chain anchor was actually read back and compared;
    # None when the report was only locally anchored or the chain is
    # unreachable — "unknown" must never be presented as "verified".
    blockchain_verified: Optional[bool] = None
    signature_algorithm: Optional[str] = None
    kem_algorithm: Optional[str] = None
    signed_by: Optional[str] = None
    blockchain_tx_hash: Optional[str] = None
    anchored_on: Optional[str] = None
    verified_at: datetime
    detail: str

class CreateImagingReportRequest(BaseModel):
    patient_id: str
    scan_region: str
    exam_type: str  # MRI, X-Ray, CT Scan, Ultrasound
    clinical_history: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None
    recommendations: Optional[str] = None
    image_data: Optional[str] = None

class ImagingReportItem(BaseModel):
    id: str
    patient_name: Optional[str] = None
    patient_user_id: Optional[str] = None
    scan_region: str
    exam_type: str
    clinical_history: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None
    recommendations: Optional[str] = None
    # The image itself is never included in list responses: it is encrypted at
    # rest and decrypting every study just to render a list would be both
    # wasteful and an unnecessary exposure. Fetch it per-study from
    # /api/lab-tech/imaging/{id}/image instead.
    has_image: bool = False
    document_hash: Optional[str] = None
    kem_algorithm: Optional[str] = None
    signature_algorithm: Optional[str] = None
    blockchain_tx_hash: Optional[str] = None
    created_at: Optional[datetime] = None


# ─── Nurse module ─────────────────────────────────────────────────────────────

class NurseProfile(BaseModel):
    id: str
    user_id: Optional[str] = None
    full_name: str
    email: str
    role: str
    gender: str
    ward: str = "General Ward"
    status: str
    created_at: Optional[datetime] = None


class NurseDashboardSummary(BaseModel):
    patients_attended_today: int = 0
    vitals_recorded_today: int = 0
    notes_added_today: int = 0
    medications_administered_today: int = 0
    recent_activities: list[PatientActivityItem] = []


class NursePatientListItem(BaseModel):
    id: str
    user_id: Optional[str] = None
    full_name: str
    gender: str
    blood_group: Optional[str] = None
    last_recorded_at: Optional[datetime] = None
    status: str


class PatientVitalsRecord(BaseModel):
    id: str
    temperature_celsius: Optional[float] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    heart_rate: Optional[int] = None
    spo2: Optional[int] = None
    respiratory_rate: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    notes: Optional[str] = None
    recorded_at: Optional[datetime] = None
    nurse_name: Optional[str] = None


# Bounds catch fat-finger entry (e.g. "990" instead of "99" for SpO2) at the
# point of capture, since these numbers can directly steer clinical decisions.
class CreateVitalsRequest(BaseModel):
    temperature_celsius: Optional[float] = Field(default=None, ge=25.0, le=45.0)
    blood_pressure_systolic: Optional[int] = Field(default=None, ge=40, le=300)
    blood_pressure_diastolic: Optional[int] = Field(default=None, ge=20, le=200)
    heart_rate: Optional[int] = Field(default=None, ge=20, le=300)
    spo2: Optional[int] = Field(default=None, ge=0, le=100)
    respiratory_rate: Optional[int] = Field(default=None, ge=4, le=80)
    weight_kg: Optional[float] = Field(default=None, gt=0, le=500)
    height_cm: Optional[float] = Field(default=None, gt=0, le=300)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one_reading(self):
        fields = (
            self.temperature_celsius, self.blood_pressure_systolic, self.blood_pressure_diastolic,
            self.heart_rate, self.spo2, self.respiratory_rate, self.weight_kg, self.height_cm,
        )
        if all(v is None for v in fields):
            raise ValueError("At least one vital reading must be provided.")
        return self


class NursingNoteRecord(BaseModel):
    id: str
    note_type: str
    content: str
    created_at: Optional[datetime] = None
    nurse_name: Optional[str] = None


class CreateNursingNoteRequest(BaseModel):
    note_type: str = "Observation"
    content: str = Field(min_length=1)

    @field_validator("note_type")
    @classmethod
    def valid_note_type(cls, v: str) -> str:
        allowed = {"Observation", "Care", "Incident"}
        if v not in allowed:
            raise ValueError(f"note_type must be one of {sorted(allowed)}")
        return v


class ActivePrescriptionForNurse(BaseModel):
    id: str
    medicine_name: str
    dosage: str
    frequency: str
    duration: str
    instructions: Optional[str] = None
    prescribed_date: Optional[date] = None
    last_administered_at: Optional[datetime] = None
    last_administered_status: Optional[str] = None


class MedicationAdministrationRecord(BaseModel):
    id: str
    prescription_id: str
    medicine_name: str
    dosage: str
    status: str
    remarks: Optional[str] = None
    administered_at: Optional[datetime] = None
    nurse_name: Optional[str] = None


class CreateMedicationAdministrationRequest(BaseModel):
    status: str = "Administered"
    remarks: Optional[str] = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        allowed = {"Administered", "Refused", "Held", "Missed"}
        if v not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return v


class NursePatientDetail(BaseModel):
    profile: NursePatientListItem
    vitals_history: list[PatientVitalsRecord] = []
    nursing_notes: list[NursingNoteRecord] = []
    active_prescriptions: list[ActivePrescriptionForNurse] = []


# ─── Consent & emergency access ──────────────────────────────────────────────

class ConsentEntry(BaseModel):
    """One clinician's standing access to a patient's records."""
    doctor_id: str
    doctor_user_id: Optional[str] = None
    doctor_name: str
    specialization: Optional[str] = None
    # How the relationship arose, so a patient can see why this clinician
    # appears at all rather than being asked to trust a bare list.
    relationship: str
    status: str                      # Authorized | Revoked
    revoked_at: Optional[datetime] = None
    emergency_override_until: Optional[datetime] = None


class RevokeConsentRequest(BaseModel):
    reason: Optional[str] = None


class EmergencyAccessRequest(BaseModel):
    patient_id: str
    reason: str = Field(min_length=10)
    duration_hours: int = Field(default=4, ge=1, le=24)

    @field_validator("reason")
    @classmethod
    def reason_must_be_substantive(cls, v: str) -> str:
        # Break-glass access is permanently recorded and reviewed. A blank or
        # throwaway justification defeats the point of recording it.
        if len(v.strip()) < 10:
            raise ValueError("Give a clinical reason of at least 10 characters.")
        return v.strip()


class EmergencyAccessRecord(BaseModel):
    id: str
    patient_id: str
    patient_name: Optional[str] = None
    patient_user_id: Optional[str] = None
    requester_id: str
    requester_name: Optional[str] = None
    requester_user_id: Optional[str] = None
    reason: str
    status: str
    blockchain_tx_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = False
