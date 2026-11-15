# Cloud storage and a 1,000-user test

PostgreSQL is the application database. S3 stores a second copy of encrypted
document bytes; it does not contain a copy of every database row. IPFS is an
optional additional store for ciphertext. If all database rows must be kept in
cloud storage for disaster recovery, take an encrypted, consistent PostgreSQL
backup and restore it to a separate database during a recovery drill. Uploading
individual user rows to S3 would create a second database without transaction
consistency or an access-control model.

## Before adding synthetic accounts to the hosted database

The existing `generate_dataset.py` adds users and clinical records. It does not
simulate concurrent traffic. Its `--target-total-users` mode adds exactly the
difference between the current count and the requested total. It never resets
existing records in that mode. Do not use `--reset` on the hosted database.

1. Confirm the deployed API and schema are at the current `main` commit. The
   S3 bucket screenshot alone does not establish that the Render API uses it.
2. Take a PostgreSQL backup, preserve the matching `ENCRYPTION_KEY` and
   `CONSENT_LEDGER_KEY`, and verify a restore on a separate database. The
   backup contains confidential account and clinical data; encrypt and restrict
   it. Confirm that the free database has enough space and will not expire
   during the review.
3. Set `DATABASE_URL` to the intended database in the execution environment.
   Run `python generate_dataset.py --target-total-users 1000 --plan` from
   `backend/`. It only reads `Users` and prints the current count and addition.
4. Set a private, random `DEMO_DATASET_PASSWORD` of at least 16 characters.
   If the plan reports `N` existing users, run
   `python generate_dataset.py --target-total-users 1000 --expected-existing-users N`.
   The count guard refuses to run if another operation changed the database
   between planning and execution. Generated credentials are not written by
   default in this mode; supply `--credentials-output` with a private path only
   if a test account must be used for sign-in. Never commit that file.
5. Confirm `SELECT count(*) FROM "Users"` is exactly 1,000. In Admin →
   Infrastructure Health, confirm S3 is connected and check lab reports with
   cloud copies. A user count of 1,000 does **not** imply 1,000 S3 objects:
   only documents created for those users are uploaded.
6. If S3 was configured after reports were created, dry-run
   `python backfill_s3_copies.py`. Review the reported missing objects before
   `--apply`. The repair updates only S3 keys; it preserves any IPFS CID.

The generator uses real post-quantum keys, encryption and signatures, so it
needs the backend Docker image with liboqs. It appends a large synthetic
dataset and should not be run repeatedly or during the live presentation.
`DEMO_DATASET_PASSWORD` is deliberately never printed in target-total mode.

## Capacity test

One thousand rows in `Users` tests data volume and page/query behavior. It
does not prove support for 1,000 simultaneous users. Measure a separate,
bounded request test against authenticated reads, registration and report
retrieval: start with a few concurrent clients, then increase gradually while
recording p50/p95 latency, error rate, CPU, memory and PostgreSQL connections.
Stop at sustained errors or resource saturation. Do not claim a throughput or
concurrency number without that measurement. Use fictional accounts only.
