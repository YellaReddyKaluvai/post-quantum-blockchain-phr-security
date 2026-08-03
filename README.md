# 🔐 QuantumCare — Post-Quantum Cryptography & Blockchain Secure Hospital Management System (PHR)

> **Enterprise-Grade Post-Quantum Health Record Management Platform** powered by **ML-KEM (Kyber-768)**, **ML-DSA (Dilithium-3)**, **AWS S3 Cloud Storage**, **IPFS Multihash CIDs**, and **PostgreSQL**.

---

## 🌟 Overview

**QuantumCare** is an advanced, commercial-grade healthcare and Personal Health Record (PHR) platform built to defend electronic health records against classical and quantum computing security threats.

The architecture combines **Post-Quantum Key Encapsulation (ML-KEM)**, **Quantum Digital Signatures (ML-DSA)**, **AES-256-GCM Symmetric Encryption**, **AWS S3 Cloud Storage**, and **IPFS Content Addressing** to guarantee zero-knowledge privacy, verifiable integrity, and post-quantum security.

---

## ⚡ Core System Modules

### 1. 🛡️ Administrator Dashboard (`/dashboard/admin`)
- **User Registration Verification & Approval**: Workflow for reviewing and approving newly registered Doctors, Patients, Lab Technicians, and Nurses.
- **Automated Public ID Generation**: Issues sequential identifiers (`PAT-2026-000001`, `DOC-2026-000001`, `LAB-2026-000001`, `NUR-2026-000001`).
- **User Management & Role Access Control**: Active user toggles, status management, and permissions.
- **Cryptographic Key Center**: Real-time stats on ML-KEM public keys, ML-DSA signatures, and Argon2id hash parameters.
- **Email Notifications**: Live SMTP Gmail dispatch for registration approvals and rejection notices.

### 2. 🏥 Doctor Dashboard (`/dashboard/doctor`)
- **Patient Workspace**: Patient roster search, chart view, and medical history.
- **Diagnosis Builder**: Interactive modal for recording diagnoses, symptoms, doctor notes, and recommended tests.
- **Prescription System**: Form for issuing electronic prescriptions with medicine name, dosage, frequency, and duration.
- **Lab Report & Document Review**: Direct access to finalized laboratory test results and imaging scans.
- **Appointment Manager**: Manage scheduled, completed, and cancelled patient consultations.

### 3. 🧪 Laboratory Technician Dashboard (LIMS) (`/dashboard/lab-technician`)
- **Laboratory Information Management System (LIMS)**: Complete portal for receiving test requests, searching patient directories, and uploading medical documents.
- **Structured Report Form Builder**: Form templates for CBC, Blood Sugar, Urine Analysis, LFT, ECG, and Imaging.
- **Live Hospital Document Preview**: Dynamic preview rendering official hospital letterhead and test result ranges.
- **12-Step PQC Security Pipeline**: Automated SHA-256 hashing, AES-256-GCM payload encryption, ML-KEM key wrapping, ML-DSA digital signing, and IPFS multihash pinning.
- **Imaging Gallery**: High-resolution gallery for X-Rays, MRIs, CT Scans, and Ultrasounds with interactive zoom.
- **Blockchain Audit Trail Modal**: View cryptographic transaction hashes, IPFS CIDs (`ipfs://Qm...`), and AWS S3 storage keys.

### 4. 👤 Patient Dashboard (`/dashboard/patient`)
- **Personal Health Record (PHR)**: Medical records, diagnosis timeline, active prescriptions, and lab report history.
- **Appointments & Consultations**: Upcoming appointment schedule and consultation notes.
- **Security & Privacy Center**: Real-time PQC protection status, active session logs, and login IP address tracker.
- **Real-Time Notification Feed**: System notifications for report readiness and appointment updates.

---

## 🔒 Security & Cryptographic Architecture

| Layer | Protocol / Algorithm | Purpose |
| --- | --- | --- |
| **Password Hashing** | **Argon2id** | Memory-hard, GPU-resistant credential protection |
| **PII Encryption** | **AES-256-CBC** | Encrypts sensitive demographics (DOB, Blood Group) |
| **Key Encapsulation** | **ML-KEM (Kyber-768)** | Post-Quantum Key Encapsulation (FIPS 203) for payload AES keys |
| **Digital Signatures** | **ML-DSA (Dilithium-3)** | Post-Quantum Digital Signature (FIPS 204) for document authenticity |
| **Cloud Storage** | **AWS S3** | Resilient cloud storage bucket (`postquantumcryptography`) |
| **Decentralized Storage** | **IPFS (v0 Multihash)** | Content-addressed storage CID (`ipfs://Qm...`) |
| **Audit Logging** | **Blockchain Metadata** | Immutable audit logging in `AdminAuditLogs` |

---

## 🛠️ Technology Stack

- **Backend**: FastAPI (Python 3.11/3.13), Uvicorn, PostgreSQL, `psycopg3`, `boto3`, `liboqs-python`
- **Frontend**: Next.js 16 (App Router), TailwindCSS v4, Framer Motion 12, Lucide React
- **Database**: PostgreSQL 15+ (`pqc_hospital`)
- **Cloud & Storage**: AWS S3, IPFS Gateway (Pinata)

---

## 🚀 Quick Start Guide

### 1. Clone & Setup Environment
```bash
git clone https://github.com/YellaReddyKaluvai/post-quantum-blockchain-phr-security.git
cd post-quantum-blockchain-phr-security
```

### 2. Configure Backend Environment (`backend/.env`)
```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/pqc_hospital"
SECRET_KEY="your-production-jwt-secret"
ENCRYPTION_KEY="32-byte-hex-encryption-key"

# Email Configuration
SMTP_HOST="smtp.gmail.com"
SMTP_PORT="587"
SMTP_USER="your-email@gmail.com"
SMTP_PASSWORD="your-app-password"

# AWS S3 Cloud Storage Credentials
AWS_ACCESS_KEY_ID="your_aws_access_key"
AWS_SECRET_ACCESS_KEY="your_aws_secret_key"
AWS_REGION="eu-north-1"
AWS_S3_BUCKET="postquantumcryptography"
IPFS_GATEWAY_URL="https://gateway.pinata.cloud/ipfs/"
```

### 3. Run Backend API Server
```bash
cd backend
python -m pip install -r requirements.txt  # Or install dependencies
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Run Frontend Web Application
```bash
cd frontend
npm install
npm run dev
```

Visit **http://localhost:3000** to log in to the platform!

---

## 🔑 Demo Login Credentials

| Role | Public User ID | Email / Password |
| --- | --- | --- |
| **Administrator** | `ADM-2026-000001` | `admin@hospital.com` / `Admin@1234` |
| **Doctor** | `DOC-2026-000001` | `doctor@pqc.com` / `Password123!` |
| **Patient** | `PAT-2026-000001` | `patient@pqc.com` / `Password123!` |
| **Lab Technician** | `LAB-2026-000001` | `lab@pqc.com` / `Password123!` |
