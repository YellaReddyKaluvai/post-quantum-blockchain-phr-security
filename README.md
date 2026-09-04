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
- **Emergency Access Review**: Every break-glass declaration with its verbatim clinical reason, both parties, expiry and on-chain transaction hash. Active declarations are surfaced first.
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
- **Record Consultation**: Capture the visit itself — symptoms, assessment and advice — which the patient then reads in their portal.
- **Emergency Access**: Break-glass override when a patient has withdrawn consent. Requires a substantive clinical reason, is time-boxed, and states its consequences before the form — the patient is notified at once and the declaration is anchored on-chain.

### 3. 🧪 Laboratory Technician Dashboard (LIMS) (`/dashboard/lab-technician`)
- **Laboratory Information Management System (LIMS)**: Complete portal for receiving test requests, searching patient directories, and uploading medical documents.
- **Structured Report Form Builder**: Nine panels — CBC, Blood Sugar, LFT, KFT, Lipid, Thyroid, Urine, ECG and Radiology — each driving both the data-entry form and the printed report.
- **Live Hospital Document Preview**: Dynamic preview rendering official hospital letterhead and test result ranges.
- **PQC Security Pipeline**: SHA-256 hashing, AES-256-GCM payload encryption, ML-KEM key encapsulation, ML-DSA digital signing, and an on-chain integrity anchor. Only ciphertext reaches cloud storage.
- **Imaging Gallery**: High-resolution gallery for X-Rays, MRIs, CT Scans, and Ultrasounds with interactive zoom.
- **Blockchain Audit Trail Modal**: Transaction hash with its network, the document's content CID, and the AWS S3 object key — each shown only when it genuinely exists.

### 4. 👤 Patient Dashboard (`/dashboard/patient`)
- **Personal Health Record (PHR)**: Medical records, diagnosis timeline, active prescriptions, and lab report history.
- **My Documents**: Discharge summaries, referral letters and certificates written by your doctors — decrypted on demand, with the signing algorithm, digest and on-chain anchor shown so authenticity is checkable rather than asserted.
- **My Vitals**: Nurse-recorded observations, with out-of-range readings flagged using the same thresholds clinical staff see.
- **Appointment Booking**: Request an appointment with any approved doctor; the doctor is notified and confirms or declines.
- **Record Access**: Every clinician who can read the record and how that relationship arose, with one-click withdrawal. Revoking genuinely blocks reads rather than merely noting a preference; an active emergency override is shown plainly.
- **Security & Privacy Center**: PQC protection status, active session logs, and login IP tracking.
- **Notification Feed**: Report readiness, appointment updates, and vitals alerts.

### 5. 🩺 Nurse Dashboard (`/dashboard/nurse`)
- **Patient Chart**: Vitals entry, nursing notes, and medication rounds in one view.
- **Vitals Recording**: Temperature, blood pressure, heart rate, SpO₂, respiratory rate, weight and height. Out-of-range readings are flagged at the point of entry and the attending doctor is alerted automatically.
- **Nursing Notes**: Observation, Care and Incident entries, visible to the treating doctor.
- **Medication Administration**: Records each round against the prescription as Administered, Refused, Held or Missed, with the last outcome shown per medicine.

> Vitals recorded here are readable by the treating **doctor** and by the **patient**. Nursing notes go to the doctor only — they are clinical handover between staff.

---

## 🔄 End-to-End Data Flow

How data actually moves between the five roles. Each arrow below exists in
code; where a flow stops short, it is marked and listed again under
[Incomplete workflows](#-incomplete-workflows).

### The security pipeline every document passes through

```
Structured form  →  Hospital PDF  →  SHA-256 digest
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
              AES-256-GCM           ML-KEM-768             ML-DSA-65
           encrypts the file    protects the AES key    signs the digest
                    │                     │                     │
                    └─────────────────────┼─────────────────────┘
                                          ▼
                        Database (authoritative) + AWS S3 (redundant)
                                          │
                                          ▼
                              Digest anchored on-chain
```

AES handles the bulk data; ML-KEM protects only the 32-byte key; ML-DSA proves
who issued it. **Only the digest reaches the blockchain — never the document,
never key material.** On read, the digest is re-checked before release, so a
tampered record is refused rather than returned.

### 1. Registration → active account

```
Patient/Doctor/Nurse/Lab signs up
      → status Pending, DOB + blood group encrypted immediately
      → Administrator reviews
            ├─ Reject → reason recorded → rejection email
            └─ Approve → permanent User ID issued (PAT-2026-000001)
                       → ML-KEM-768 + ML-DSA-65 keypairs generated
                       → approval email → account usable
```

Keys are issued **only on approval**, so a pending or rejected account never
holds usable key material.

### 2. Doctor → Laboratory → Patient  *(the main clinical workflow)*

```
Doctor opens patient chart → requests an investigation (panel + priority)
      → LabTestRequests row (Pending)
      → Technician's queue, ordered by urgency
      → Technician opens the matching structured form (1 of 9 panels)
      → Finalise → hospital PDF → security pipeline above
      → Notifications: REPORT_READY to BOTH patient and referring doctor
            ├─ Doctor  → decrypts PDF, verifies signature + on-chain digest
            └─ Patient → decrypts and downloads their own copy
```

The report is permanently bound to its originating request, patient, doctor and
technician. One finalised report per request, enforced by a unique index.

### 3. Doctor → clinical record → Patient

```
Doctor records diagnosis / prescription / consultation
      → clinical text encrypted at column level (AES-256-CBC)
      → Patient sees it in Medical Records / Prescriptions / Consultations

Doctor authors a document (discharge summary, referral, certificate)
      → full security pipeline → DOCUMENT_READY notification
      → Patient opens it decrypted, with signature + anchor shown
```

### 4. Nurse → observations → Doctor and Patient

```
Nurse records vitals (range-validated at entry)
      → PatientVitals row
      → out of range?  ── yes ──→ ABNORMAL_VITALS alert naming the readings
      │                              → Doctor sees the reading itself on the chart
      └─ no ──→ VITALS_RECORDED
      → Patient sees their own vitals in My Vitals

Nurse writes a nursing note → visible to the treating doctor only
Nurse records a medication round → ✗ no one can read the history (see below)
```

Vitals are shaped by one shared function for all three views, so a reading
cannot appear differently depending on who is looking.

### 5. Patient → appointment → Doctor

```
Patient books (past dates and unknown doctors refused at the schema)
      → status Pending → APPOINTMENT_REQUEST notification to doctor
      → Doctor accepts / completes / cancels
      → ✗ patient is not notified of the outcome (see below)
```

### 6. Consent and break-glass

```
Patient revokes a doctor's access
      → Consent row → every doctor-facing read now returns 404
      → CONSENT_REVOKED notification to the doctor

Doctor declares emergency access (substantive reason required, ≤24h)
      → overrides the revocation
      → EMERGENCY_ACCESS notification to the patient immediately
      → written to the admin audit log
      → anchored on-chain so it cannot be quietly removed
      → Administrator reviews it in Emergency Access
```

Break-glass is deliberately **not** gated on approval — waiting for a second
party in an emergency defeats the purpose. The control is accountability, not
prevention.

### 7. Everything is audited

```
Every admin action, record access and download
      → AdminAuditLogs (55+ entries across 10 action types)
Every login attempt
      → AuthLogs
Every finalised document and break-glass declaration
      → DocumentAnchors + on-chain transaction
```

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
| Imaging studies | ✅ | Encrypted, signed, anchored — and now readable by the patient and by an entitled doctor |
| Nurse module | ✅ | Vitals, notes and medication rounds all reach the doctor and the patient |
| Cloud storage (AWS S3) | ✅ | Ciphertext only, verified; doubles as a recovery path if the database copy is lost |
| Blockchain anchoring | ✅ | Real on-chain writes via `PHR.sol`; falls back to a clearly-labelled local anchor |
| Session handling | ✅ | 30-minute tokens; expiry redirects to login and returns you to where you were |
| RBAC across 5 roles | ✅ | Enforced server-side; backend/frontend permission parity is test-enforced |
| Doctor-authored documents | ✅ | Encrypted, signed and anchored — and readable by the patient they concern, completing the spec's "patient receives authorized access" |
| Clinical record encryption | ✅ | Diagnoses and prescriptions encrypted at column level; grepping the database for a diagnosis returns nothing |
| Consent management | ✅ | Revoking a doctor genuinely blocks reads — the same report returns 200 before and 404 after |
| Doctor access requests | ✅ | Doctor requests with a stated purpose → patient approves or declines → the backend enforces it. Verified: no request 403, pending 403, rejected 403, approved 200 |
| AI security layer | ✅ | Anomaly detection, XAI, alerts, incidents. Federated aggregation real; peer nodes simulated |
| Emergency break-glass access | ✅ | Time-boxed override, patient notified immediately, anchored on-chain, reviewable by an admin |
| Automated tests | ✅ | 106 tests, mutation-checked |

### Imaging: encrypted but unreachable

Imaging studies receive the full hybrid pipeline and the patient is notified
that a study is ready — but **no patient or doctor endpoint exists to open one**.
Only the uploading technician can view it. The protection is real; the delivery
is missing. Listed below rather than counted as complete.

---

## ⚠️ Incomplete Workflows

Flows that start but do not finish. Five were closed in this pass; what remains
is listed honestly rather than quietly dropped.

### Closed

| Workflow | What was wrong | Now |
|---|---|---|
| **Imaging → clinician / patient** | Encrypted, signed, anchored — and openable only by the uploading technician. The patient was notified about something they could not reach. | Patient and entitled doctor both read studies, through one shared release path |
| **Medication adherence → prescriber** | Every round recorded; no endpoint ever returned it. A refusal was stored and never surfaced. | Doctor sees it on the chart, patient sees their own history; refusals reported in their own right |
| **Appointment outcome → patient** | Accept, complete and cancel notified nobody, so a cancelled appointment was one the patient turned up for. | Every outcome reaches the patient |
| **Lab request → laboratory** | The only role in the system not told when work arrived for it. | All technicians notified, priority marked |
| **Report reviewed → patient** | The moment the patient is really waiting for went unannounced. | Patient told a clinician has read their result |

### Still open

| # | Workflow | Where it stops |
|---|---|---|
| 1 | **Post-quantum ZKP** | The zero-knowledge proof is Schnorr — genuine, but classically secure only. See below. |
| 2 | **Public IPFS replication** | Content is really pinned, but on one node. That is not replication across the public network. |

### Not implemented

| Area | Status |
|---|---|
| **Post-quantum ZKP** | The Schnorr proof below is real but rests on discrete logarithm, which Shor's algorithm breaks. A quantum-resistant proof system (hash-based STARKs, lattice-based proofs) is not implemented. |
| **Multi-hospital federation** | Real peers can now register and submit signed parameters, and displace the simulated nodes when they do. Simulated peers remain only as the fallback when nobody has federated yet. |
| **Public IPFS replication** | Content is genuinely pinned to a running node — real CIDs, real blocks, real retrieval — but on one node, which is not the same as replication across the public network. |
| `MedicalRecords` table | Dead schema — 0 references, 0 rows. Marked deprecated in `init.sql` and left in place rather than dropped unilaterally; safe to remove once the team agrees. |

> On AI: the security layer performs **behavioural anomaly detection**, not
> clinical prediction. It never reads medical content and never makes a
> diagnostic judgement. Note also that the "ML" in ML-KEM and ML-DSA means
> *Module-Lattice*, not machine learning — the two are unrelated.

### Known data caveats
- Two lab reports predate the encryption pipeline and hold no ciphertext, so they cannot be given a cloud copy or be decrypted. They are counted honestly in `/api/admin/storage/status`.
- Anchors written before the chain integration are marked `local-simulated` and carry no on-chain proof. The admin Security page reports the on-chain vs simulated split rather than hiding it.

---

## 🧪 Demonstration Dataset

A synthetic dataset at hospital scale, generated by
[`backend/generate_dataset.py`](backend/generate_dataset.py), for showing how
much data the platform carries.

### What it contains

| | Count |
|---|---|
| **Users** | **500** (400 patients, 40 doctors, 30 nurses, 25 technicians, 5 admins) |
| Diagnoses | 806 |
| Prescriptions | 806 |
| Nurse-recorded vitals | 1,821 |
| Medication rounds | 1,633 |
| Nursing notes | 582 |
| Lab test requests | 1,075 |
| **Signed lab reports** | **795** (4.2 MB of PDF, encrypted and anchored) |
| Appointments | 376 |
| **Total rows** | **~8,400** |

Generation takes **37 seconds**, and the database grows to **34 MB**.

### Synthetic identities, genuine cryptography

Only the *names and clinical content* are invented. Everything protecting them
is real, and was verified after generation:

| Property | Verified result |
|---|---|
| ML-KEM-768 public keys | 1,184 bytes — the exact FIPS 203 size |
| ML-DSA-65 public keys | 1,952 bytes — the exact FIPS 204 size |
| ML-DSA-65 signatures | 3,309 bytes — the exact FIPS 204 size |
| Placeholder / mock keys | **0** |
| Diagnoses readable in the database | **0** |
| Medicine names readable in the database | **0** |
| Reports encrypted **and** signed | 802 / 802 |
| Reports with a cloud copy | 802 / 802 |

A patient opening one of these reports through the normal download route gets
back a **valid 1-page PDF**, meaning the AES-GCM decrypt and the signature
check both pass on generated data exactly as on hand-entered data.

Clinical content is coherent rather than random: a diabetic patient carries
metformin, a glucose panel and a raised weight, because a chart full of
unrelated rows would look populated while making no clinical sense.

### Measured capacity

Response times at 515 users and ~8,700 records, mean of 5 requests:

| Endpoint | Latency |
|---|---|
| Patient medical records | 4 ms |
| Patient lab reports | 8 ms |
| Admin user list (page 1 of 26) | 8 ms |
| Admin user list (**last** page) | 8 ms |
| Admin audit log | 11 ms |
| Lab technician report queue | 14 ms |
| Nurse patient list | 37 ms |
| Lab technician pending requests | 76 ms |
| Admin blockchain status | 257 ms |
| Admin storage status | 401 ms |

Deep pagination costs the same as the first page, so the list endpoints are not
scanning the whole table. The two slow endpoints are slow for an honest reason:
they call **out** to the chain and to S3 to report live infrastructure health,
rather than trusting a cached value.

> These are single-machine figures — one laptop, one Postgres, a local chain.
> They are meaningful as *relative* measurements and as evidence the queries
> scale sensibly; they are not production throughput numbers.

### Logging in as a generated user

Password hashes are Argon2 and cannot be reversed, so passwords only exist if
they are captured at creation. The generator writes every account to
`backend/dataset_credentials.csv` (user ID, name, role, password, e-mail) as it
runs.

**Every generated account uses the password `Demo@1234`.**

That file is deliberately **not committed** — a checked-in file full of logins
is a bad habit even when the accounts are synthetic. Regenerate it any time:

```bash
cd backend && python3 generate_dataset.py --reset
```

`--reset` removes only previously generated accounts, identified by their
`@quantumcare-demo.invalid` e-mail marker. Hand-made demo accounts and anything
entered through the UI are matched by nothing in that scope and are left
untouched. `--smoke` generates a 14-user sample; `--no-s3` skips cloud upload.
The random seed is fixed, so a re-run reproduces the same dataset.

---

## 🌐 IPFS Publishing

Content is genuinely published to a running IPFS node — not addressed and left
on disk, which is what this module used to do while a gateway link in the UI
implied otherwise.

```
ciphertext ──► ipfs add --pin ──► node computes CID ──► CID recorded
                                                          │
                     recovery order: database → S3 → IPFS ┘
```

| | |
|---|---|
| Node | kubo v0.43, local daemon |
| CID | computed **by the node**, not by us |
| Pinned | yes — `pin/ls` confirms, retrieval returns byte-identical content |
| Payload | **ciphertext only** |

**Only ciphertext is ever published.** IPFS serves content to anyone who asks
for its hash, so putting a plaintext record there would be a disclosure, not a
storage decision.

Two CIDs legitimately differ and this is asserted in a test so nobody
"fixes" it: `generate_ipfs_cid_v0` hashes the raw bytes, while `ipfs add` wraps
them in a UnixFS node and hashes that. Both are valid CIDv0 values addressing
different objects. Once content is genuinely published, the node's CID is the
one that resolves, so it is the one recorded.

Running without a node is a supported configuration: `pin_to_ipfs` returns
`None` rather than raising, so a hospital that does not run IPFS can still file
reports. `fetch_from_ipfs` does raise, because asking for content that cannot
be had is an error rather than empty data. The admin status endpoint reports
*not configured* separately from *configured but unreachable* — those need
different actions from whoever is on call.

> **Scope.** Pinning on one node is real IPFS but it is not replication. Content
> is reachable while that node runs and is dialable; it is not spread across the
> public network. The status endpoint says exactly this rather than implying
> global availability.

```bash
export IPFS_PATH=~/devtools/ipfs-repo
~/devtools/kubo/ipfs daemon --enable-gc
```

---

## 🔐 Zero-Knowledge Consent Proof

When a patient approves an access request, the system issues the doctor a secret
**consent token**. To exercise that access the doctor proves they know the token
— without ever sending it.

```
patient approves  →  token x issued once   ·   commitment y = g^x stored
                            │
doctor proves     →  t = g^r     r fresh, never reused
                     c = H(g, y, t, challenge, context)
                     s = r + c·x
                            │
server verifies   →  g^s  ==  t · y^c        token never transmitted
```

Schnorr's identification protocol made non-interactive with Fiat–Shamir — the
canonical zero-knowledge proof of knowledge of a discrete logarithm.

**What it buys.** After issuance the secret never crosses the wire again, and a
full database compromise yields only commitments, which are public by
construction. An attacker who reads every row still cannot produce a valid proof.

**Verified by test:** an honest prover is accepted; the wrong token, a replayed
challenge, a proof reused against a different patient, a tampered response, and a
value outside the prime-order subgroup are all refused. The token appears nowhere
in the transmitted proof.

> ### ⚠️ This one component is not post-quantum secure
>
> Schnorr rests on the hardness of discrete logarithm, which **Shor's algorithm
> breaks**. Everything else here — ML-KEM-768, ML-DSA-65 — was chosen precisely
> to resist that attack; this module is the exception, and saying so is the
> point. A quantum adversary who recovered `x` from `y` could forge consent
> proofs, though they still could not decrypt any record: confidentiality does
> not depend on this module.
>
> It is included because a working, textbook-correct ZKP is worth more than an
> empty interface. Post-quantum zero-knowledge exists, but implementing one
> correctly is research-grade work and a broken one would be far worse than none.

The proof runs **alongside** the ordinary consent check, never instead of it. A
proof failing does not open a record, and a proof succeeding does not open one
either — authorization is still decided by relationship and consent state. What
the proof adds is evidence that the party presenting it is the one the patient
actually approved.

---

## 🤖 AI Security Layer

Behavioural threat detection over the healthcare workflow. It analyses **how**
records are touched — never what they contain.

### Where it sits

```
Authentication → RBAC → Consent → ACCESS DECISION
                                        │
                                        ▼
                            (action proceeds or is refused)
                                        │
                                        ▼
                              Security event emitted
                                        │
                          Local anomaly detection (peer baseline)
                                        │
                              Risk score + explanation
                                        │
                    LOW ──── MEDIUM ──────── HIGH
                     │         │               │
                  MONITOR   VERIFY         ESCALATE
                                               │
                                     Alert → Incident → Compliance
```

**The layer never grants or revokes access.** Authentication, RBAC and consent
have already decided that. A statistical model must not be the thing standing
between a clinician and a patient's record; this scores behaviour, explains the
score, and hands a human something to judge.

### How detection works

Six behavioural features per actor — records opened, distinct patients,
off-hours share, failed sign-ins, emergency declarations, busiest hour —
compared against a baseline of **their own role**, so ordinary differences
between a nurse and a doctor are not mistaken for anomalies.

Deviation uses **median absolute deviation**, not standard deviation. A handful
of extreme actors inflate a standard deviation enough to hide inside it, which
is precisely the actor being hunted. Scoring is **one-sided**: a clinician doing
*less* than their peers is not a security concern.

The score comes from the **three strongest indicators** rather than the average
across all six. That was a corrected calibration: normalising over every feature
meant an actor had to be anomalous on nearly every dimension to reach HIGH, so a
doctor sweeping 140 charts at 03:00 with 11 failed sign-ins scored merely
"review". Real misuse is extreme on a subset.

### Explainable AI

The per-feature deviations are the score **and** the explanation — the same
arithmetic, not a second model reconstructing a decision after the fact:

```
DOC-2026-000011   score 85.42   HIGH

  distinct patients accessed        140   vs peer median 1
  failed sign-in attempts            11   vs peer median 1
  busiest single hour               140   vs peer median 9.5
  records opened                    141   vs peer median 3

  → ESCALATE   incident INC-2026-00001 opened
```

### Federated learning — what is real, what is not

| Component | Status |
|---|---|
| FedAvg aggregation, weighted by sample count | **Real** |
| Local baseline fitted from this hospital's activity | **Real** |
| Only parameters (medians, scales) cross the boundary | **Real** |
| Peer registration, signed submission, poisoning floor | **Real** |
| Peer institutions actually running | **Depends on deployment** |

A second QuantumCare instance registers as a peer, fits its own baseline, and
POSTs only its parameters to `/api/federated/submit`. Submissions are HMAC-signed
per peer — without that, anyone who could reach the endpoint could drag the
global baseline wherever they liked and silently blind every participant's
detector. Implausible parameters (negative medians, zero scales) are refused
before aggregation.

**When a real peer submits, the simulated nodes are dropped from the round.**
They exist only to demonstrate the aggregation before anyone has federated;
padding a real round with invented nodes would misrepresent the result. The
endpoint's disclosure states which case applied.

Verified: a signed submission accepted, a forged signature **401**, poisoned
parameters **400**, and a round that ran with **2 real nodes and 0 simulated**.

What federation buys is precise: no record, event or identifier ever leaves the
institution — only the few numbers describing what normal looks like.

### Verified

20 actors across 5 peer groups; a real insider pattern scored **85.42 HIGH**
while 19 benign actors stayed LOW; alert raised with `ESCALATE`; incident
`INC-2026-00001` opened; FedAvg round completed over 4 nodes. 343 events
backfilled from real audit and auth history so the detector had genuine
activity on its first run. 15 tests.

---

## 🔒 Security & Cryptographic Architecture

| Layer | Protocol / Algorithm | Purpose |
| --- | --- | --- |
| **Password Hashing** | **Argon2id** | Memory-hard, GPU-resistant credential protection |
| **PII Encryption** | **AES-256-CBC** | Encrypts sensitive demographics (DOB, blood group) and the clinical text of diagnoses and prescriptions. Defends the database at rest, not a compromised application server — the app holds the key |
| **Key Encapsulation** | **ML-KEM (Kyber-768)** | Post-Quantum Key Encapsulation (FIPS 203) for payload AES keys |
| **Digital Signatures** | **ML-DSA (Dilithium-3)** | Post-Quantum Digital Signature (FIPS 204) for document authenticity |
| **Cloud Storage** | **AWS S3** | Resilient cloud storage bucket (`postquantumcryptography`) |
| **Content Addressing** | **CIDv0 (IPFS multihash format)** | Deterministic fingerprint of the encrypted document. Computed locally — **not** published to the IPFS network |
| **Integrity Anchoring** | **Ethereum (`PHR.sol`)** | Document digests committed on-chain via `DocumentAnchors`; falls back to a labelled local anchor when no chain is reachable |
| **Access Auditing** | **PostgreSQL** | Every read, download and admin action recorded in `AdminAuditLogs` / `AuthLogs` |
| **Consent Enforcement** | **PostgreSQL + RBAC** | A patient's revocation is checked on every doctor-facing read, so withdrawal actually blocks rather than merely records |

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

106 tests, no database or running server required — they exercise pure functions
so they fail for exactly one reason.

What they cover, and why these specific assertions: every test asserts a
*refusal* as well as a success, because a happy-path-only suite would pass
against a verifier that always returns true. That is not hypothetical — this
codebase previously shipped one.

| Area | The property being protected |
|---|---|
| `test_crypto_pipeline.py` | A tampered digest fails verification; a forged signature fails; a mock key never verifies; wrong-key decryption raises; ciphertext does not leak plaintext |
| `test_storage_and_anchoring.py` | A failed upload records no object key; a failed download raises instead of returning placeholder bytes; placeholder credentials read as *unconfigured*; an unreachable chain yields a clearly-labelled local anchor |
| `test_clinical_validation.py` | Impossible vitals (SpO₂ 990%) are rejected while abnormal-but-real ones (SpO₂ 88%) are accepted; past appointment dates are refused; break-glass demands a substantive reason and a bounded duration |
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
