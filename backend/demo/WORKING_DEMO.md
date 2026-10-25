# Working demonstration and reproducible evidence

This package demonstrates the deployed software through its public frontend
URL. It complements the existing cryptography scripts and disposable-database
integration tests. It does not require a database password or direct SQL access.

Watch the captioned video on the [public homepage](https://post-quantum-blockchain-phr-securit.vercel.app/#project-demo)
without signing in. The video, poster and transcript are versioned under
`frontend/public/demo/` and served with the frontend deployment.

## Submission contents

| Requirement | Deliverable |
|---|---|
| Working deployed model | https://post-quantum-blockchain-phr-securit.vercel.app |
| Short explanatory video | `quantumcare-captioned-demo.mp4` in the accompanying submission bundle |
| Embedded captions | Burned into the MP4; also supplied separately as SRT and transcript |
| Run instructions | This guide |
| Script regenerating metrics and outputs | `run_hosted_demo.py` |
| Measured results and sample output | `results.json`, `summary.md`, `sample-report.pdf` |
| Source/configuration versions | Revision fields, runner hash, configuration and algorithm names in `results.json` |

The video uses captures of the actual deployed application. Pauses are edited
for readable captions. It is a caption-led walkthrough, without spoken narration.
All people and clinical observations used by this demonstration are fictional.

## Reproduce the run

Requires Python 3.9+ (standard library only), network access to the app and an
existing administrator account. Use a dedicated demonstration deployment when
possible. Each execution creates four new fictional accounts and associated
records, does not delete existing data, and does not reset the database.

From the repository root:

```sh
python3 backend/demo/run_hosted_demo.py \
  --url https://post-quantum-blockchain-phr-securit.vercel.app \
  --admin-id ADM-2026-000001 \
  --output demo-runs/current \
  --private-output ../quantumcare-demo-private \
  --backend-revision REPLACE_WITH_RUNNING_BACKEND_COMMIT \
  --frontend-revision REPLACE_WITH_RUNNING_FRONTEND_COMMIT \
  --samples 5 \
  --create-demo-data
```

The administrator password is requested with hidden input, not a command-line
argument. Obtain it from your secret store. Never publish it. Determine the
running revisions from the hosting dashboards: the frontend and backend may
be on different commits. These revision arguments are operator-supplied
metadata, not an automatic attestation from the API.

The private directory contains generated fictional account credentials with
restricted file permissions. Keep it separate from the submission and Git.
The public output directory contains no passwords, session tokens or keys.
Approval email delivery is not assumed; assigned User IDs come from the API.

## Demonstrated path

1. Public frontend proxy health and anonymous administrator-access refusal.
2. Registration and administrator approval for Patient, Doctor, Lab Technician
   and Nurse; role-specific login and secure session cookies.
3. A doctor is refused before consent, requests access, and is allowed only
   after the patient approves.
4. A nurse is refused before assignment. The doctor creates a time-bounded
   care-team assignment, and nursing observations become visible to the patient.
5. A fictional diagnosis is added and visible in the patient's medical records.
6. A CBC order moves from doctor to laboratory; the technician accepts and
   finalizes a report.
7. The API reports ML-KEM-768 and ML-DSA-65. The patient verifies the digest and
   signature and downloads a decrypted PDF; a report-ready notification exists.
8. A patient cannot access administrator APIs. Consent withdrawal blocks the
   doctor and the delegated nurse; the patient restores access for the video.
9. Administrator audit and security endpoints respond. Every role logs out,
   and the API rejects the ended session.

The script fails on the first unexpected status or failed assertion and writes
partial evidence. It does not retry mutations, fabricate results, modify real
patient records, corrupt database values or create emergency overrides.

## Metrics and interpretation

Five sequential client requests per route measure health, patient dashboard
and report verification. The summary gives median and nearest-rank p95, with
all raw request durations in JSON. The first health request is also recorded
and may include a free-tier cold start. There is one client and no load test;
latency includes network, proxy, API and database work. Do not describe these
numbers as server-only latency, throughput or clinical performance.

The sample PDF hash and byte count allow the submitted file to be matched to
its measured run. The algorithm identifiers are the cryptographic parameter
sets, not an AI classifier version. The run does not evaluate a trained
classifier or independent federated institutions. Source revisions and the
runner hash identify the code/configuration used for this demonstration.

## Video walkthrough and coverage

| Area | What to show or explain |
|---|---|
| Entry and registration | One public URL, four registration roles, approval requirement |
| Patient | Dashboard, completed report, Verify result, vitals, consent and notifications |
| Doctor | Authorized patient workspace, clinical entries and laboratory requests |
| Nurse | Assigned care team and observations; no unrestricted patient browsing |
| Laboratory | Ordered tests and completed, signed report |
| Administrator | Users/approvals, cryptographic status, audit and security monitoring |
| Secondary workflows | Menus also expose appointments, prescriptions, documents and imaging; this run does not exercise every secondary workflow |
| AI/federation | Explain the interface and deployment-dependent models; do not claim a multi-hospital training evaluation |
| Infrastructure | Disclose missing blockchain, IPFS, S3 and SMTP integrations |
| Results | Show actual check count, measured timings and reproducibility command |

No real blockchain proof is claimed when `blockchain_verified` is null or false.
A CID does not demonstrate a pinned IPFS copy. The baseline stores the
report's authoritative encrypted copy in PostgreSQL. Successful PDF release
is evidence of decryption/verification, not a direct audit of at-rest bytes.
The independent tamper tests remain in `backend/tests/test_e2e_flow.py` and
must run only with a disposable database.

## Refreshing the video

Re-run the script, sign into its generated fictional accounts, and capture
actual screens without passwords, tokens or private settings. Use the new
results for captions rather than copying old timing claims. The submission
also includes its caption transcript and video-building script. The build
script consumes a screen-capture scene manifest and embeds the captions;
recording fresh screens requires authorized browser interaction.

A video need not be stored in Git to reproduce the metrics. Keep the video
and sample output bundle with the submission; keep this runner and guide in
version history. Free hosting can expire or sleep; see [DEPLOY.md](../../DEPLOY.md).

### Build the captioned MP4 from recorded captures

With Python, Pillow and an FFmpeg executable installed (or `imageio-ffmpeg`):

```sh
python3 -m pip install Pillow imageio-ffmpeg
python3 backend/demo/build_captioned_video.py \
  --manifest /path/to/video-source/scenes.json \
  --results /path/to/results.json \
  --output /path/to/rendered-demo \
  --font /path/to/a-readable-font.ttf
```

The supplied `video-source/scenes.json` references the accompanying captured
JPEGs. Use a new output directory. The renderer preserves the captured screen
layout, adds permanent captions and creates an SRT, transcript and metadata.
A scene can contain a still capture or timestamped navigation frames. The
final metrics cards read the actual JSON results rather than invented numbers.
The submitted MP4 has no audio; all explanation is visible in its captions.

The recorded run used backend `41abb2c` and frontend `515f499`. During browser
review, an administrator-counter field-name mismatch was corrected in
`85f13f2`; that corrected aggregate screen was captured after deployment.
The API workflow and measured timings precede this frontend-only correction.
