-- Database: phr_db

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$ BEGIN
    CREATE TYPE registration_status AS ENUM ('Pending', 'Approved', 'Rejected');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('Patient', 'Doctor', 'Nurse', 'Lab Technician', 'Administrator');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE consent_status AS ENUM ('Authorized', 'Revoked', 'Emergency', 'Expired');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE notification_channel AS ENUM ('InApp', 'Email', 'Push');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Redesigned Users table
CREATE TABLE IF NOT EXISTS Users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),           -- Internal UUID (never exposed)
    user_id VARCHAR(20) UNIQUE,                                -- Public User ID (PAT-2026-000001), NULL until approved
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,                                -- Argon2 hash
    role user_role NOT NULL,
    gender VARCHAR(20) NOT NULL,
    date_of_birth_encrypted TEXT NOT NULL,                      -- AES-256 encrypted
    blood_group_encrypted TEXT,                                 -- AES-256 encrypted (patients only)
    specialization VARCHAR(255),                                -- Doctors only
    status registration_status NOT NULL DEFAULT 'Pending',
    mlkem_public_key TEXT,                                      -- Set on approval
    mlkem_private_key_encrypted TEXT,                           -- Set on approval
    mldsa_public_key TEXT,                                      -- Set on approval
    mldsa_private_key_encrypted TEXT,                           -- Set on approval
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMPTZ,
    approved_by UUID REFERENCES Users(id)
);

-- User ID sequence counters (per role, per year)
CREATE TABLE IF NOT EXISTS UserIdSequences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role_prefix VARCHAR(3) NOT NULL,      -- PAT, DOC, NUR, LAB
    year INTEGER NOT NULL,
    last_sequence INTEGER NOT NULL DEFAULT 0,
    UNIQUE(role_prefix, year)
);

-- Sessions table
CREATE TABLE IF NOT EXISTS Sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    role user_role NOT NULL,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Authentication audit logs
CREATE TABLE IF NOT EXISTS AuthLogs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES Users(id),
    public_user_id VARCHAR(20),
    action VARCHAR(50) NOT NULL,           -- LOGIN_SUCCESS, LOGIN_FAILED, LOGOUT, etc.
    ip_address INET,
    user_agent TEXT,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS MedicalRecords (
    Medical_Record_ID UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    Patient_ID UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    Uploaded_By UUID REFERENCES Users(id) ON DELETE SET NULL,
    Record_Type VARCHAR(120) NOT NULL,
    Storage_Provider VARCHAR(40) NOT NULL DEFAULT 'Firestore',
    Storage_Reference TEXT NOT NULL,
    Encrypted_Key_Reference TEXT NOT NULL,
    Key_Version INTEGER NOT NULL DEFAULT 1,
    Blockchain_Tx_Hash VARCHAR(255),
    Consent_Required BOOLEAN NOT NULL DEFAULT TRUE,
    Created_At TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Updated_At TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Consent (
    Consent_ID UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    Patient_ID UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    Subject_User_ID UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    Subject_Role VARCHAR(80) NOT NULL,
    Status consent_status NOT NULL DEFAULT 'Authorized',
    Scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    Granted_At TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Expires_At TIMESTAMP WITH TIME ZONE,
    Revoked_At TIMESTAMP WITH TIME ZONE,
    UNIQUE(Patient_ID, Subject_User_ID, Subject_Role)
);

CREATE TABLE IF NOT EXISTS EmergencyAccess (
    Emergency_Access_ID UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    Requester_ID UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    Patient_ID UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    Reason TEXT NOT NULL,
    Status consent_status NOT NULL DEFAULT 'Emergency',
    Approved_By UUID REFERENCES Users(id) ON DELETE SET NULL,
    Blockchain_Tx_Hash VARCHAR(255),
    Created_At TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Expires_At TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS Notifications (
    Notification_ID UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    User_ID UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    Channel notification_channel NOT NULL DEFAULT 'InApp',
    Notification_Type VARCHAR(120) NOT NULL,
    Title VARCHAR(255) NOT NULL,
    Body TEXT NOT NULL,
    Read_At TIMESTAMP WITH TIME ZONE,
    Created_At TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Add Disabled status to enum
DO $$ BEGIN
    ALTER TYPE registration_status ADD VALUE IF NOT EXISTS 'Disabled';
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Add rejection_reason to Users
ALTER TABLE Users ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

-- Admin Audit Logs
CREATE TABLE IF NOT EXISTS AdminAuditLogs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admin_id UUID REFERENCES Users(id),
    admin_user_id VARCHAR(20),
    action VARCHAR(100) NOT NULL,
    target_user_id UUID REFERENCES Users(id),
    target_public_user_id VARCHAR(20),
    ip_address INET,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_admin ON AdminAuditLogs(admin_id);
CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON AdminAuditLogs(created_at DESC);

-- Lab Report Type enum
DO $$ BEGIN
    CREATE TYPE lab_report_type AS ENUM (
        'CBC', 'Blood Sugar', 'Urine Test', 'Lipid Profile',
        'Liver Function', 'Kidney Function', 'ECG', 'X-Ray',
        'MRI', 'CT Scan', 'Ultrasound', 'Other'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE appointment_status AS ENUM ('Scheduled', 'Completed', 'Cancelled');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE lab_report_status AS ENUM ('Pending', 'Completed', 'Reviewed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS Diagnoses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    symptoms TEXT,
    doctor_notes TEXT,
    recommended_tests TEXT,
    visit_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS LabReports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    uploaded_by UUID REFERENCES Users(id) ON DELETE SET NULL,
    report_name VARCHAR(255) NOT NULL,
    report_type lab_report_type NOT NULL DEFAULT 'Other',
    report_id_public VARCHAR(30) UNIQUE,
    file_data TEXT,
    findings TEXT,
    normal_range TEXT,
    status lab_report_status NOT NULL DEFAULT 'Pending',
    upload_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Prescriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    medicine_name VARCHAR(255) NOT NULL,
    dosage VARCHAR(100) NOT NULL,
    frequency VARCHAR(100) NOT NULL,
    duration VARCHAR(100) NOT NULL,
    instructions TEXT,
    prescribed_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS DoctorConsultations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    consultation_date DATE NOT NULL,
    symptoms TEXT,
    diagnosis_summary TEXT,
    doctor_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    department VARCHAR(100),
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    status appointment_status NOT NULL DEFAULT 'Scheduled',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    CREATE TYPE medical_document_type AS ENUM (
        'Diagnosis Report', 'Consultation Report', 'Treatment Summary',
        'Medical Certificate', 'Referral Letter', 'Discharge Summary', 'Other'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'Pending';
ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'Confirmed';

CREATE TABLE IF NOT EXISTS MedicalDocuments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    document_name VARCHAR(255) NOT NULL,
    document_type medical_document_type NOT NULL DEFAULT 'Other',
    content TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'Final',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_medicaldocuments_doctor ON MedicalDocuments(doctor_id);
CREATE INDEX IF NOT EXISTS idx_medicaldocuments_patient ON MedicalDocuments(patient_id);
    
DO $$ BEGIN
    CREATE TYPE lab_request_priority AS ENUM ('Routine', 'Urgent', 'Emergency');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE lab_request_status AS ENUM ('Pending', 'Accepted', 'In Progress', 'Completed');
EXCEPTION WHEN duplicate_object THEN null; END $$;

CREATE TABLE IF NOT EXISTS LabTestRequests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    test_name VARCHAR(255) NOT NULL,
    priority lab_request_priority NOT NULL DEFAULT 'Routine',
    status lab_request_status NOT NULL DEFAULT 'Pending',
    clinical_notes TEXT,
    requested_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ImagingReports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    lab_tech_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    scan_region VARCHAR(100) NOT NULL,
    exam_type VARCHAR(100) NOT NULL,
    clinical_history TEXT,
    findings TEXT,
    impression TEXT,
    recommendations TEXT,
    image_data TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS structured_data JSONB;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS document_hash VARCHAR(64);
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS encrypted_aes_key TEXT;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS digital_signature TEXT;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS blockchain_tx_hash VARCHAR(66);
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS lab_tech_id UUID REFERENCES Users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_labtestrequests_patient ON LabTestRequests(patient_id);
CREATE INDEX IF NOT EXISTS idx_labtestrequests_status ON LabTestRequests(status);
CREATE INDEX IF NOT EXISTS idx_imagingreports_patient ON ImagingReports(patient_id);

CREATE INDEX IF NOT EXISTS idx_diagnoses_patient ON Diagnoses(patient_id);
CREATE INDEX IF NOT EXISTS idx_labreports_patient ON LabReports(patient_id);
CREATE INDEX IF NOT EXISTS idx_prescriptions_patient ON Prescriptions(patient_id);
CREATE INDEX IF NOT EXISTS idx_consultations_patient ON DoctorConsultations(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON Appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON Appointments(appointment_date);

CREATE INDEX IF NOT EXISTS idx_users_role ON Users(role);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON Sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auditlogs_user_id ON AuthLogs(user_id);
CREATE INDEX IF NOT EXISTS idx_records_patient_id ON MedicalRecords(Patient_ID);
CREATE INDEX IF NOT EXISTS idx_consent_patient_subject ON Consent(Patient_ID, Subject_User_ID);

-- Email Notifications
CREATE TABLE IF NOT EXISTS EmailNotifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    email_address VARCHAR(100) NOT NULL,
    notification_type VARCHAR(20) NOT NULL, -- 'APPROVAL', 'REJECTION'
    email_subject VARCHAR(255) NOT NULL,
    email_content TEXT NOT NULL,
    sent_status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- 'SENT', 'FAILED', 'PENDING'
    sent_timestamp TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_email_notifications_user ON EmailNotifications(user_id);
CREATE INDEX IF NOT EXISTS idx_email_notifications_status ON EmailNotifications(sent_status);

-- IPFS & AWS S3 Cloud Storage Columns
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS ipfs_cid VARCHAR(255);
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS s3_key VARCHAR(512);

ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS ipfs_cid VARCHAR(255);
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS s3_key VARCHAR(512);

ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS ipfs_cid VARCHAR(255);
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS s3_key VARCHAR(512);




-- ─────────────────────────────────────────────────────────────────────────────
-- Laboratory report workflow: Doctor request → Lab technician → Signed report
-- Links the report permanently to its originating request, referring doctor and
-- performing technician, and stores the hybrid-encryption material needed to
-- decrypt it later (ML-KEM ciphertext + AES-GCM nonce/tag).
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS lab_request_id UUID REFERENCES LabTestRequests(id) ON DELETE SET NULL;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS doctor_id UUID REFERENCES Users(id) ON DELETE SET NULL;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS panel_code VARCHAR(32);
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS accession_number VARCHAR(32);
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS collected_at TIMESTAMPTZ;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS finalized_at TIMESTAMPTZ;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS is_locked BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS interpretation TEXT;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS remarks TEXT;

-- Hybrid encryption material. encrypted_aes_key already exists and now holds
-- the ML-KEM ciphertext; these carry the AES-256-GCM parameters beside it.
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS encryption_nonce TEXT;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS encryption_tag TEXT;
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS kem_algorithm VARCHAR(32);
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS signature_algorithm VARCHAR(32);
ALTER TABLE LabReports ADD COLUMN IF NOT EXISTS encrypted_document TEXT;

-- One finalised report per test request.
CREATE UNIQUE INDEX IF NOT EXISTS idx_labreports_request_unique
    ON LabReports(lab_request_id) WHERE lab_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_labreports_doctor ON LabReports(doctor_id);
CREATE INDEX IF NOT EXISTS idx_labreports_labtech ON LabReports(lab_tech_id);

-- Panel selected by the doctor when raising the request, so the technician
-- opens the correct form rather than choosing one by hand.
ALTER TABLE LabTestRequests ADD COLUMN IF NOT EXISTS panel_code VARCHAR(32);
ALTER TABLE LabTestRequests ADD COLUMN IF NOT EXISTS accepted_by UUID REFERENCES Users(id) ON DELETE SET NULL;
ALTER TABLE LabTestRequests ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;
ALTER TABLE LabTestRequests ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- Blockchain / integrity anchor. One row per auditable document event; holds
-- only identifiers, action, timestamp and the SHA-256 digest. Never the
-- document itself and never key material.
CREATE TABLE IF NOT EXISTS DocumentAnchors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_type VARCHAR(40) NOT NULL,
    document_id UUID NOT NULL,
    report_id_public VARCHAR(30),
    patient_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    actor_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    actor_public_id VARCHAR(20),
    action VARCHAR(60) NOT NULL,
    document_hash VARCHAR(64) NOT NULL,
    tx_hash VARCHAR(66),
    anchored_on VARCHAR(30) NOT NULL DEFAULT 'local-simulated',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_anchors_document ON DocumentAnchors(document_id);
CREATE INDEX IF NOT EXISTS idx_anchors_patient ON DocumentAnchors(patient_id);

-- Block number is present only for genuine on-chain anchors; NULL means the
-- anchor was written locally because no chain was reachable.
ALTER TABLE DocumentAnchors ADD COLUMN IF NOT EXISTS block_number BIGINT;

-- ─────────────────────────────────────────────────────────────────────────────
-- Nurse module: vitals, nursing notes, and medication administration.
-- Nurses are not "assigned" to patients the way doctors are (via diagnoses);
-- any approved nurse can record observations for any approved patient, and the
-- nurse's own patient list is simply "who I've recorded something for", mirroring
-- how the Lab Technician's queue works.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS PatientVitals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    nurse_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    temperature_celsius NUMERIC(4,1),
    blood_pressure_systolic SMALLINT,
    blood_pressure_diastolic SMALLINT,
    heart_rate SMALLINT,
    spo2 SMALLINT,
    respiratory_rate SMALLINT,
    weight_kg NUMERIC(5,2),
    height_cm NUMERIC(5,2),
    notes TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    CREATE TYPE nursing_note_type AS ENUM ('Observation', 'Care', 'Incident');
EXCEPTION WHEN duplicate_object THEN null; END $$;

CREATE TABLE IF NOT EXISTS NursingNotes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    nurse_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    note_type nursing_note_type NOT NULL DEFAULT 'Observation',
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$ BEGIN
    CREATE TYPE medication_admin_status AS ENUM ('Administered', 'Refused', 'Held', 'Missed');
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- One administration event per prescription per nurse action; a prescription
-- can have many rows over its course (e.g. "Twice daily" for 90 days).
CREATE TABLE IF NOT EXISTS MedicationAdministration (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prescription_id UUID NOT NULL REFERENCES Prescriptions(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
    nurse_id UUID REFERENCES Users(id) ON DELETE SET NULL,
    status medication_admin_status NOT NULL DEFAULT 'Administered',
    remarks TEXT,
    administered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Doctor-authored documents (discharge summaries, referral letters, medical
-- certificates) previously stored their body as plaintext in `content` and
-- never reached cloud storage at all, bypassing the security pipeline that
-- every other document type goes through. They now carry the same hybrid
-- material. `content` is retained only for rows predating encryption.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS encrypted_content TEXT;
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS encrypted_aes_key TEXT;
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS encryption_nonce TEXT;
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS encryption_tag TEXT;
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS document_hash VARCHAR(64);
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS digital_signature TEXT;
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS kem_algorithm VARCHAR(32);
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS signature_algorithm VARCHAR(32);
ALTER TABLE MedicalDocuments ADD COLUMN IF NOT EXISTS blockchain_tx_hash VARCHAR(66);

-- ─────────────────────────────────────────────────────────────────────────────
-- Imaging reports carry the same hybrid-encryption material as lab reports.
-- Previously the image payload was uploaded to cloud storage as plaintext and
-- stored plaintext in image_data, which contradicts the rule that the cloud
-- never holds unencrypted medical content. image_data is retained only for
-- rows predating encryption; new rows populate the encrypted_* columns.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS encrypted_image TEXT;
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS encrypted_aes_key TEXT;
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS encryption_nonce TEXT;
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS encryption_tag TEXT;
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS document_hash VARCHAR(64);
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS digital_signature TEXT;
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS kem_algorithm VARCHAR(32);
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS signature_algorithm VARCHAR(32);
ALTER TABLE ImagingReports ADD COLUMN IF NOT EXISTS blockchain_tx_hash VARCHAR(66);

CREATE INDEX IF NOT EXISTS idx_vitals_patient ON PatientVitals(patient_id);
CREATE INDEX IF NOT EXISTS idx_vitals_nurse ON PatientVitals(nurse_id);
CREATE INDEX IF NOT EXISTS idx_vitals_recorded ON PatientVitals(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_nursingnotes_patient ON NursingNotes(patient_id);
CREATE INDEX IF NOT EXISTS idx_nursingnotes_nurse ON NursingNotes(nurse_id);
CREATE INDEX IF NOT EXISTS idx_medadmin_patient ON MedicationAdministration(patient_id);
CREATE INDEX IF NOT EXISTS idx_medadmin_prescription ON MedicationAdministration(prescription_id);
CREATE INDEX IF NOT EXISTS idx_medadmin_nurse ON MedicationAdministration(nurse_id);
