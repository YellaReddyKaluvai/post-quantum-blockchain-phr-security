# 🔐 QuantumCare — Post-Quantum Cryptography & Blockchain Secure Hospital Management System (PHR)

> Post-quantum Personal Health Record platform built on **ML-KEM-768** (FIPS 203), **ML-DSA-65** (FIPS 204), **AES-256-GCM**, encrypted **AWS S3** storage, on-chain integrity anchoring and **PostgreSQL**.

---

## Start here

- [Installation](INSTALL.md): prerequisites, local setup and first login.
- [Working demonstration](backend/demo/WORKING_DEMO.md): captioned video package, repeatable workflow and measured outputs.
- [Deployment](DEPLOY.md): Vercel frontend, Render API/PostgreSQL and migration.
- [Documentation](docs/README.md): architecture, requirements, schema and flows.
- [Contributing](CONTRIBUTING.md): changes, checks, pull requests and history.
- [Repository checklist](docs/11_Repository_Checklist.md): evidence for the technical-repository requirements.
- [MIT license](LICENSE): reuse terms; retain third-party dependency licenses.

**Hosted demonstration:** <https://post-quantum-blockchain-phr-securit.vercel.app>
The hosted baseline has PostgreSQL and post-quantum libraries enabled;
blockchain, IPFS publishing, S3 and SMTP are not configured there. Source
capabilities below do not imply every integration is enabled in the demo.

## Repository layout

```text
backend/                 FastAPI API, crypto and maintenance scripts
  app/                   Application services and routes
  db/init.sql            Database schema
  tests/                 Unit and integration tests
  demo/                  Cryptography demonstrations
frontend/                Next.js application and frontend checks
  src/app/               Role-specific pages
  src/lib/               Session, API and cryptographic utilities
contracts/PHR.sol        Solidity access and integrity contract
docs/                    Architecture, requirements and operational guides
.github/workflows/       Automated checks
INSTALL.md               Local installation and verification
DEPLOY.md                Hosting, migration and operational limits
CONTRIBUTING.md          Contribution and maintenance process
LICENSE                  MIT reuse terms
```

## 🌟 Overview

**QuantumCare** is a research and demonstration healthcare and Personal Health Record (PHR) platform built to defend electronic health records against classical and quantum computing security threats.

The architecture combines **ML-KEM-768** key encapsulation, **ML-DSA-65** digital signatures, **AES-256-GCM** document encryption, encrypted **AWS S3** storage and **on-chain integrity anchoring**.

The design rule throughout: *the system never claims a protection it did not actually apply.* A failed upload records no object key, an unreachable chain produces a visibly-simulated anchor, and a missing post-quantum library raises rather than substituting placeholder keys.

---

## ⚡ Core System Modules

### 1. 🛡️ Administrator Dashboard (`/dashboard/admin`)
- **User Registration Verification & Approval**: Workflow for reviewing and approving newly registered Doctors, Patients, Lab Technicians, and Nurses.
- **Automated Public ID Generation**: Issues sequential identifiers (`PAT-2026-000001`, `DOC-2026-000001`, `LAB-2026-000001`, `NUR-2026-000001`).
- **User Management & Role Access Control**: Active user toggles, status management, and permissions.
- **Cryptographic Key Center**: Live counts of issued ML-KEM / ML-DSA keypairs and active cryptographic identities.
- **Infrastructure Health**: Live blockchain, cloud-storage and IPFS status — chain connectivity and block height, the **on-chain vs locally-simulated** anchor split, how many reports actually have a cloud copy, and per replication target how many documents are confirmed pinned, still queued or failed. Built to surface problems rather than imply everything is fine.
- **Federation Peers**: Register a peer institution (its HMAC secret is shown once), and suspend or reinstate it; a suspended peer's submissions are refused.
- **Emergency Access Review**: Every break-glass declaration with its verbatim clinical reason, both parties, expiry and on-chain transaction hash. Active declarations are surfaced first.
- **AI Security**: Behavioural anomaly detection over record access — alerts to work, risk scores with the attribution that produced them, incident records, and the federated IDS panel with its honesty disclosure beside the node count.
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
- **Access Requests**: Ask a patient you are not already treating for permission to read their record, with a clinical reason they will read before deciding. Track every request through pending, approved and declined.
- **Imaging**: Studies for patients you treat or who have granted you access, decrypted one at a time with their provenance shown.
- **Medication Adherence**: On the patient chart — whether the prescription is actually being taken, with refusals and missed doses called out rather than averaged away.
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
- **Access Requests**: Doctors asking permission to read your record, with their stated reason. Nothing is shared until you decide.
- **My Scans**: X-ray, MRI, CT and ultrasound studies, decrypted on request with the signing algorithm and chain anchor shown.
- **Medication History**: Every dose nursing staff recorded — given, refused, held or missed.
- **Record Access**: Every clinician who can read the record and how that relationship arose, with one-click withdrawal. Revoking genuinely blocks reads rather than merely noting a preference; an active emergency override is shown plainly.
- **Security & Privacy Center**: PQC protection status, active session logs, and login IP tracking.
- **Notification Feed**: Report readiness, appointment updates, and vitals alerts.

### 5. 🩺 Nurse Dashboard (`/dashboard/nurse`)
- **Patient Chart**: Vitals entry, nursing notes, and medication rounds in one view.
- **Vitals Recording**: Temperature, blood pressure, heart rate, SpO₂, respiratory rate, weight and height. Out-of-range readings are flagged at the point of entry and the attending doctor is alerted automatically.
- **Nursing Notes**: Observation, Care and Incident entries, visible to the treating doctor.
- **Medication Administration**: Records each round against the prescription as Administered, Refused, Held or Missed, with the last outcome shown per medicine.

> Vitals recorded here are readable by the treating **doctor** and by the **patient**. Nursing notes go to the doctor only — they are clinical handover between staff.
>
> **A nurse sees only their care team.** Access to a patient is an assignment — made by a doctor who is already authorized for that patient (and lasting only while that doctor's access does) or by an administrator as a ward allocation — time-boxed, visible to the patient, and ended rather than deleted. Search covers the care team only.

---

## 🔄 End-to-End Data Flow

How data moves between the five roles through the implemented application workflows.

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

### 5. Doctor asks, patient decides

```
Doctor with NO treating relationship
      → requests access, clinical reason required
      → ACCESS_REQUEST notification to the patient
      → patient approves or declines
            ├─ approve → consent token issued (once) + commitment stored
            │            decision anchored on-chain
            └─ decline → reads stay refused
      → backend enforces: 403 / 403 / 403 / 200 across the four states
```

A doctor already treating the patient reads on that relationship — making an
oncologist file a form before opening the chart of someone they are actively
treating is the kind of obstruction clinicians route around. A doctor with no
relationship has no implicit access at all.

The doctor can later prove they hold the consent token **without sending it**
(a post-quantum lattice zero-knowledge proof). That proof neither opens nor closes a record; it evidences that
the party presenting it is the one the patient approved.

### 6. Patient → appointment → Doctor

```
Patient books (past dates and unknown doctors refused at the schema)
      → status Pending → APPOINTMENT_REQUEST notification to doctor
      → Doctor accepts / completes / cancels
      → ✗ patient is not notified of the outcome (see below)
```

### 7. Consent and break-glass

```
Patient approves / withdraws a doctor's access
      → Consent row  +  PHR.sol updateConsent()   (pseudonymous refs, when a chain is up)
      → every doctor-facing read checks the row; a read that rests on consent
        also asks the contract (checkConsent) — disagreement refuses access
        and opens a CONSENT_LEDGER_MISMATCH incident
      → CONSENT_* notification to the doctor

Doctor declares emergency access
      → re-enters their password                    (identity verification)
      → at most EMERGENCY_MAX_PER_DAY per doctor     (rate limit)
      → scored by the AI risk gate, emergency policy
      → overrides the withdrawal, time-boxed ≤24h
      → EMERGENCY_ACCESS notification to the patient immediately
      → anchored on-chain + PHR.sol emergencyAccess()
      → compliance incident opened automatically for review
```

Break-glass is deliberately **not** gated on a second person's approval —
waiting for one in an emergency defeats the purpose. It is not a silent bypass
either: identity is re-verified, frequency is limited, behaviour is scored, the
patient is told, and every override becomes a compliance record someone must
close with a resolution.

### 8. Everything is audited

```
Every admin action, record access and download
      → AdminAuditLogs
Every login attempt
      → AuthLogs
Every finalised document, consent decision and break-glass declaration
      → DocumentAnchors + on-chain transaction
Every sign-in, read, refusal, consent decision, upload and failed check
      → SecurityEvents (the AI layer's input — metadata only, never content)
```

### 9. Every access passes the security layer

```
authenticated → RBAC → relationship / consent (+ on-chain consent check)
      → AI risk gate: this actor, scored now against their role's baseline
          (the federated model when real institutions built one, else local)
      → LOW allow · MEDIUM monitor · HIGH re-enter password     ← configurable
      → release: decrypt → digest check → ML-DSA signature check
          (a failure withholds the record and opens an incident)
      → SecurityEvent → scheduled anomaly analysis → alerts → incidents
```

The gate only ever makes access stricter: a low score cannot open a record that
consent closed. What MEDIUM and HIGH do — monitor, ask for the password again,
or refuse — is a policy setting, shown on Admin → AI Security. A refused
attempt is itself recorded, so probing for records raises an alert.

---

## 📊 Implementation Status

Implemented features and their verification evidence are summarized below.
See [Deployment](DEPLOY.md) for the hosted configuration.

### Working end-to-end

| Area | State | Notes |
|---|---|---|
| Registration → admin approval → login | ✅ | Permanent role-scoped User IDs; real SMTP approval/rejection email — **verified live in CI**: the approval mail is read back from a mail server (Mailpit), addressed to the patient and carrying their User ID |
| Post-quantum key issuance | ✅ | Real ML-KEM-768 + ML-DSA-65 via liboqs, generated on approval |
| Doctor → Lab → Patient report pipeline | ✅ | 9 structured panels → hospital PDF → AES-256-GCM → ML-KEM → ML-DSA → chain anchor |
| Imaging studies | ✅ | Encrypted, signed, anchored — and now readable by the patient and by an entitled doctor |
| Nurse module | ✅ | Vitals, notes and medication rounds all reach the doctor and the patient; a nurse reaches a patient only through a care-team assignment. Existing nurse–patient work is listed for an administrator to review and allocate |
| Cloud storage (AWS S3) | ✅ | Ciphertext only, verified; doubles as a recovery path if the database copy is lost. **Verified live in CI** against SeaweedFS's S3 gateway (`AWS_S3_ENDPOINT_URL` takes any S3-compatible store): the object is exactly the ciphertext, and a report whose database copy is removed is still released from S3 |
| Patient security notifications | ✅ | A record withheld after failing its integrity or signature check, consent altered against the blockchain, repeated refused attempts at a chart — the patient is told, with the incident reference; only Patient accounts are ever notified |
| Encryption-key rotation | ✅ | `rotate_encryption_key.py` moves every encrypted column (personal fields, clinical text, post-quantum private keys) to a new key: strict decryption, every value verified, one locked transaction, dry run by default |
| Blockchain anchoring | ✅ | Real on-chain writes via `PHR.sol` (writes restricted to the backend's key); falls back to a clearly-labelled local anchor. **Verified live in CI** against anvil: consent written on-chain, report digests read back, break-glass through `emergencyAccess()`, a consent row edited in SQL refused as a mismatch |
| Session handling | ✅ | 30-minute tokens; expiry redirects to login and returns you to where you were |
| RBAC across 5 roles | ✅ | Enforced server-side; backend/frontend permission parity is test-enforced |
| Doctor-authored documents | ✅ | Encrypted, signed and anchored — and readable by the patient they concern, completing the spec's "patient receives authorized access" |
| Clinical record encryption | ✅ | Diagnoses and prescriptions encrypted at column level; grepping the database for a diagnosis returns nothing |
| Consent management | ✅ | Revoking a doctor genuinely blocks reads — the same report returns 200 before and 404 after |
| Smart-contract consent | ✅ | Decisions written to `PHR.sol` (`updateConsent`, pseudonymous refs); consent-based reads refused if the contract's `consentStatus` disagrees with the row. **Verified live in CI** against anvil (see Blockchain anchoring) |
| Doctor access requests | ✅ | Doctor requests with a stated purpose → patient approves or declines → the backend enforces it. Verified: no request 403, pending 403, rejected 403, approved 200 |
| AI security layer | ✅ | Anomaly detection (scheduled, and inline at every clinician read), XAI explanations, configurable risk policy with password re-verification, alerts from every security source, incidents worked to closure |
| Zero-knowledge consent proof | ✅ | **Post-quantum**: lattice proof (Fiat–Shamir with aborts, ML-DSA-65 parameters), **made in the doctor's browser** — the token never leaves it. The TypeScript prover and the Python verifier are checked against each other in CI. Consents approved before the switch keep their Schnorr commitment, which still verifies and is reported as *not* post-quantum. See its own section |
| IPFS publishing | ✅ | Really pinned to a running kubo node; joins the recovery chain behind the database and S3. **Verified live in CI** with two kubo daemons: the stored object is exactly the ciphertext, and replication is confirmed by the replica's own pin list |
| IPFS replication | ✅ | Copies on other IPFS nodes and/or Pinning-Service-API providers; only copies a target confirms count. **Verified live in CI** against a second kubo node; a commercial pinning service is unit-tested against a scripted fake only |
| Federation peer admin screen | ✅ | Register a peer (secret shown once), rotate its secret, suspend, reinstate. **Verified live in CI**: Chromium drives the built frontend against a running backend, and the API is asked afterwards whether it agrees |
| Medication adherence | ✅ | Refusals and misses reach the prescriber and the patient, not only a percentage |
| Emergency break-glass access | ✅ | Password re-verification, daily limit, risk-scored, time-boxed, patient notified immediately, anchored on-chain, compliance incident opened automatically |
| End-to-end flow (spec §37) | ✅ | `tests/test_e2e_flow.py` drives access request → consent → nurse care team → lab request → signed, encrypted report → patient release → tamper detection → withdrawal → break-glass → incidents and audit, against real Postgres and real liboqs. CI runs it twice: database-only, and with the chain, IPFS and a second hospital live |
| Browser sessions | ✅ | The session token lives only in an HttpOnly cookie (scripts cannot read it); CORS is limited to `CORS_ORIGINS`; a cookie-authenticated change needs an `X-Requested-With` header (CSRF); each token has an id checked on every request, so logout revokes it and disabling a user ends their sessions at once |
| Consent-token storage | ✅ | Sealed in the browser with AES-256-GCM under **a passkey** — the key comes from the device's authenticator through the WebAuthn PRF extension, so nothing secret is typed — or under a passphrase where no such authenticator exists. Backups are the sealed form; tokens stored before this are flagged with a one-step protect. Checked in CI by `scripts/check-vault.mjs` and, with a virtual authenticator, in the browser |
| Differential privacy across rounds | ✅ | Every classifier release is recorded with its zCDP cost and composed across rounds into a total (ε, δ); `FEDERATION_DP_TOTAL_EPSILON` stops releases at the budget; a release without noise voids any overall claim and is shown as such |
| Late anchoring | ✅ | Anchors recorded while no chain was reachable can be written on-chain later (Admin → Security), marked `LATE_ANCHOR` on the chain itself: they prove the digest existed by that block, not at the original time |
| Anchor provenance | ✅ | A digest verifies only from events our own contract (or a listed previous one) emitted — a look-alike contract's event does not count |
| Automated tests | ✅ | 459 Python tests plus a Foundry contract suite and a browser-prover vector check; weighted toward refusals. CI runs them inside the backend image, where liboqs is real |
| Federated learning between hospitals | ✅ | Per-role baselines **and a threat classifier trained on investigated incidents**, federated with robust FedAvg, clipped updates and optional differential privacy; each global model evaluated locally before adoption, with rollback. **Verified live in CI across three hospitals** (separate servers and databases), over two training rounds |

Every row above is ✅: nothing in this table is still waiting to be tried on a running system.

---

## 🧪 Demonstration Dataset

### Records in the hosted demonstration

The public app uses its hosted PostgreSQL database. Its demonstration accounts
were created through the application and approved by an administrator; they
are not the example IDs from the local 500-account dataset generator.

On **25 October 2026**, the following records were read successfully through
the deployed patient API while signed in as `PAT-2026-000002`:

| Record | Count in this demo patient's account |
|---|---:|
| Completed lab reports | 1 |
| Vitals entries | 1 |
| Medical records | 1 |

These are fictional demonstration records stored in the hosted database.
They are not totals for every user or record in the deployment. Start with
this patient to see the recorded demonstration's clinical review and CBC report.

See [verified hosted accounts](#verified-hosted-demo-accounts) for the working
User IDs and [account verification evidence](docs/demo-results/2026-10-25-account-verification.json)
for the dated checks. Accounts and access can change after verification; nurse
assignments are time-limited and patient consent still governs clinician access.

### Reproduce the hosted workflow

[The working-demonstration guide](backend/demo/WORKING_DEMO.md) explains how to
create a fresh set of fictional accounts, exercise the workflow and export
results. The runner obtains assigned IDs from the API and saves each account's
own password in a private file. It does not assume IDs or a shared password.

[Measured run results](docs/demo-results/2026-10-25-summary.md) and
[raw timing/configuration evidence](docs/demo-results/2026-10-25-results.json)
record the separate end-to-end demonstration run. They are dated observations,
not live database totals or throughput claims.

### Optional local dataset generator

[`backend/generate_dataset.py`](backend/generate_dataset.py) can populate a
separate disposable development database with a larger synthetic dataset.
That dataset has **not** been imported into the hosted demonstration. Its
example IDs, passwords, row counts and local timings do not describe the public app.

Use the generated `backend/dataset_credentials.csv` for the actual local
account IDs and passwords. This file is gitignored. The generator uses shared
demo credentials, so run it only against a disposable database. `--smoke`
creates a smaller sample; `--no-s3` skips cloud upload. `--reset` deletes the
previous generator-owned accounts and should be used only when that reset is intended.

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

```bash
export IPFS_PATH=~/devtools/ipfs-repo
~/devtools/kubo/ipfs daemon --enable-gc
```

### Replication

Pinning on one node is real IPFS but it is not resilience: content is reachable
only while that node runs and is dialable. Replication keeps further copies
elsewhere, using either or both of:

| Target | Configure | How a copy is made |
|---|---|---|
| Other IPFS nodes — a second site, a teammate's node, a cloud VM | `IPFS_REPLICA_NODES=http://host-a:5001,http://host-b:5001` | The replica is dialled to this node (`swarm/connect`), then asked to `pin/add` the CID; bitswap moves the blocks. Confirmed synchronously |
| Pinning services — any provider of the [IPFS Pinning Service API](https://ipfs.github.io/pinning-services-api-spec/) (Pinata, Filebase, 4EVERLAND, …) | `IPFS_PINNING_SERVICES='[{"name":"pinata","endpoint":"https://api.pinata.cloud/psa","token":"…"}]'` | The CID is submitted with this node's addresses as origins; the service fetches it and reports `queued` → `pinning` → `pinned` |

```
document filed ─► pinned on this node ─► background job ─► each target ─► IpfsReplicas row
                                                                          (status the target reported)
```

- **Only confirmed copies count.** A request a service has merely queued is
  recorded as `queued`, not as a copy; an unreachable target is `failed` with its
  error. The admin Security page shows, per target, how many CIDs are pinned,
  in progress and failed, and the fewest copies any document has.
- **Never blocks a clinician.** Replication runs in a background thread after
  the report is saved. A slow or broken target costs nothing at filing time.
- **Backfill and retry.** *Admin → Security → Replicate missing copies* (or
  `POST /api/admin/ipfs/replication/sync`) polls services about queued requests
  and requests copies for every published document a target does not yet hold.
  CIDs recorded while no node was running were never published and are skipped.
- **Only ciphertext**, as before — the same bytes the primary node already
  serves to anyone with the CID. Service tokens are never returned by any
  endpoint.

> **Status.** Tested against a scripted HTTP fake (17 tests: confirmed vs queued,
> one failing target not stopping the others, a failed status check not
> downgrading a pin, malformed configuration reported). It has not yet been run
> against a real second node or a real pinning service.

---

## 🔐 Zero-Knowledge Consent Proof

When a patient approves an access request, the system issues the doctor a secret
**consent token**. To exercise that access the doctor proves they know the token
— without ever sending it. The proof is **post-quantum**: it rests on the same
lattice problems as ML-DSA-65 rather than on discrete logarithm.

```
patient approves  →  token ξ issued once
                     A = ExpandA(ρ),  s1, s2 short (from ξ)
                     commitment (ρ, t = A·s1 + s2) stored
                            │
doctor proves     →  y fresh,  w = A·y1 + y2
                     c = H(t, w, challenge, context)
                     z = y + c·s      abort and retry unless ‖z‖∞ < γ1 − β
                            │
server verifies   →  ‖z‖∞ < γ1 − β   and   c == H(t, A·z1 + z2 − c·t, …)
                                              token never transmitted
```

Lyubashevsky's identification scheme made non-interactive with Fiat–Shamir
"with aborts" — the construction ML-DSA itself is built on — over
Z_q[X]/(X²⁵⁶+1) with ML-DSA-65's parameters (q = 8 380 417, 6×5 matrix,
η = 4, τ = 49, γ1 = 2¹⁹). Code: [`zkp_lattice.py`](backend/app/zkp_lattice.py).

- **Hiding the token** is Module-LWE; **forging a proof** yields a Module-SIS
  solution of the same shape and order of bound as in ML-DSA-65's analysis.
- **Zero-knowledge comes from the abort.** z = y + c·s alone would leak s; keeping
  only z inside the smaller box makes every accepted z uniform whatever s is.
  `simulate_transcript` makes this executable — it produces accepting transcripts
  with no secret at all, and a test checks they verify.
- **Size and speed:** commitment 4.4 KB, proof 7 KB; about 0.1 s to prove and
  0.04 s to verify in pure Python. Nothing is compressed (no HighBits or hint),
  so it is larger than an ML-DSA signature but short enough to read line by line.

**What it buys.** After issuance the secret never crosses the wire again, and a
full database compromise yields only commitments, which are public by
construction. An attacker who reads every row still cannot produce a valid proof
— now including one with a quantum computer.

**Verified by test (43):** the NTT agrees with schoolbook multiplication; an honest
prover is accepted; the wrong token, another commitment, a replayed challenge, a
proof for a different patient, a tampered response or challenge hash, a response
on the norm bound, and a long "solution" that satisfies the equation are all
refused; malformed input returns false rather than crashing; the token appears in
neither proof nor commitment. Three deliberate mutations — no abort, no norm check
in the verifier, context dropped from the hash — each make a test fail.

**Making a proof.** The token never goes back to the server, so proofs are made
where it is kept. On the patient's page a doctor collects the token once and
then presses **Prove consent**: the browser asks for a challenge, proves locally
with `frontend/src/lib/zkpLattice.ts` (a line-for-line port of the Python
module, ~20–40 ms), checks the proof against the commitment, and sends only the
proof. `backend/tests/fixtures/zkp_vectors.json` holds a fixed token, its
commitment and a proof from each implementation; the Python suite verifies the
browser's proof and `frontend/scripts/check-zkp.mjs` (run in CI) verifies
Python's. Outside the browser, the same proof from the command line:

```bash
# token from GET /api/doctor/consent-token/{patient_id} (delivered once)
# challenge + context from POST /api/doctor/zkp/challenge?patient_id=...
QUANTUMCARE_CONSENT_TOKEN="mlwe1:…" python demo/zkp_prove.py \
    --challenge <challenge> --context "consent:<patient_id>" > proof.json
# then POST proof.json to /api/doctor/zkp/verify
```

> ### Honest limits
>
> - The construction uses ML-DSA-65's parameters and assumptions, but it is not
>   itself a NIST-standardised scheme, and this implementation has not been
>   independently reviewed.
> - Python big-integer arithmetic is not constant-time. Only the prover handles
>   the secret, and it runs on the doctor's side; the server only verifies public
>   values.
> - Consents approved **before** the switch carry Schnorr commitments. Those
>   still verify — every response then says `post_quantum_secure: false` and
>   explains why — until the patient withdraws and re-approves, which issues a
>   lattice token. Confidentiality never depended on this module either way.

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
Authentication → RBAC → relationship / consent ──── refused ──► ACCESS_DENIED event
                                │ permitted                      (repeated → alert)
                                ▼
             AI RISK GATE  (this actor, scored now, own-role baseline)
                                │
          LOW ──────── MEDIUM ──────────── HIGH          (configurable policy)
          allow        monitor            verify: re-enter password
                       + alert            + alert + incident   (or block)
                                │
                                ▼
            release → digest + ML-DSA signature verified → SecurityEvent
                                │
              Scheduled analysis (every 30 min) + on demand
                                │
                     Risk score + explanation (XAI)
                                │
                  Alert → Incident → worked to Closed (compliance)
```

**The layer never grants access.** Authentication, RBAC and consent decide that
first, and a low score cannot open a record they closed. It can make access
*stricter* — by default only by asking a HIGH-risk user to re-enter their
password, which stops a stolen session without stopping a clinician. Whether
MEDIUM/HIGH monitor, verify or block is the configured policy
(`RISK_POLICY_*`), visible on Admin → AI Security. Roles with fewer than
`RISK_MIN_PEERS` actors are not scored at all: with two technicians, "unusual"
would only mean "busier than the other one".

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
EXAMPLE-DOCTOR   score 85.42   HIGH

  distinct patients accessed        140   vs peer median 1
  failed sign-in attempts            11   vs peer median 1
  busiest single hour               140   vs peer median 9.5
  records opened                    141   vs peer median 3

  → ESCALATE   incident INC-2026-00001 opened
```

### Federated learning — what is real, what is not

The federated IDS has two models, both learned locally and federated:

| Model | What it learns | What leaves the hospital |
|---|---|---|
| **Per-role behaviour baselines** | What normal looks like for each role (median and spread of 7 behavioural features) | Medians and scales per role |
| **Threat classifier** | Which behaviour investigators *confirmed* as a threat — trained on incidents closed with a verdict | 7 weights and a bias, clipped (and optionally noised) |

| Component | Status |
|---|---|
| Local training: baselines from this hospital's activity; the classifier from its investigated incidents, starting each round from the global weights | **Real** |
| Robust FedAvg, for both models: each node weighted by its samples but capped at 5× the lower-median node, and with 3+ nodes an outlying update set aside (baselines per role, compared in log space). Who was capped or set aside is reported at the hub and never sent to peers | **Real** |
| Privacy: no record, event, label or identifier is sent; classifier updates are clipped, and `FEDERATION_DP_EPSILON` adds Gaussian noise (the Gaussian mechanism per round — no accounting across rounds is claimed) | **Real** |
| Signed, replay-protected exchange: every submission carries a signed timestamp and the hub takes only a fresh one newer than the last from that peer; the hub signs the model it returns for the requesting peer and request, and a participant refuses one altered or replayed in transit | **Real** |
| Peer control: registration, suspension (a suspended peer's earlier updates are left out of new rounds), secret rotation; submissions only to the open round; per-role counts bounded and consistent with the total; an update older than 7 days is not carried into a round | **Real** |
| The hub's own adoption gate: each round is evaluated on the hub's data exactly as a participant evaluates a pulled one, and detection at the hub uses it only if it passes | **Real** |
| Adoption gate: a pulled model is evaluated on local data and used only if it does not make detection here worse; every model kept, any one activatable, rollback to local-only | **Real** |
| Detection: risk = the higher of the anomaly score and the classifier's threat probability, explained per feature by whichever model spoke | **Real** |
| Automation: hub rounds when real peers have submitted (`FEDERATION_ROUND_INTERVAL_MINUTES`, `FEDERATION_MIN_PEERS`); participant sync (`FEDERATION_SYNC_INTERVAL_MINUTES`) | **Real** |
| Joining a federation from the admin screen (secret encrypted at rest) or by environment variables | **Real** |
| **Three hospitals in CI**, each a separate server and database | **Verified** — see below |
| Independent institutions actually federating | **Depends on deployment** |

```
Hospital A, C (participants)                            Hospital B (hub)
incidents closed with a verdict → labels
train classifier from the global weights
fit per-role baselines
clip (+ DP noise) · sign ── update ──────────────────►  /api/federated/submit
                                                         round: per-role FedAvg +
                                                         robust FedAvg of classifiers
evaluate on local data ◄── signed pull ──────────────── /api/federated/global-model
adopt if it is no worse here; else keep it for review    (real institutions only)
risk engine: max(anomaly score, threat probability)
```

Per role, because detection compares each actor with their own role: an
all-roles average would describe nobody and flag doctors and technicians alike
for being themselves. Logistic regression, because it trains from tens of
labelled incidents, FedAvg averages it exactly, and every prediction decomposes
into per-feature contributions — the Explainable AI view works for it as it does
for the anomaly score.

**When a real peer submits, the simulated nodes are dropped from the round.**
They exist only to demonstrate the aggregation before anyone has federated, add
baselines but never classifier weights, and a model that includes them never
scores anyone.

**Verified.** Unit tests (`tests/test_federated_learning.py`): the classifier
learns; three hospitals with a handful of incidents each converge over FedAvg
rounds to a model that works on all three; clipping bounds the step; the noise
has the stated scale; a node claiming a million examples cannot buy the model;
a poisoned update is set aside; a poisoned global classifier is refused on local
incidents; global baselines that would flag this hospital's normal staff are
refused. Live in CI (`tests/test_federation_live.py`), three hospitals as separate
servers and databases: A and C join through the admin API, train on their own
investigated incidents and submit; B aggregates (2 real peers, 0 simulated); both
pull and adopt; a second round starts from the global weights; A rolls back to
local models and re-activates an older global one; B is checked to hold no labels
and nothing A stored names a node or a person. Then B's defences, against the
running servers: A's captured submission replayed is refused; one correctly
signed for a round not yet open is refused; C's secret is rotated, its old one
stops working at once and the new one works; A is suspended, cannot submit, and
B's next round is built without it. Hub-side refusals one by one, and the
participant refusing an unsigned, altered or replayed model, are unit-tested
(`tests/test_federation_hub.py`, `tests/test_security_architecture.py`).

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
| **Content Addressing** | **IPFS (CIDv0)** | The encrypted document is pinned on this hospital's node when one is configured, and replicated to further nodes or pinning services when those are configured; otherwise a CID is computed locally and nothing is published |
| **Consent Proof** | **Lattice ZKP (Module-LWE/SIS, ML-DSA-65 parameters)** | A doctor proves they hold the consent token without sending it; post-quantum. Pre-switch consents keep a Schnorr proof, reported as not post-quantum |
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

Follow [INSTALL.md](INSTALL.md) for prerequisites and complete commands. It
starts PostgreSQL and the API in Docker, configures the frontend proxy, creates
the first administrator and verifies patient registration, approval and login.
The image builds the required native liboqs library.

For the Vercel frontend with a Render API and database, use [DEPLOY.md](DEPLOY.md).
Do not copy example passwords or encryption keys into a live deployment.

### Running the Tests

```bash
cd backend
python3 -m pytest
```

The suite includes unit tests and opt-in live integration tests. Without
liboqs the post-quantum tests skip; live database, chain, storage and browser
checks need their configured services and opt-in flags. The
[CI workflow](.github/workflows/deploy.yml) is the authoritative setup.
Report skipped tests rather than treating them as passed.

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
| `test_zkp_lattice.py` | Ring arithmetic matches a schoolbook reference; every forgery, replay, cross-patient and cross-scheme proof is refused; the abort and the verifier's norm check each hold on their own |
| `test_ipfs_replication.py` | A queued request is never counted as a copy; one failing target does not stop the rest; a failed status check does not downgrade a pin; service tokens never appear in a report |
| `test_security_architecture.py` | The default risk policy never blocks care; an insider sweep is challenged *with* its explanation; refusals, failed sign-ins and tampering reach alerts and incidents without duplicating them; the chain contradicting a consent row is a mismatch, an unreachable chain is "unverified" not "agreed"; hub requests are signed, fresh and purpose-bound; chart writes, lab orders and report filing need entitlement |
| `test_e2e_flow.py` | The whole §37 flow against real Postgres and real liboqs (CI only — opt-in with `RUN_E2E=1`) |

The suite was checked by mutation: reintroducing three real past bugs — a
signature verifier that always returned true, an upload that recorded a key it
never wrote, and a dropped vitals validator — made 7, 1 and 2 tests fail
respectively.

### Blockchain Audit Trail

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

Sign in to the deployed platform: **[QuantumCare Login](https://post-quantum-blockchain-phr-securit.vercel.app/login)**.

`http://localhost:3000` applies only when running the frontend on your own computer.

---

## 🔑 Signing in and demo accounts

**[Open the public login page](https://post-quantum-blockchain-phr-securit.vercel.app/login)**

Sign in with the **User ID**, not an email address. Use the password assigned
when that particular account was created. The local dataset generator's shared
password does not work for the hosted accounts below.

### Verified hosted demo accounts

All four accounts below successfully authenticated and returned the expected
role from `/api/auth/me` on **25 October 2026**. They are the existing fictional
accounts used for the captioned project demonstration.

| Role | Actual hosted User ID | Demonstration |
|---|---|---|
| **Patient** | `PAT-2026-000002` | Clinical record, recorded vitals and completed CBC report |
| **Doctor** | `DOC-2026-000001` | Patient access subject to consent; clinical review and lab request |
| **Nurse** | `NUR-2026-000001` | Care-team access subject to assignment and consent; nursing observations |
| **Lab Technician** | `LAB-2026-000001` | Completed report from the demonstration's CBC request |

Passwords are supplied privately by the project owner and are not stored in
Git. There is no shared hosted demo password. Do not use the older local-dataset
IDs to sign into this deployment. The administrator account is managed privately
and is not a public demo login.

The [verification record](docs/demo-results/2026-10-25-account-verification.json)
contains the tested IDs and results without passwords, session tokens or keys.
For a demonstration without account access, use the
[public captioned video](https://post-quantum-blockchain-phr-securit.vercel.app/#project-demo).

### Accounts on a new local installation

A fresh installation has no pre-created accounts. Run `backend/seed_admin.py`
as described in [INSTALL.md](INSTALL.md). It uses a private `ADMIN_PASSWORD`
or generates a random password printed once. Re-running it does not reset an
existing account. Register other roles through `/signup`, approve them as an
administrator, and use the assigned User ID with the registration password.

For accounts created by the optional local dataset generator, read the actual
credentials from `backend/dataset_credentials.csv` in that installation.
