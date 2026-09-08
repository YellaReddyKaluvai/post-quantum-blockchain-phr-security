"""Cloud storage for encrypted medical documents (AWS S3) and IPFS addressing.

Storage model
-------------
The **database** holds the authoritative copy of an encrypted report
(``LabReports.encrypted_document``). S3 is a second, off-database copy of the
same ciphertext, used for durability and recovery.

Only ever ciphertext leaves this process. The AES key is never uploaded — it
lives solely as an ML-KEM ciphertext in the database — so an S3 object on its
own discloses nothing.

Failure behaviour
-----------------
Upload and download raise ``StorageError`` rather than returning a plausible
looking result. An earlier version swallowed every exception and still returned
the object key, which recorded pointers to objects that were never written; and
returned ``b"MOCK_ENCRYPTED_PAYLOAD_FROM_S3"`` on download failure, feeding
garbage into the decryption path. Both made a broken configuration look
healthy, which is the one thing storage code must never do.

Callers that can safely continue without the cloud copy (report finalisation
can, because the database copy is authoritative) should catch ``StorageError``
and record a NULL key — never a key that was not actually written.
"""

import hashlib
import urllib.parse
import urllib.request
import os
import json
import logging
import threading
from typing import Optional, Tuple

from app.config import get_settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_client = None
_client_built = False

# Values shipped as defaults so the app boots without AWS. Treated as "not
# configured" rather than as credentials that happen to be wrong.
_PLACEHOLDER_MARKERS = ("mock", "changeme", "your_aws", "your-aws")


class StorageError(RuntimeError):
    """Raised when cloud storage is unreachable, misconfigured, or rejects a request."""


def is_s3_configured() -> bool:
    """True when real-looking S3 credentials and a bucket are present."""
    s = get_settings()
    if not (s.AWS_ACCESS_KEY_ID and s.AWS_SECRET_ACCESS_KEY and s.AWS_S3_BUCKET):
        return False
    blob = f"{s.AWS_ACCESS_KEY_ID} {s.AWS_SECRET_ACCESS_KEY}".lower()
    return not any(marker in blob for marker in _PLACEHOLDER_MARKERS)


def _get_client():
    """Return a cached boto3 S3 client, or raise StorageError."""
    global _client, _client_built

    if _client is not None:
        return _client

    with _lock:
        if _client is not None:
            return _client
        if not is_s3_configured():
            raise StorageError(
                "AWS S3 is not configured (credentials are missing or still "
                "placeholders). Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, "
                "AWS_REGION and AWS_S3_BUCKET in backend/.env."
            )
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise StorageError("boto3 is not installed; cannot reach AWS S3.") from exc

        s = get_settings()
        try:
            _client = boto3.client(
                "s3",
                aws_access_key_id=s.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=s.AWS_SECRET_ACCESS_KEY,
                region_name=s.AWS_REGION,
                # Fail fast: a hung upload must not stall a clinical action.
                config=Config(
                    connect_timeout=5, read_timeout=15,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        except Exception as exc:
            raise StorageError(f"Could not create an S3 client: {exc}") from exc
        _client_built = True
        return _client


def reset_client() -> None:
    """Drop the cached client so the next call re-reads settings. For tests."""
    global _client, _client_built
    with _lock:
        _client = None
        _client_built = False


def generate_ipfs_cid_v0(content_bytes: bytes) -> str:
    """Compute an IPFS CIDv0 (``Qm...``) for the given bytes.

    This is pure content addressing — a Base58-encoded sha2-256 multihash,
    computed exactly as IPFS would compute it. It identifies the ciphertext and
    needs no network call, so it is always available even when S3 is not.

    This addresses the *raw bytes*. A real ``ipfs add`` wraps content in a
    UnixFS node and hashes that instead, so the two values legitimately differ —
    they address different objects, and neither is wrong.

    On its own this proves nothing about availability: computing a CID is not
    publishing. ``pin_to_ipfs`` does the publishing when a node is configured,
    and the two are kept separate so a fingerprint can still be recorded when no
    node is reachable.
    """
    sha256_hash = hashlib.sha256(content_bytes).digest()
    multihash_bytes = b"\x12\x20" + sha256_hash  # 0x12 = sha2-256, 0x20 = 32 bytes

    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    num = int.from_bytes(multihash_bytes, "big")
    encoded = ""
    while num > 0:
        num, remainder = divmod(num, 58)
        encoded = alphabet[remainder] + encoded

    for byte in multihash_bytes:
        if byte == 0:
            encoded = "1" + encoded
        else:
            break

    return encoded


def upload_to_aws_s3(
    encrypted_bytes: bytes,
    file_name: str,
    content_type: str = "application/octet-stream",
) -> Tuple[str, str]:
    """Upload ciphertext to S3. Returns ``(s3_key, s3_url)``.

    Raises ``StorageError`` if the object was not stored — the caller must
    never record a key for an object that does not exist.
    """
    settings = get_settings()
    s3_key = f"phr_records/{file_name}"
    s3_url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"

    client = _get_client()
    try:
        client.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=s3_key,
            Body=encrypted_bytes,
            ContentType=content_type,
            # Encrypted again at rest by S3. The payload is already AES-GCM
            # encrypted by us; this is defence in depth, not the primary control.
            ServerSideEncryption="AES256",
        )
    except Exception as exc:
        raise StorageError(f"S3 upload of {s3_key} failed: {exc}") from exc

    logger.info("Uploaded %d bytes to S3: %s", len(encrypted_bytes), s3_url)
    return s3_key, s3_url


def download_file_from_s3(s3_key: str) -> bytes:
    """Fetch ciphertext back from S3.

    Raises ``StorageError`` on any failure. It deliberately does not return
    substitute bytes: handing back a placeholder would corrupt the decryption
    path and disguise a real outage.
    """
    settings = get_settings()
    client = _get_client()
    try:
        response = client.get_object(Bucket=settings.AWS_S3_BUCKET, Key=s3_key)
        data = response["Body"].read()
    except Exception as exc:
        raise StorageError(f"S3 download of {s3_key} failed: {exc}") from exc

    logger.info("Downloaded %d bytes from S3: %s", len(data), s3_key)
    return data


def s3_object_exists(s3_key: str) -> bool:
    """Whether the object is actually present in the bucket."""
    settings = get_settings()
    try:
        client = _get_client()
        client.head_object(Bucket=settings.AWS_S3_BUCKET, Key=s3_key)
        return True
    except StorageError:
        return False
    except Exception:
        return False



# ─── IPFS publishing ─────────────────────────────────────────────────────────
#
# Computing a CID and pinning content are different things, and conflating them
# is how this module previously claimed more than it did. The CID above is
# arithmetic over the bytes; the functions below talk to a real node, and every
# one of them reports honestly when there is no node to talk to.

class IPFSError(RuntimeError):
    """An IPFS operation failed. Never raised for 'no node configured'."""


def ipfs_api_url() -> Optional[str]:
    """The configured node's API root, or None when IPFS is not in use."""
    return os.getenv("IPFS_API_URL") or None


def is_ipfs_configured() -> bool:
    return bool(ipfs_api_url())


def pin_to_ipfs(encrypted_bytes: bytes, file_name: str) -> Optional[str]:
    """Publish ciphertext to the configured IPFS node and pin it.

    Returns the CID the node itself computed, or None when no node is
    configured — an absent node is a deployment choice, not an error, and must
    not stop a clinician filing a report.

    Only ciphertext is ever passed here. IPFS content is addressed by hash and
    served to anyone who asks for that hash, so putting a plaintext record on it
    would be a disclosure, not a storage decision.
    """
    api = ipfs_api_url()
    if not api:
        return None

    boundary = "----QuantumCareIPFS" + hashlib.sha256(file_name.encode()).hexdigest()[:16]
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        encrypted_bytes,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    request = urllib.request.Request(
        f"{api.rstrip('/')}/api/v0/add?cid-version=0&pin=true",
        data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8").strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001 - any transport failure is the same to callers
        raise IPFSError(f"IPFS add failed for {file_name}: {exc}") from exc

    cid = payload.get("Hash")
    if not cid:
        raise IPFSError(f"IPFS returned no CID for {file_name}: {payload}")
    logger.info("Pinned %d bytes to IPFS as %s", len(encrypted_bytes), cid)
    return cid


def fetch_from_ipfs(cid: str) -> bytes:
    """Retrieve pinned content by CID. Raises if it cannot be had."""
    api = ipfs_api_url()
    if not api:
        raise IPFSError("No IPFS node is configured.")
    request = urllib.request.Request(
        f"{api.rstrip('/')}/api/v0/cat?arg={urllib.parse.quote(cid)}", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except Exception as exc:  # noqa: BLE001
        raise IPFSError(f"IPFS cat failed for {cid}: {exc}") from exc


def ipfs_status() -> dict:
    """Live node health, for the admin dashboard.

    Reports 'not configured' distinctly from 'configured but unreachable',
    because those call for different actions from whoever is on call.
    """
    api = ipfs_api_url()
    status = {"configured": bool(api), "api_url": api, "connected": False,
              "peer_id": None, "pinned_objects": None, "error": None,
              "scope": None}
    if not api:
        status["error"] = "No IPFS node configured (set IPFS_API_URL to enable publishing)."
        return status

    try:
        with urllib.request.urlopen(
                urllib.request.Request(f"{api.rstrip('/')}/api/v0/id", method="POST"),
                timeout=10) as response:
            info = json.loads(response.read())
        status["connected"] = True
        status["peer_id"] = info.get("ID")
    except Exception as exc:  # noqa: BLE001
        status["error"] = f"IPFS node unreachable: {exc}"
        return status

    try:
        with urllib.request.urlopen(
                urllib.request.Request(f"{api.rstrip('/')}/api/v0/pin/ls?type=recursive",
                                       method="POST"), timeout=15) as response:
            keys = json.loads(response.read()).get("Keys", {})
        status["pinned_objects"] = len(keys)
    except Exception:  # noqa: BLE001 - a pin count is nice to have, not essential
        pass

    # Said plainly so nobody mistakes a local node for global availability.
    status["scope"] = (
        "Content is pinned on this node. It is genuine IPFS — real CIDs, real "
        "block storage, real retrieval — but it is reachable only while this "
        "node runs and is dialable. That is not the same as being replicated "
        "across the public network."
    )
    return status


def store_encrypted_document(
    encrypted_bytes: bytes, document_name: str
) -> Tuple[str, Optional[str]]:
    """Content-address the ciphertext and store it in S3.

    Returns ``(content_cid, s3_key)``. ``s3_key`` is **None** when the upload
    did not happen, so a missing cloud copy is recorded truthfully instead of
    as a dead pointer. The CID is always returned: it is derived from the
    content itself and needs no network.

    Formerly ``process_and_pin_ipfs``, which was a misnomer — it never pinned
    anything to IPFS and returned a public gateway URL that could not resolve.
    """
    content_cid = generate_ipfs_cid_v0(encrypted_bytes)

    file_name = f"{content_cid}_{document_name.replace(' ', '_')}.enc"

    # Publish to IPFS when a node is configured. A failure here is logged and
    # survived: the database copy is authoritative and a clinician must not be
    # blocked from filing a report because a storage node is down.
    try:
        node_cid = pin_to_ipfs(encrypted_bytes, file_name)
        if node_cid:
            # The node's CID differs from the computed one, and that is correct
            # rather than a fault. generate_ipfs_cid_v0 hashes the raw bytes;
            # `ipfs add` wraps them in a UnixFS node first and hashes that. Both
            # are valid CIDv0 values addressing different objects. Once content
            # is genuinely published the node's CID is the one that resolves, so
            # it is the one recorded.
            content_cid = node_cid
    except IPFSError as exc:
        logger.error("IPFS publish failed for %s: %s", document_name, exc)

    try:
        s3_key, _ = upload_to_aws_s3(encrypted_bytes, file_name)
    except StorageError as exc:
        # The database copy is authoritative, so the clinical action proceeds;
        # but the missing cloud copy is logged loudly and stored as NULL.
        logger.error("Cloud copy NOT stored for %s: %s", document_name, exc)
        return content_cid, None

    logger.info("content CID %s -> S3 key %s", content_cid, s3_key)
    return content_cid, s3_key


def storage_status() -> dict:
    """Live health of the cloud storage backend, for the admin dashboard."""
    settings = get_settings()
    status: dict = {
        "configured": is_s3_configured(),
        "bucket": settings.AWS_S3_BUCKET or None,
        "region": settings.AWS_REGION or None,
        "connected": False,
        "error": None,
    }
    if not status["configured"]:
        status["error"] = "AWS credentials are missing or still placeholders."
        return status

    try:
        client = _get_client()
        client.head_bucket(Bucket=settings.AWS_S3_BUCKET)
        status["connected"] = True
    except Exception as exc:
        status["error"] = str(exc)

    return status
