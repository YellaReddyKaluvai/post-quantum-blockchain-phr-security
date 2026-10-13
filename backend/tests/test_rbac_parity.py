"""Guard against the backend RBAC matrix and the frontend IAM map drifting apart.

The backend is the authoritative enforcer. The frontend keeps a mirrored copy in
``frontend/src/lib/iam.ts`` so it can restore a session from a cookie without an
API round-trip. If the two disagree, the UI ends up gating on permission strings
the server has never heard of, which fails open or closed unpredictably.

This test parses the TypeScript literal directly rather than importing it, so it
stays honest without needing a JS runtime.
"""

import re
from pathlib import Path

import pytest

from app.rbac import ROLE_DEFINITIONS

IAM_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "iam.ts"


def _parse_frontend_permissions() -> dict[str, set[str]]:
    source = IAM_TS.read_text()

    match = re.search(
        r"export const rolePermissions:[^=]*=\s*\{(.*?)\n\};",
        source,
        re.DOTALL,
    )
    assert match, "Could not locate rolePermissions in iam.ts"
    block = match.group(1)

    # Strip comments so they can't be mistaken for entries.
    block = re.sub(r"//.*", "", block)

    parsed: dict[str, set[str]] = {}
    # Matches both  Patient: [...]  and  "Lab Technician": [...]
    for m in re.finditer(r'(?:"(?P<q>[^"]+)"|(?P<b>\w+))\s*:\s*\[(?P<items>.*?)\]', block, re.DOTALL):
        role = m.group("q") or m.group("b")
        items = set(re.findall(r'"([^"]+)"', m.group("items")))
        parsed[role] = items

    return parsed


def test_iam_ts_exists():
    assert IAM_TS.exists(), f"Expected frontend IAM map at {IAM_TS}"


def test_roles_match():
    frontend = _parse_frontend_permissions()
    assert set(frontend) == set(ROLE_DEFINITIONS), (
        "Role sets differ between backend rbac.py and frontend iam.ts"
    )


@pytest.mark.parametrize("role", sorted(ROLE_DEFINITIONS))
def test_permissions_match_for_role(role):
    frontend = _parse_frontend_permissions()
    expected = set(ROLE_DEFINITIONS[role]["permissions"])
    actual = frontend.get(role, set())

    missing = expected - actual
    extra = actual - expected
    assert not missing and not extra, (
        f"Permission drift for {role!r}:\n"
        f"  missing from frontend: {sorted(missing)}\n"
        f"  not in backend:        {sorted(extra)}"
    )
