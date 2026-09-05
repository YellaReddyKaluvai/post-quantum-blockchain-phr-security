# 9. Database Schema

30 tables in PostgreSQL 16, grouped by responsibility. The database holds the
authoritative copy of every record; S3 and IPFS are redundant stores.

## Entity relationships (core clinical path)

```mermaid
erDiagram
    USERS ||--o{ CONSENT : "grants or withdraws"
    USERS ||--o{ DIAGNOSES : "receives"
    USERS ||--o{ PRESCRIPTIONS : "receives"
    USERS ||--o{ PATIENTVITALS : "measured for"
    USERS ||--o{ LABTESTREQUESTS : "requested for"
    USERS ||--o{ APPOINTMENTS : "books"
    USERS ||--o{ NOTIFICATIONS : "receives"
    USERS ||--o{ SESSIONS : "authenticates"

    LABTESTREQUESTS ||--o| LABREPORTS : "yields one"
    PRESCRIPTIONS ||--o{ MEDICATIONADMINISTRATION : "administered as"
    LABREPORTS ||--o{ DOCUMENTANCHORS : "anchored by"
    MEDICALDOCUMENTS ||--o{ DOCUMENTANCHORS : "anchored by"
    IMAGINGREPORTS ||--o{ DOCUMENTANCHORS : "anchored by"

    USERS ||--o{ EMERGENCYACCESS : "declares"
    USERS ||--o{ SECURITYEVENTS : "generates"
    SECURITYEVENTS ||--o{ RISKASSESSMENTS : "scored into"
    RISKASSESSMENTS ||--o| SECURITYALERTS : "raises"
    SECURITYALERTS ||--o| SECURITYINCIDENTS : "escalates to"

    USERS {
        uuid id PK
        varchar user_id UK "PAT-2026-000001"
        varchar full_name
        text password_hash "Argon2id"
        user_role role
        text date_of_birth_encrypted "AES-256-CBC"
        text blood_group_encrypted "AES-256-CBC"
        text mlkem_public_key "ML-KEM-768"
        text mlkem_private_key_encrypted
        text mldsa_public_key "ML-DSA-65"
        text mldsa_private_key_encrypted
        registration_status status
    }

    LABREPORTS {
        uuid id PK
        uuid patient_id FK
        uuid doctor_id FK
        uuid lab_request_id FK
        text encrypted_document "AES-256-GCM"
        text encrypted_aes_key "ML-KEM ciphertext"
        text digital_signature "ML-DSA-65"
        varchar document_hash "SHA-256"
        varchar s3_key
        varchar ipfs_cid
        varchar blockchain_tx_hash
    }

    CONSENT {
        uuid consent_id PK
        uuid patient_id FK
        uuid subject_user_id FK
        consent_status status "Pending|Authorized|Rejected|Revoked|Emergency"
        text purpose
        timestamptz requested_at
        timestamptz decided_at
    }
```

## Tables by group

### Identity & access — 6 tables
| Table | Cols | Purpose |
|---|---|---|
| `users` | 20 | Accounts, encrypted PII, PQC keypairs |
| `sessions` | 9 | Active JWT sessions, revocable |
| `useridsequences` | 4 | Atomic per-role, per-year ID counter |
| `consent` | 17 | Access requests and consent lifecycle |
| `emergencyaccess` | 9 | Break-glass declarations, time-boxed |
| `zkpchallenges` | 8 | Zero-knowledge consent proof challenges |

### Clinical records — 10 tables
| Table | Cols | Purpose |
|---|---|---|
| `diagnoses` | 11 | Encrypted clinical text |
| `prescriptions` | 10 | Encrypted medicine, dosage, instructions |
| `patientvitals` | 13 | Nurse-recorded observations |
| `nursingnotes` | 6 | Observation / Care / Incident |
| `medicationadministration` | 7 | Administered / Refused / Held / Missed |
| `doctorconsultations` | 8 | Visit records |
| `appointments` | 10 | Booking lifecycle |
| `labtestrequests` | 13 | Investigation orders |
| `labreports` | 34 | Encrypted report + full crypto metadata |
| `imagingreports` | 22 | Encrypted studies |
| `medicaldocuments` | 19 | Discharge summaries, referrals |

### Audit & integrity — 4 tables
`documentanchors` (13) · `adminauditlogs` (9) · `authlogs` (8) · `emailnotifications` (10)

### AI security — 7 tables
`securityevents` (10) · `riskassessments` (11) · `securityalerts` (10) ·
`securityincidents` (16) · `federatedrounds` (7) · `federatedglobalmodel` (7) ·
`federatedpeers` (8)

### Deprecated — 1 table
`medicalrecords` (12) — dead schema from an earlier design, 0 rows, 0 code
references. Marked deprecated rather than dropped unilaterally.

## Encryption at rest

| Data | Protection |
|---|---|
| Passwords | Argon2id (memory-hard, per-user salt) |
| Date of birth, blood group | AES-256-CBC column encryption |
| Diagnoses, prescriptions | AES-256-CBC column encryption |
| Lab reports, imaging, documents | AES-256-GCM, key wrapped by ML-KEM-768 |
| PQC private keys | AES-encrypted before storage |

Grepping the database for a condition name such as "Diabetes" returns **0 rows**
across 810 diagnoses, while the patient portal displays the text correctly.

## Indexing

Indexes back the access paths that run per request: audit log by admin and by
time, security events by actor and by type, consent by patient and status,
notifications by user. Deep pagination measured the same as page one
(8 ms at page 1 and page 26 of the admin user list), confirming the list
endpoints are not scanning whole tables.
