"""Reconcile lab-report cloud copies with what is actually in S3.

Why this exists
---------------
An earlier version of ``storage_service.upload_to_aws_s3`` caught every
exception and returned the object key regardless, so reports were saved with an
``s3_key`` even when the upload never happened. Those rows point at objects that
do not exist.

This script checks each report's recorded key against the bucket and repairs
the mismatch, using the authoritative ciphertext held in the database:

  * key recorded, object present   -> OK, untouched
  * key recorded, object missing   -> re-upload from the database copy
  * no key, database copy present  -> upload and record the key
  * no key, no database copy       -> reported; nothing can be done here

Usage:
    python3 backfill_s3_copies.py           # report only (no writes)
    python3 backfill_s3_copies.py --apply   # perform the repairs
"""

import sys

from psycopg.rows import dict_row

from app.database import get_db
from app.storage_service import (
    StorageError,
    is_s3_configured,
    s3_object_exists,
    storage_status,
    upload_to_aws_s3,
    generate_ipfs_cid_v0,
)


def main() -> int:
    apply_changes = "--apply" in sys.argv

    if not is_s3_configured():
        print("ERROR: AWS S3 is not configured (credentials missing or placeholders).")
        print("Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in backend/.env first.")
        return 1

    status = storage_status()
    if not status["connected"]:
        print(f"ERROR: cannot reach bucket '{status['bucket']}': {status['error']}")
        return 1
    print(f"Bucket {status['bucket']} ({status['region']}) reachable.\n")

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, report_id_public, panel_code, s3_key, encrypted_document
                FROM LabReports
                ORDER BY created_at
            """)
            reports = cur.fetchall()

    ok, to_upload, unfixable = [], [], []
    for r in reports:
        has_body = bool(r["encrypted_document"])
        if r["s3_key"] and s3_object_exists(r["s3_key"]):
            ok.append(r)
        elif has_body:
            to_upload.append(r)
        else:
            unfixable.append(r)

    print(f"{len(reports)} report(s) examined:")
    print(f"  {len(ok):>3} already have a valid cloud copy")
    print(f"  {len(to_upload):>3} need uploading (missing or dangling key)")
    print(f"  {len(unfixable):>3} cannot be repaired (no database copy either)")

    for r in unfixable:
        print(f"       ! {r['report_id_public'] or r['id']} has neither a cloud nor a database copy")

    if not to_upload:
        print("\nNothing to repair.")
        return 0

    if not apply_changes:
        print("\nWould re-upload:")
        for r in to_upload:
            state = "dangling key" if r["s3_key"] else "no key"
            print(f"    {r['report_id_public'] or r['id']}  ({state})")
        print("\nDry run. Re-run with --apply to perform the uploads.")
        return 0

    print("\nUploading...")
    repaired = failed = 0
    with get_db() as conn:
        for r in to_upload:
            body = r["encrypted_document"].encode("utf-8")
            cid = generate_ipfs_cid_v0(body)
            name = f"{cid}_{(r['report_id_public'] or str(r['id']))}_{r['panel_code'] or 'REPORT'}.enc"
            try:
                s3_key, _ = upload_to_aws_s3(body, name)
            except StorageError as exc:
                print(f"    FAILED {r['report_id_public'] or r['id']}: {exc}")
                failed += 1
                continue

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE LabReports SET s3_key = %s, ipfs_cid = %s WHERE id = %s",
                    (s3_key, cid, r["id"]),
                )
                conn.commit()
            print(f"    repaired {r['report_id_public'] or r['id']} -> {s3_key}")
            repaired += 1

    print(f"\nDone. {repaired} repaired, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
