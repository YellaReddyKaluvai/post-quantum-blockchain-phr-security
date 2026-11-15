# Completed workflows and rollout

## Implemented

- Doctor documents: patient selection, supported document types, text authoring, authenticated viewing, visible API errors and server refresh after creation. The subsequent completion below adds PDF/DOCX attachments; imaging retains its own uploader.
- Missing database ciphertext can recover from S3 for medical documents, and S3/IPFS for imaging. Recovered bytes still pass GCM, digest and signature checks.
- Account security at `/dashboard/account` for every role: password change, TOTP enrollment/confirmation/disable, single-use recovery codes, PQC key rotation and explicit historical-key revocation.
- Forgotten passwords: 256-bit random tokens, hashed storage, 15-minute expiry, one-time consumption, trusted frontend URLs, generic replies and database throttles. SMTP errors never return/log a reset token. Reset keeps MFA enabled and revokes all sessions.
- Login: atomic PostgreSQL throttles shared by workers; an MFA-enabled user must provide a fresh six-digit code or unused recovery code alongside the password. A successful password alone does not start a session. Setup invalidates other sessions; recovery codes are shown once and stored hashed.
- Appointments: hospital-local future-time validation, 30-minute overlap checks for both doctor and patient, serialized reservations, suggested available slots, patient cancellation/rescheduling and backend status-transition validation. Rescheduling requires fresh doctor confirmation. Default hours are 09:00–17:00 every day; doctor schedules and leave now override them and API bookings enforce availability.
- New column writes use a versioned AES-256-GCM envelope. Recognized ciphertext that fails decryption is refused. Legacy CBC/plaintext is readable for migration, and cannot retrospectively acquire integrity until migrated.
- PQC versions: records bind to recipient/signing versions. Rotation preserves the historical KEM private keys and signature public keys. Explicit revocation prevents release of affected records; it cannot recall copies already downloaded or undo exposure of a compromised key. Issuance and rotation share a transaction lock. Historical private keys are included in master-key rotation and column migration.
- `REQUIRE_CONSENT_PROOF=true` requires a proof of the current consent commitment verified within five minutes for **consent-based** doctor access. Treating-relationship and emergency access retain their existing policies. This is not a claim that every read requires ZKP. The patient chart shows the proof panel even when record loading is refused. Challenges and one-time token collection lock rows against concurrent replay.
- Legacy `crypto_utils` no longer substitutes fake keys or base64 for real encryption.

## Safe rollout

1. Back up PostgreSQL and securely retain the existing `ENCRYPTION_KEY`. Stop application writers during schema and column migration. Test on a copy first.
2. Apply `backend/db/init.sql`. It is idempotent; startup also runs it and now refuses to start on migration failure. Existing records are assigned key version 1 and current user keys are snapshotted before rotation is offered. Previously lost/replaced private keys cannot be reconstructed.
3. In the backend environment, run `python upgrade_column_encryption.py` for a dry run, then `python upgrade_column_encryption.py --apply`. It verifies every conversion before committing. It does **not** change `ENCRYPTION_KEY`. After a successful migration, set `REQUIRE_AUTHENTICATED_COLUMNS=true` to reject plaintext/CBC downgrades on normal reads; leave it off only during the migration window.
4. Configure `PUBLIC_APP_URL` to the real HTTPS frontend origin, SMTP settings, secure cookies and trusted reverse-proxy addresses. Recovery email intentionally does not work without a real SMTP configuration.
5. Set `HOSPITAL_TIMEZONE` and optional `APPOINTMENT_START_HOUR`/`APPOINTMENT_END_HOUR`. Times refer to that hospital zone. Slot suggestions do not reserve a time until the booking transaction succeeds.
6. Roll out frontend/backend together. Users can enroll MFA from Account security; require them to save recovery codes outside the browser. Email recovery alone cannot bypass MFA. Lost authenticator **and** lost recovery codes use the dual-administrator identity recovery flow described below.
7. Optionally enable `REQUIRE_CONSENT_PROOF` after doctors have collected their consent tokens. Existing relationship and emergency policies remain explicit.

The migration is forward compatible with old ciphertext. Rolling back to old application code after new GCM writes or PQC rotations is unsafe: old code cannot understand the new format or historical key versions. Roll back application and database together from the backup, or fix forward.

## External integrations

No paid services or production credentials are provisioned by these source changes. The default Render blueprint deliberately keeps blockchain off and IPFS unset.

- Blockchain: configure a reachable RPC, appropriate network key, deployed `PHR.sol` address and chain ID. Use Admin → Security to check connectivity, then late-anchor backlog entries. A local-simulated anchor is not blockchain proof.
- IPFS: configure `IPFS_API_URL`; add a second node or pinning service via the existing replication settings. Run replication sync and verify confirmed pins, not queued requests.
- S3: configure the existing AWS/S3-compatible settings, check Admin → Security, and backfill missing copies using `backfill_s3_copies.py`.
- SMTP: configure a working mailbox/server and `PUBLIC_APP_URL`; validate password reset delivery using a test account.
- Federation: use the existing hub/peer admin screens and [federation deployment guide](10_Federation_Deployment.md). Real institutions must supply endpoints/shared secrets; simulated peers are not a live deployment.

The existing CI provisions PostgreSQL, liboqs, IPFS, S3-compatible storage, SMTP and a local chain. `tests/test_completed_workflows.py` adds algorithm vectors, corruption/recovery tests, and opt-in real-database tests for MFA, password reset, appointments and historical PQC records. Run from `backend`: `python -m pytest`; use `RUN_E2E=1` only with a disposable database.

References for implementation: [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238.html) and [OWASP password recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).


## Validation in the implementation workspace

Frontend TypeScript, ESLint (two existing imaging warnings), a production Webpack build,
browser ZKP vectors and consent-vault checks pass. The backend suite passes with real
liboqs; live-service tests are skipped without their opt-in infrastructure. PostgreSQL
single-user validation checks the schema twice and verifies version stamping and historical
key retention. The bundled PostgreSQL lacks uuid-ossp, so that local schema check substitutes
its UUID generator with PostgreSQL's equivalent built-in gen_random_uuid wrapper; repository
SQL retains uuid-ossp for the existing deployment.

Full HTTP/database integration tests have been added but must still run in CI: this workspace
cannot open database sockets. External integrations and production behavior have not been
validated here. No live patient data or production configuration was changed.

## Remaining workflow completion (14 November 2026)

The subsequent completion branch adds:

- **Configuration:** Compose forwards SMTP, trusted frontend URL, schedule defaults, verification, refresh lifetime and strict-proof/encryption switches. Render includes those policy settings and explicit secure cookies. Set `PUBLIC_APP_URL` to the real HTTPS frontend and provision a stable `CONSENT_LEDGER_KEY`; never rotate that ledger key casually.
- **Sessions:** login issues a hashed, single-use refresh token in an HttpOnly cookie. Refresh rotates the token while preserving an absolute family lifetime (`REFRESH_TOKEN_DAYS`). Reuse revokes the session. Password/MFA changes and disable/logout revoke the associated database sessions, which also blocks refresh. The frontend retries an expired request once and serializes refreshes across tabs where Web Locks is available.
- **Email:** `REQUIRE_EMAIL_VERIFICATION=true` requires ownership proof for new registrations before login. Existing users are not silently locked out. `/verify-email` requests a fresh link and consumes a one-hour token. Administrator approval remains separately necessary. This does not claim verification of previously approved users.
- **MFA:** local QR generation (no external QR provider), remaining-code count and authenticated regeneration invalidate old codes. Admin → Account Recovery requires two distinct MFA-enabled administrators, independent identity verification and an auditable case reference. The requester/account owner cannot approve their own request. A 15-minute token goes only to the registered email; consumption changes the password, removes lost factors and revokes all sessions. The person must enroll a new authenticator after login. Identity evidence remains in the institution's system, not uploaded to this app. Deployments with one administrator must provision a second trusted administrator through the existing private administration process.
- **Appointments:** doctors edit weekly working intervals, appointment duration and dated leave in their appointments page. Both initial booking and rescheduling enforce the schedule and collision checks. Durations are stored on bookings. Schedule changes that invalidate existing future bookings are refused; resolve those appointments first. One interval per weekday is supported, in the configured hospital timezone.
- **Attachments:** the doctor document form accepts PDF or DOCX up to 10 MiB. Filename, MIME and base64 bytes are signed/encrypted together in the existing document pipeline. Authorized patients/doctors download the original file. Signature/container checks reject mismatches, macro-containing DOCX, traversal and oversized ZIP metadata. Files are not executed, extracted or rendered as HTML. This is not antivirus certification; use a suitable malware scanner for deployments accepting untrusted clinical documents.
- **Historical PQC records:** Account Security → Migrate records re-encrypts up to 20 records per action under the current recipient KEM key. Repeat until `remaining=0`, then consider revocation. The server verifies GCM and the existing plaintext digest before updating; signatures, signer versions and plaintext anchors stay unchanged. The old recipient key must still be available and unrevoked. External ciphertext copies already retained by others cannot be erased. A cloud write followed by database rollback can leave an orphan encrypted object. Revoke a historical signer version only if withholding records signed by it is intended.
- **Backup/restore:** `python database_backup.py backup /secure/path/backup.dump` creates a mode-0600 archive using `DATABASE_URL`; `verify` checks its table of contents. Set `RESTORE_DATABASE_URL` to a separate empty disposable database, then use `restore ... --confirm-target EXACT_DATABASE_NAME`. Restore uses a single transaction and never drops existing objects. `pg_dump`/`pg_restore` must be installed. Encrypt archives in your managed backup system and escrow the matching application keys separately; test decryption after restoring.

### Verification and release gates

Apply the idempotent schema before deploying both services. Run `python -m pytest` and the frontend lint/build. CI also runs `frontend/e2e/completion-smoke.mjs` against actual services for MFA enrollment, recovery-code replacement, key rotation, invalid reset handling and doctor availability; API integration tests exercise refresh replay, email verification and booking enforcement.

Production SMTP, remote chain, public IPFS pinning, object storage, backup retention and three physical laptops need actual operator-provided resources. The repository's three-node results remain synthetic containers, not measured physical-laptop or hospital results. Do not replace those evidence requirements with simulated success. To run a physical experiment use `scripts/federation_lab.py` and the deployment guide, then archive the resulting measurements.

### Local validation of the completion branch

The production build generates 59 pages. TypeScript and ESLint pass (existing imaging warnings remain). Real PostgreSQL/liboqs tests cover refresh replay, verification links, doctor schedules, attachment round trips, recipient-key migration and two-administrator MFA recovery. A real Chromium session exercises the account and schedule screens. A disposable `pg_dump`/`pg_restore` drill validates the archive and restored rows. For local PostgreSQL only, the unavailable `uuid-ossp` extension is replaced in a temporary test copy by a wrapper around `gen_random_uuid`; repository schema and CI still use `uuid-ossp`.

These local checks do not validate a production database, real mailbox, external storage account or physical laptop network.

Final local regression: **495 passed, 10 skipped** with real PostgreSQL and liboqs.
The skipped cases require external chain/IPFS/mail/federation services not started for
this local run. Chromium completion smoke passed, including automatic refresh after
an invalid/expired access cookie. Backup restoration also passed a decrypted-column
check using the matching application key. Production infrastructure remains unverified.
