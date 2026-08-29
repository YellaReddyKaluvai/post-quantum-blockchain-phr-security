# 🔐 QuantumCare — Post-Quantum Cryptography & Blockchain Secure Hospital Management System (PHR)

> Post-quantum Personal Health Record platform built on **ML-KEM-768** (FIPS 203), **ML-DSA-65** (FIPS 204), **AES-256-GCM**, encrypted **AWS S3** storage, on-chain integrity anchoring and **PostgreSQL**.

---

## 🌟 Overview

**QuantumCare** is an advanced, commercial-grade healthcare and Personal Health Record (PHR) platform built to defend electronic health records against classical and quantum computing security threats.

The architecture combines **ML-KEM-768** key encapsulation, **ML-DSA-65** digital signatures, **AES-256-GCM** document encryption, encrypted **AWS S3** storage and **on-chain integrity anchoring**.

The design rule throughout: *the system never claims a protection it did not actually apply.* A failed upload records no object key, an unreachable chain produces a visibly-simulated anchor, and a missing post-quantum library raises rather than substituting placeholder keys.

---

## ⚡ Core System Modules

### 1. 🛡️ Administrator Dashboard (`/dashboard/admin`)
- **User Registration Verification & Approval**: Workflow for reviewing and approving newly registered Doctors, Patients, Lab Technicians, and Nurses.
- **Automated Public ID Generation**: Issues sequential identifiers (`PAT-2026-000001`, `DOC-2026-000001`, `LAB-2026-000001`, `NUR-2026-000001`).
- **User Management & Role Access Control**: Active user toggles, status management, and permissions.
- **Cryptographic Key Center**: Live counts of issued ML-KEM / ML-DSA keypairs and active cryptographic identities.
- **Infrastructure Health**: Live blockchain and cloud-storage status — chain connectivity and block height, the **on-chain vs locally-simulated** anchor split, and how many reports actually have a cloud copy. Built to surface problems rather than imply everything is fine.
- **Audit Log**: Every administrative action, report access and download, with search and pagination.
- **Email Notifications**: Live SMTP dispatch for registration approvals and rejections, with delivery status tracked per message.

### 2. 🏥 Doctor Dashboard (`/dashboard/doctor`)
- **Patient Workspace**: Patient roster search, chart view, and medical history.
- **Nursing Observations**: The vitals and notes recorded by nursing staff, with out-of-range readings highlighted — the reading behind each abnormal-vitals alert.
- **Diagnosis Builder**: Structured entry for title, visit date, symptoms, clinical notes and recommended tests.
- **Prescription System**: Electronic prescriptions with medicine, dosage, frequency, duration and instructions.
- **Lab Requests**: Order an investigation from the patient's chart, then track every request through Pending → Accepted → In Progress → Completed, opening the signed report the moment it is filed.
- **Report Review & Verification**: Decrypt finalised reports, and re-check each one's signature and on-chain digest.
- **Appointment Manager**: Confirm, complete or cancel patient appointments.

### 3. 🧪 Laboratory Technician Dashboard (LIMS) (`/dashboard/lab-technician`)
- **Laboratory Information Management System (LIMS)**: Complete portal for receiving test requests, searching patient directories, and uploading medical documents.
- **Structured Report Form Builder**: Nine panels — CBC, Blood Sugar, LFT, KFT, Lipid, Thyroid, Urine, ECG and Radiology — each driving both the data-entry form and the printed report.
- **Live Hospital Document Preview**: Dynamic preview rendering official hospital letterhead and test result ranges.
- **PQC Security Pipeline**: SHA-256 hashing, AES-256-GCM payload encryption, ML-KEM key encapsulation, ML-DSA digital signing, and an on-chain integrity anchor. Only ciphertext reaches cloud storage.
- **Imaging Gallery**: High-resolution gallery for X-Rays, MRIs, CT Scans, and Ultrasounds with interactive zoom.
- **Blockchain Audit Trail Modal**: Transaction hash with its network, the document's content CID, and the AWS S3 object key — each shown only when it genuinely exists.

### 4. 👤 Patient Dashboard (`/dashboard/patient`)
- **Personal Health Record (PHR)**: Medical records, diagnosis timeline, active prescriptions, and lab report history.
- **My Vitals**: Nurse-recorded observations, with out-of-range readings flagged using the same thresholds clinical staff see.
- **Appointment Booking**: Request an appointment with any approved doctor; the doctor is notified and confirms or declines.
- **Security & Privacy Center**: PQC protection status, active session logs, and login IP tracking.
- **Notification Feed**: Report readiness, appointment updates, and vitals alerts.

### 5. 🩺 Nurse Dashboard (`/dashboard/nurse`)
- **Patient Chart**: Vitals entry, nursing notes, and medication rounds in one view.
- **Vitals Recording**: Temperature, blood pressure, heart rate, SpO₂, respiratory rate, weight and height. Out-of-range readings are flagged at the point of entry and the attending doctor is alerted automatically.
- **Nursing Notes**: Observation, Care and Incident entries, visible to the treating doctor.
- **Medication Administration**: Records each round against the prescription as Administered, Refused, Held or Missed, with the last outcome shown per medicine.

> Vitals recorded here are readable by the treating **doctor** and by the **patient**. Nursing notes go to the doctor only — they are clinical handover between staff.

---

## 📊 Implementation Status

Verified against the running system, not aspirational. Anything not built is
listed as not built.

### Working end-to-end

| Area | State | Notes |
|---|---|---|
| Registration → admin approval → login | ✅ | Permanent role-scoped User IDs; real SMTP approval/rejection email |
| Post-quantum key issuance | ✅ | Real ML-KEM-768 + ML-DSA-65 via liboqs, generated on approval |
| Doctor → Lab → Patient report pipeline | ✅ | 9 structured panels → hospital PDF → AES-256-GCM → ML-KEM → ML-DSA → chain anchor |
| Imaging studies | ✅ | Same hybrid protection as lab reports; encrypted before storage, decrypted only on request |
| Nurse module | ✅ | Vitals, notes, medication rounds; shared with doctor and patient |
| Cloud storage (AWS S3) | ✅ | Ciphertext only, verified; doubles as a recovery path if the database copy is lost |
| Blockchain anchoring | ✅ | Real on-chain writes via `PHR.sol`; falls back to a clearly-labelled local anchor |
| Session handling | ✅ | 30-minute tokens; expiry redirects to login and returns you to where you were |
| RBAC across 5 roles | ✅ | Enforced server-side; backend/frontend permission parity is test-enforced |
| Automated tests | ✅ | 75 tests, mutation-checked |

### Not implemented

| Area | Status |
|---|---|
| **Consent management** | `Consent` table exists in the schema; **no endpoints or UI**. Patients cannot currently grant or revoke access. |
| **Emergency "break-glass" access** | `EmergencyAccess` table and `PHR.sol`'s `emergencyAccess()` both exist; **no endpoints or UI**. |
| **IPFS publishing** | A CIDv0 is computed locally, but nothing is pinned to the IPFS network — see the Content Addressing row below. |
| **Detail views** | Some list pages have no per-record detail screen (patient medical record, patient lab report, lab technician report). |
| `MedicalRecords` table | Dead schema — defined in `init.sql`, referenced nowhere. Superseded by `LabReports` / `MedicalDocuments`. |

### Known data caveats
- Two lab reports predate the encryption pipeline and hold no ciphertext, so they cannot be given a cloud copy or be decrypted. They are counted honestly in `/api/admin/storage/status`.
- Anchors written before the chain integration are marked `local-simulated` and carry no on-chain proof. The admin Security page reports the on-chain vs simulated split rather than hiding it.

---

## 🔒 Security & Cryptographic Architecture

| Layer | Protocol / Algorithm | Purpose |
| --- | --- | --- |
| **Password Hashing** | **Argon2id** | Memory-hard, GPU-resistant credential protection |
| **PII Encryption** | **AES-256-CBC** | Encrypts sensitive demographics (DOB, Blood Group) |
| **Key Encapsulation** | **ML-KEM (Kyber-768)** | Post-Quantum Key Encapsulation (FIPS 203) for payload AES keys |
| **Digital Signatures** | **ML-DSA (Dilithium-3)** | Post-Quantum Digital Signature (FIPS 204) for document authenticity |
| **Cloud Storage** | **AWS S3** | Resilient cloud storage bucket (`postquantumcryptography`) |
| **Content Addressing** | **CIDv0 (IPFS multihash format)** | Deterministic fingerprint of the encrypted document. Computed locally — **not** published to the IPFS network |
| **Integrity Anchoring** | **Ethereum (`PHR.sol`)** | Document digests committed on-chain via `DocumentAnchors`; falls back to a labelled local anchor when no chain is reachable |
| **Access Auditing** | **PostgreSQL** | Every read, download and admin action recorded in `AdminAuditLogs` / `AuthLogs` |

---

## 🛠️ Technology Stack

- **Backend**: FastAPI on **Python 3.12+** (3.10 minimum — the codebase uses `X | None` syntax), Uvicorn, PostgreSQL, `psycopg3`, `boto3`, `liboqs-python`, `reportlab`
- **Frontend**: Next.js 16 (App Router), TailwindCSS v4, Framer Motion 12, Lucide React
- **Database**: PostgreSQL 15+ (`pqc_hospital`)
- **Cloud & Storage**: AWS S3 (encrypted objects only)

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

# Blockchain audit anchoring (defaults target a local dev chain)
BLOCKCHAIN_ENABLED="true"
BLOCKCHAIN_RPC_URL="http://127.0.0.1:8545"
BLOCKCHAIN_CHAIN_ID="31337"
BLOCKCHAIN_NETWORK_NAME="anvil-local"
BLOCKCHAIN_CONTRACT_ADDRESS="0x5FbDB2315678afecb367f032d93F642f64180aa3"
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

### 5. Running the Tests

```bash
cd backend
python3 -m pytest
```

75 tests, no database or running server required — they exercise pure functions
so they fail for exactly one reason.

What they cover, and why these specific assertions: every test asserts a
*refusal* as well as a success, because a happy-path-only suite would pass
against a verifier that always returns true. That is not hypothetical — this
codebase previously shipped one.

| Area | The property being protected |
|---|---|
| `test_crypto_pipeline.py` | A tampered digest fails verification; a forged signature fails; a mock key never verifies; wrong-key decryption raises; ciphertext does not leak plaintext |
| `test_storage_and_anchoring.py` | A failed upload records no object key; a failed download raises instead of returning placeholder bytes; placeholder credentials read as *unconfigured*; an unreachable chain yields a clearly-labelled local anchor |
| `test_clinical_validation.py` | Impossible vitals (SpO₂ 990%) are rejected while abnormal-but-real ones (SpO₂ 88%) are accepted; past appointment dates are refused |
| `test_rbac_parity.py` | The backend permission matrix and the frontend IAM map cannot drift apart |

The suite was checked by mutation: reintroducing three real past bugs — a
signature verifier that always returned true, an upload that recorded a key it
never wrote, and a dropped vitals validator — made 7, 1 and 2 tests fail
respectively.

### 6. Blockchain Audit Trail

Document digests are anchored on-chain via `contracts/PHR.sol`. Every developer
runs their own local chain — no accounts, no funds, no internet required.

Install [Foundry](https://getfoundry.sh), then:

```bash
# From the repository root — compile the contract
forge build

# Start a local chain (leave running)
anvil --port 8545 --chain-id 31337

# Deploy, then copy the printed address into backend/.env
cd backend && python3 deploy_contract.py
```

The deploy address is deterministic, so the value already in `.env` works as
long as you deploy to a fresh chain as the first transaction.

**Verifying it is genuinely on-chain** — `GET /api/admin/blockchain/status`
reports live connection state and an `on_chain` vs `simulated` anchor count.
Each report's `/verify` endpoint returns `blockchain_verified`, which re-reads
the digest from the chain and compares it to the stored one. That check is what
catches tampering: an attacker who rewrites `document_hash` in Postgres cannot
alter the digest already committed to the chain, so the two stop agreeing.

If no chain is reachable the system keeps working, but anchors are written with
`anchored_on='local-simulated'` and no block number — deliberately visible, so a
simulated anchor is never mistaken for a real one.

**Sharing one ledger across the team** (e.g. for a demo with a public block
explorer), point every developer at the same testnet instead:

```env
BLOCKCHAIN_RPC_URL="https://sepolia.infura.io/v3/<your-key>"
BLOCKCHAIN_CHAIN_ID="11155111"
BLOCKCHAIN_NETWORK_NAME="sepolia"
BLOCKCHAIN_PRIVATE_KEY="<testnet-only key, funded from a faucet>"
BLOCKCHAIN_EXPLORER_URL="https://sepolia.etherscan.io/tx/"
BLOCKCHAIN_CONTRACT_ADDRESS="<address from deploy_contract.py>"
```

Deploy once, share the resulting contract address. Use a throwaway key funded
only with faucet ETH — never a key that holds real funds.

Visit **http://localhost:3000** to log in to the platform!

---

## 🔑 Demo Login Credentials

Sign in with the **User ID**, not the email address.

| Role | User ID | Password | Seeded as |
| --- | --- | --- | --- |
| **Administrator** | `ADM-2026-000001` | `Admin@1234` | System Administrator |
| **Doctor** | `DOC-2026-000001` | `Password@123` | Dr Carol |
| **Patient** | `PAT-2026-000001` | `Password@123` | Bob Patient |
| **Lab Technician** | `LAB-2026-000001` | `Password@123` | Leo LabTech |
| **Nurse** | `NUR-2026-000001` | `Password@123` | Nina Nurse |

Create these with the seed scripts in `backend/` (`seed_admin.py`, then the
role seeders). The admin password comes from `ADMIN_PASSWORD` in `.env`.
