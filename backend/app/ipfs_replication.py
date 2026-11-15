"""IPFS replication — copies of every published CID beyond this hospital's node.

Pinning on one node makes content genuinely addressable, but it is reachable
only while that node runs and can be dialled. Replication asks other parties to
hold the same blocks, so a document outlives any single machine:

* **Replica nodes** (``IPFS_REPLICA_NODES``) — other kubo daemons: a second
  site, a team member's node, a cloud VM. This node is connected to them first,
  then each is asked to ``pin add`` the CID and fetches the blocks over bitswap.
* **Pinning services** (``IPFS_PINNING_SERVICES``) — any provider implementing
  the IPFS Pinning Service API (Pinata, Filebase, 4EVERLAND, …). The CID is
  submitted with this node's addresses as origins; the service fetches and pins
  it, and reports progress asynchronously.

Every replica is recorded in ``IpfsReplicas`` with the status the target itself
reported. "queued" is not "pinned", and a target that could not be reached is
recorded as "failed" with its error — the replication factor counts only copies
a target has confirmed.

Only ciphertext ever reaches here: the same bytes the primary node already
serves to anyone holding the CID. The AES key never leaves the database.

Replication runs in the background. A clinician filing a report must never wait
on, or be blocked by, a third party's pinning queue.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

from app.storage_service import ipfs_api_url

logger = logging.getLogger(__name__)

STATUSES = ("queued", "pinning", "pinned", "failed")
LIVE = ("queued", "pinning", "pinned")          # a request worth waiting on

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ipfs-replicate")


class ReplicationError(RuntimeError):
    """A replication target refused, failed or could not be reached."""


@dataclass(frozen=True)
class Target:
    name: str
    kind: str                     # "node" | "service"
    url: str
    token: Optional[str] = None   # pinning-service bearer token; never reported

    def public(self) -> dict:
        """What may be shown to an administrator. The token is deliberately absent."""
        return {"name": self.name, "kind": self.kind, "url": self.url}


# ─── Configuration ───────────────────────────────────────────────────────────

def _timeout() -> int:
    try:
        return max(5, int(os.getenv("IPFS_REPLICATION_TIMEOUT", "60")))
    except ValueError:
        return 60


def config_errors() -> list[str]:
    """Problems in the replication settings, reported rather than silently ignored."""
    errors = []
    raw = os.getenv("IPFS_PINNING_SERVICES", "").strip()
    if raw:
        try:
            services = json.loads(raw)
            if not isinstance(services, list):
                errors.append("IPFS_PINNING_SERVICES must be a JSON list.")
            else:
                for i, s in enumerate(services):
                    if not (isinstance(s, dict) and s.get("name") and s.get("endpoint") and s.get("token")):
                        errors.append(f"IPFS_PINNING_SERVICES entry {i} needs name, endpoint and token.")
        except json.JSONDecodeError as exc:
            errors.append(f"IPFS_PINNING_SERVICES is not valid JSON: {exc.msg}.")
    return errors


def targets() -> list[Target]:
    """Every configured replication target. Malformed entries are skipped (see config_errors)."""
    found: list[Target] = []
    for url in os.getenv("IPFS_REPLICA_NODES", "").split(","):
        url = url.strip().rstrip("/")
        if url:
            found.append(Target(name=f"node {urllib.parse.urlsplit(url).netloc or url}",
                                kind="node", url=url))
    try:
        services = json.loads(os.getenv("IPFS_PINNING_SERVICES", "").strip() or "[]")
    except json.JSONDecodeError:
        services = []
    if isinstance(services, list):
        for s in services:
            if isinstance(s, dict) and s.get("name") and s.get("endpoint") and s.get("token"):
                found.append(Target(name=str(s["name"]), kind="service",
                                    url=str(s["endpoint"]).rstrip("/"), token=str(s["token"])))
    return found


def is_configured() -> bool:
    return bool(targets())


# ─── HTTP ────────────────────────────────────────────────────────────────────

def _http(method: str, url: str, *, body: Optional[bytes] = None,
          headers: Optional[dict] = None, timeout: Optional[int] = None) -> tuple[int, bytes]:
    """One HTTP exchange. The single seam the tests replace."""
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout or _timeout()) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001 - every transport failure means the same to callers
        raise ReplicationError(f"{method} {url} failed: {exc}") from exc


def _json(status: int, payload: bytes, what: str) -> dict:
    if not 200 <= status < 300:
        raise ReplicationError(f"{what} returned HTTP {status}: {payload[:200].decode('utf-8', 'replace')}")
    try:
        # kubo streams newline-delimited JSON for some calls; the last line is the result.
        return json.loads(payload.decode("utf-8").strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise ReplicationError(f"{what} returned something that is not JSON.") from exc


# ─── The primary node ────────────────────────────────────────────────────────

def primary_addresses() -> list[str]:
    """This node's multiaddrs, given to targets so they can fetch the blocks from us."""
    api = ipfs_api_url()
    if not api:
        return []
    try:
        info = _json(*_http("POST", f"{api.rstrip('/')}/api/v0/id", timeout=10), "IPFS id")
    except ReplicationError as exc:
        logger.warning("Could not read this node's addresses: %s", exc)
        return []
    return [a for a in info.get("Addresses") or [] if isinstance(a, str)]


def primary_pins() -> Optional[set[str]]:
    """CIDs actually pinned on the primary node, or None if it cannot be asked.

    Only these can be replicated. A CID recorded while no node was running was
    computed locally and is held nowhere; asking a target to pin it would make
    that target search the network until it timed out.
    """
    api = ipfs_api_url()
    if not api:
        return None
    try:
        keys = _json(*_http("POST", f"{api.rstrip('/')}/api/v0/pin/ls?type=recursive", timeout=30),
                     "IPFS pin ls").get("Keys") or {}
    except ReplicationError as exc:
        logger.warning("Could not list pins on the primary node: %s", exc)
        return None
    return set(keys)


# ─── Replicating one CID ─────────────────────────────────────────────────────

def _to_node(target: Target, cid: str, origins: list[str]) -> dict:
    # Dial this node first. Without a connection the replica would have to find
    # a provider through the DHT, which a private or LAN node may never appear in.
    for addr in origins:
        try:
            _http("POST", f"{target.url}/api/v0/swarm/connect?arg={urllib.parse.quote(addr, safe='')}",
                  timeout=10)
        except ReplicationError:
            pass  # one unreachable address is normal; the pin below is what counts
    result = _json(*_http("POST", f"{target.url}/api/v0/pin/add?arg={urllib.parse.quote(cid)}"),
                   f"{target.name} pin add")
    if cid not in (result.get("Pins") or []):
        raise ReplicationError(f"{target.name} did not confirm the pin: {result}")
    return {"status": "pinned", "request_id": None}


def _service_headers(target: Target) -> dict:
    return {"Authorization": f"Bearer {target.token}", "Content-Type": "application/json",
            "Accept": "application/json"}


def _service_status(value: object) -> str:
    if value in STATUSES:
        return str(value)
    raise ReplicationError(f"Pinning service reported an unknown status: {value!r}")


def _to_service(target: Target, cid: str, name: str, origins: list[str]) -> dict:
    body = json.dumps({"cid": cid, "name": name[:255] or cid, "origins": origins[:20]}).encode()
    result = _json(*_http("POST", f"{target.url}/pins", body=body, headers=_service_headers(target)),
                   f"{target.name} pin request")
    return {"status": _service_status(result.get("status")), "request_id": result.get("requestid")}


def replicate(cid: str, name: str = "", only: Optional[set[str]] = None) -> list[dict]:
    """Ask every target (or the named subset) to hold ``cid``. One result per target.

    Never raises: a failing target is a result, and the others are still tried.
    """
    origins = primary_addresses()
    results = []
    for target in targets():
        if only is not None and target.name not in only:
            continue
        try:
            outcome = (_to_node(target, cid, origins) if target.kind == "node"
                       else _to_service(target, cid, name, origins))
            error = None
        except ReplicationError as exc:
            outcome, error = {"status": "failed", "request_id": None}, str(exc)
            logger.error("Replication of %s to %s failed: %s", cid, target.name, exc)
        results.append({"cid": cid, "target": target.name, "kind": target.kind,
                        "error": error, **outcome})
    return results


def refresh(target: Target, request_id: str) -> dict:
    """Ask a pinning service how a request is going. Nodes answer synchronously, so only services need this."""
    try:
        result = _json(*_http("GET", f"{target.url}/pins/{urllib.parse.quote(request_id)}",
                              headers=_service_headers(target), timeout=15),
                       f"{target.name} pin status")
        return {"status": _service_status(result.get("status")), "error": None}
    except ReplicationError as exc:
        # A status check that fails says nothing about the pin itself; keep the
        # last known state rather than downgrading it to failed.
        return {"status": None, "error": str(exc)}


# ─── Persistence ─────────────────────────────────────────────────────────────

def record(conn, results: list[dict]) -> None:
    """Upsert replication results. Each (cid, target) has one row: its latest known state."""
    with conn.cursor() as cur:
        for r in results:
            cur.execute(
                """INSERT INTO IpfsReplicas (cid, target, target_kind, status, request_id, error)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (cid, target) DO UPDATE
                     SET target_kind = EXCLUDED.target_kind,
                         status = EXCLUDED.status,
                         request_id = EXCLUDED.request_id,
                         error = EXCLUDED.error,
                         updated_at = CURRENT_TIMESTAMP""",
                (r["cid"], r["target"], r["kind"], r["status"], r["request_id"], r["error"]))
    conn.commit()


def _replicate_and_record(cid: str, name: str, only: Optional[set[str]]) -> None:
    results = replicate(cid, name, only)
    if not results:
        return
    from app.database import get_db  # imported here: the module must not need a database to load
    try:
        with get_db() as conn:
            record(conn, results)
    except Exception as exc:  # noqa: BLE001 - a background job has nobody to raise to
        logger.error("Could not record replication results for %s: %s", cid, exc)


def schedule(cid: str, name: str = "", only: Optional[set[str]] = None) -> bool:
    """Replicate in the background. Returns False when there is nothing to replicate to."""
    if not is_configured():
        return False
    _executor.submit(_replicate_and_record, cid, name, only)
    return True


# ─── Reporting ───────────────────────────────────────────────────────────────

def summarise(rows: list[dict], configured: list[Target], primary: Optional[set[str]]) -> dict:
    """Per-target counts and a replication factor that counts only confirmed copies.

    ``rows`` are IpfsReplicas rows; ``primary`` is the set pinned on this node
    (None when the node could not be asked).
    """
    per_target = {t.name: {**t.public(), "pinned": 0, "in_progress": 0, "failed": 0}
                  for t in configured}
    confirmed: dict[str, int] = {}
    for row in rows:
        entry = per_target.get(row["target"])
        if entry is None:
            continue  # a target since removed from the configuration
        if row["status"] == "pinned":
            entry["pinned"] += 1
            confirmed[row["cid"]] = confirmed.get(row["cid"], 0) + 1
        elif row["status"] in ("queued", "pinning"):
            entry["in_progress"] += 1
        else:
            entry["failed"] += 1

    published = primary if primary is not None else set(confirmed)
    copies = [1 + confirmed.get(cid, 0) for cid in published]   # 1 = the primary node
    return {
        "targets": list(per_target.values()),
        "cids_published": len(published),
        "cids_with_a_replica": sum(1 for c in copies if c > 1),
        "cids_on_every_target": sum(1 for c in copies if c == 1 + len(configured)) if configured else 0,
        "min_copies": min(copies) if copies else 0,
        "configuration_errors": config_errors(),
    }
