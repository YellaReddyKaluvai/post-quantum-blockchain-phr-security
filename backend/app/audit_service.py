import ipaddress
import logging
import json

logger = logging.getLogger(__name__)


def inet_or_none(value):
    """The client address if it is one Postgres's INET type accepts, else None.

    ``request.client.host`` is not always an IP — behind some proxies, on a unix
    socket, or under a test client it is a name — and one malformed value
    otherwise makes the whole audit or security-event insert fail.
    """
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return None


def log_admin_action(
    conn,
    admin_id,
    admin_user_id,
    action,
    target_user_id=None,
    target_public_user_id=None,
    ip_address=None,
    details=None
):
    """Insert a record into AdminAuditLogs for admin action tracking."""
    try:
        with conn.cursor() as cur:
            # A savepoint when the caller has a transaction open: Postgres aborts
            # the whole transaction on any error, so a failed audit insert that
            # was merely logged would leave the rest of the request failing.
            with conn.transaction():
                cur.execute("""
                    INSERT INTO AdminAuditLogs
                        (admin_id, admin_user_id, action, target_user_id, target_public_user_id, ip_address, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    admin_id,
                    admin_user_id,
                    action,
                    target_user_id,
                    target_public_user_id,
                    inet_or_none(ip_address),
                    json.dumps(details) if details else '{}'
                ))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log admin action '{action}': {e}")
