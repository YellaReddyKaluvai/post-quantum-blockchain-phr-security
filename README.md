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

Verified against the running system, not aspirational. Anything not built is
listed as not built.

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
| Smart-contract consent | 🟡 | Decisions written to `PHR.sol` (`updateConsent`, pseudonymous refs); consent-based reads refused if `checkConsent` disagrees with the row. Unit-tested with a fake chain — **not yet run against a live chain** |
| Doctor access requests | ✅ | Doctor requests with a stated purpose → patient approves or declines → the backend enforces it. Verified: no request 403, pending 403, rejected 403, approved 200 |
| AI security layer | ✅ | Anomaly detection (scheduled, and inline at every clinician read), XAI explanations, configurable risk policy with password re-verification, alerts from every security source, incidents worked to closure |
| Federated learning loop | 🟡 | Per-role FedAvg; a hospital can submit its signed per-role update to a hub and pull the global model back; detection uses a global model only when real institutions built it. Tested against a fake hub — **not yet between two running hospitals** |
| Zero-knowledge consent proof | ✅ | **Post-quantum**: lattice proof (Fiat–Shamir with aborts, ML-DSA-65 parameters), **made in the doctor's browser** — the token never leaves it. The TypeScript prover and the Python verifier are checked against each other in CI. Consents approved before the switch keep their Schnorr commitment, which still verifies and is reported as *not* post-quantum. See its own section |
| IPFS publishing | ✅ | Really pinned to a running kubo node; joins the recovery chain behind the database and S3. **Verified live in CI** with two kubo daemons: the stored object is exactly the ciphertext, and replication is confirmed by the replica's own pin list |
| IPFS replication | 🟡 | Copies on other IPFS nodes and/or Pinning-Service-API providers; only copies a target confirms count. Unit-tested against a scripted HTTP fake — **not yet run against a real second node or pinning service** |
| Federation peer admin screen | 🟡 | Register a peer (secret shown once), suspend, reinstate. Rendered and exercised against sample data — **not yet against a live backend** |
| Medication adherence | ✅ | Refusals and misses reach the prescriber and the patient, not only a percentage |
| Emergency break-glass access | ✅ | Password re-verification, daily limit, risk-scored, time-boxed, patient notified immediately, anchored on-chain, compliance incident opened automatically |
| End-to-end flow (spec §37) | ✅ | `tests/test_e2e_flow.py` drives access request → consent → nurse care team → lab request → signed, encrypted report → patient release → tamper detection → withdrawal → break-glass → incidents and audit, against real Postgres and real liboqs. CI runs it twice: database-only, and with the chain, IPFS and a second hospital live |
| Automated tests | ✅ | 413 Python tests plus a Foundry contract suite and a browser-prover vector check; weighted toward refusals. CI runs them inside the backend image, where liboqs is real |
| Federated learning between hospitals | ✅ | Per-role baselines **and a threat classifier trained on investigated incidents**, federated with robust FedAvg, clipped updates and optional differential privacy; each global model evaluated locally before adoption, with rollback. **Verified live in CI across three hospitals** (separate servers and databases), over two training rounds |

🟡 = built and tested in isolation, still to be verified on the running system.

---

## ⚠️ Incomplete Workflows

Flows that start but do not finish. Nine have been closed so far; what remains
is listed honestly rather than quietly dropped.

### Closed

| Workflow | What was wrong | Now |
|---|---|---|
| **Imaging → clinician / patient** | Encrypted, signed, anchored — and openable only by the uploading technician. The patient was notified about something they could not reach. | Patient and entitled doctor both read studies, through one shared release path |
| **Medication adherence → prescriber** | Every round recorded; no endpoint ever returned it. A refusal was stored and never surfaced. | Doctor sees it on the chart, patient sees their own history; refusals reported in their own right |
| **Appointment outcome → patient** | Accept, complete and cancel notified nobody, so a cancelled appointment was one the patient turned up for. | Every outcome reaches the patient |
| **Lab request → laboratory** | The only role in the system not told when work arrived for it. | All technicians notified, priority marked |
| **Report reviewed → patient** | The moment the patient is really waiting for went unannounced. | Patient told a clinician has read their result |
| **Post-quantum ZKP** | The consent proof was Schnorr, which Shor's algorithm breaks. | New consents get a lattice proof under Module-LWE/SIS; old Schnorr commitments still verify and are labelled not post-quantum |
| **IPFS replication** | Content was pinned on one node only. | Each new CID is replicated in the background to configured replica nodes and pinning services; an admin can backfill and retry from the Security page |
| **Peer registration UI** | Peers could only be registered by API call. | Admin → Federation Peers: register (secret shown once), suspend, reinstate |
| **`MedicalRecords` table** | Dead schema, never read or written. | No longer created; dropped from existing databases only while empty |
| **Lab request → consent** | Ordering a test needed nothing, and a lab request counts as a treating relationship — one order for any patient unlocked their whole chart. | The ordering doctor must already be entitled to the patient |
| **Chart writes → authorization** | Diagnoses, prescriptions, consultations and documents could be written to any patient, which then also counted as a treating relationship. | Writing needs the same entitlement as reading |
| **Report ↔ request binding** | The requested investigation was loaded and never compared; any technician could file any panel against any order. | The panel must match the order, and only the technician holding the request can file or advance it |
| **Signature on release** | A failed ML-DSA check was logged and the report released anyway; documents and scans were never checked. | Every release verifies digest and signature; a failure withholds the record and opens an incident |
| **Failures → Alert & Response** | Integrity and signature failures, refusals and break-glass produced no alert or incident; only the anomaly model did. | Every security source reports to one alert queue, with its source shown |
| **Failed sign-ins → AI** | Written to AuthLogs, which the detector never reads. | Recorded as security events as they happen; a burst on one account alerts |
| **Break-glass → AI** | The event was written through a closed cursor and silently lost. | Recorded, scored, and turned into a compliance record |
| **Incident lifecycle** | Incidents could be listed, never worked. | Open → Investigating → Closed, with a required resolution |
| **Federated loop** | The global model was computed and never used; no hospital could send its update or receive the model. | Per-role models, participant submit/pull, global model used for detection when real institutions built it |
| **Smart-contract consent** | `updateConsent`/`checkConsent` existed in `PHR.sol` and were never called. | Decisions written on-chain; consent-based reads checked against the contract |
| **Blockchain in the image** | `web3` was missing from `requirements.txt`, so the container could never reach a chain. | Added |
| **Forgeable sessions** | `SECRET_KEY` defaulted to a string published in this repository, so a deployment without its own key let anyone mint an Administrator token. | A placeholder or short key is replaced by a generated one; the consent ledger has its own key; no default admin password |
| **Nurse access scope** | Any nurse could search every patient (with e-mail addresses), open any chart, record vitals and medicate anyone. | Care-team assignments by an authorized doctor or an administrator; everything else refused and recorded |
| **Contract write guard** | `PHR.sol` defined `onlyAdmin` and applied it to nothing — any address could rewrite consent. | Every write needs the backend's key; consent keeps none / granted / revoked |
| **On-chain consent check** | Ran only for consent-based reads, and only when a database column said there was a record to check. | Every non-emergency doctor read asks the chain; an on-chain withdrawal the database no longer shows is refused with an incident |
| **Re-request lifts a withdrawal** | A doctor re-asking after a withdrawal reset the row to Pending, which unblocked them before the patient decided. | The refusal stands until the patient approves |
| **Chain, IPFS replication, federation in CI** | Exercised only against fakes. | Run live in CI: anvil + deployed contract, two kubo daemons, a second hospital |
| **ZKP prover in the browser** | Proofs needed `demo/zkp_prove.py`. | "Prove consent" on the patient's page; the token stays in the browser |
| **Patient security notices** | Integrity and signature failures, altered consent and repeated refused access reached only the admin. | The patient whose record is involved is told |
| **Public `ENCRYPTION_KEY`** | Data written under the example key could not be moved to a new one. | `rotate_encryption_key.py` |
| **S3 and e-mail in CI** | Never exercised against a real service. | SeaweedFS (S3) and Mailpit in the integration run |
| **Existing nurse relationships** | Not carried into care teams. | Listed for an administrator to review and allocate |
| **Lab report progress** | The finalize dialog animated "hashing… ML-KEM… ML-DSA" on client-side timers before the request was sent. | It states what runs on the server; the result shows what the server returned |

### Still open

| # | Item | Where it stops |
|---|---|---|
| 1 | **Browser token storage** | The consent token is kept in the browser's local storage, readable by any script running on this origin. A backup file and a paste-in path exist; hardware-backed storage does not. |
| 2 | **Contracts deployed before `consentStatus`** | Detected and reported (startup log, the admin security policy, `start.sh`), but such a contract still has to be redeployed by hand before consent is verified on-chain. |

### Not implemented

| Area | Status |
|---|---|
| **A federation of independent institutions** | The protocol runs live between two backends in CI. An actual federation needs other hospitals to deploy and register; nothing here pretends they exist. |
| **Standardised post-quantum ZKP** | The lattice proof uses ML-DSA-65's parameters and assumptions, but the construction itself (Lyubashevsky's, uncompressed) is not a NIST standard and has not been independently reviewed. |

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
DOC-2026-000011   score 85.42   HIGH

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
| FedAvg: per role for baselines; for the classifier weighted by examples, each node capped at 5× the median node, an outlying update set aside (3+ nodes) | **Real** |
| Privacy: no record, event, label or identifier is sent; classifier updates are clipped, and `FEDERATION_DP_EPSILON` adds Gaussian noise (the Gaussian mechanism per round — no accounting across rounds is claimed) | **Real** |
| Signed, replay-protected exchange; peer registration; plausibility floor | **Real** |
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
and nothing A stored names a node or a person.

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

### 3. Start the IPFS node (optional)

Publishing is only attempted when `IPFS_API_URL` is set. Leave it blank and the
system runs normally — reports are still filed, just not pinned.

```bash
export IPFS_PATH=~/devtools/ipfs-repo
~/devtools/kubo/ipfs daemon --enable-gc
```

Then set `IPFS_API_URL=http://127.0.0.1:5001` in `backend/.env`.

### 4. Run Backend API Server
```bash
cd backend
python -m pip install -r requirements.txt  # Or install dependencies
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Run Frontend Web Application
```bash
cd frontend
npm install
npm run dev
```

### 6. Running the Tests

```bash
cd backend
python3 -m pytest
```

327 tests. All but the end-to-end flow need no database or running server —
they exercise pure functions so they fail for exactly one reason. Without
liboqs the post-quantum pipeline tests skip (they never pass vacuously), as do
the live-IPFS-node tests without a node and the end-to-end flow without
`RUN_E2E=1`. CI runs the full suite inside the backend image, where liboqs is
real, against a Postgres service — so nothing is skipped there except the
live IPFS node.

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

### 7. Blockchain Audit Trail

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

### The 500 generated accounts

After running the dataset generator every synthetic account shares one password:

| Role | Example | Password |
| --- | --- | --- |
| **Patient** | `PAT-2026-000035` | `Demo@1234` |
| **Doctor** | `DOC-2026-000011` | `Demo@1234` |
| **Nurse** | `NUR-2026-000006` | `Demo@1234` |
| **Lab Technician** | `LAB-2026-000008` | `Demo@1234` |
| **Administrator** | `ADM-2026-000004` | `Demo@1234` |

The full list — every user ID, name, role and password — is written to
`backend/dataset_credentials.csv` as the generator runs. That file is gitignored
and regenerated by re-running the script; see the Demonstration Dataset section
for why.

`PAT-2026-000035` is the one to open first: it carries the most data, and its
Medical Records show decrypted diagnosis text that is unreadable ciphertext in
the database.
