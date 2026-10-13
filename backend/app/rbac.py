from dataclasses import dataclass
from typing import Iterable


ROLE_DEFINITIONS = {
    "Patient": {
        "dashboard": ["patient"],
        "permissions": {
            "records:read:own",
            "records:upload:own",
            "consent:grant",
            "consent:revoke",
            "session:logout",
        },
    },
    "Doctor": {
        "dashboard": ["doctor"],
        "permissions": {
            "records:read:approved",
            "records:upload:diagnosis",
            "consent:request",
            "emergency:request",
            "session:logout",
        },
    },
    "Nurse": {
        "dashboard": ["nurse"],
        "permissions": {
            "patients:view:assigned",
            "records:upload:vitals",
            "session:logout",
        },
    },
    "Lab Technician": {
        "dashboard": ["lab-technician"],
        "permissions": {
            "records:upload:lab",
            "records:read:assigned",
            "session:logout",
        },
    },
    "Administrator": {
        "dashboard": ["admin"],
        "permissions": {
            "users:manage",
            "roles:assign",
            "permissions:manage",
            "audit:read",
            "system:configure",
            "keys:rotate",
            "registrations:manage",
            "security:view",
            "users:disable",
            "users:enable",
            "session:logout",
        },
    },
}

FUTURE_ROLES = []


def normalize_role(role: str) -> str:
    return role.strip().title()


def get_permissions_for_role(role: str) -> set[str]:
    definition = ROLE_DEFINITIONS.get(normalize_role(role))
    return set(definition["permissions"]) if definition else set()


def is_role_allowed_for_dashboard(role: str, dashboard_role: str) -> bool:
    definition = ROLE_DEFINITIONS.get(normalize_role(role))
    return bool(definition and dashboard_role in definition["dashboard"])


def has_permission(role: str, permission: str) -> bool:
    return permission in get_permissions_for_role(role)
