"""Keep administrator metric cards aligned with the API response fields."""
import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def test_admin_dashboard_cards_use_api_response_fields():
    tree = ast.parse((ROOT / 'backend/app/schemas.py').read_text())
    schema = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'DashboardStats')
    fields = {node.target.id for node in schema.body if isinstance(node, ast.AnnAssign)}
    page = (ROOT / 'frontend/src/app/dashboard/admin/page.tsx').read_text()
    cards = re.findall(r'\{ key: "([a-z_]+)", label:', page)
    assert cards, 'Expected administrator dashboard metric cards'
    assert set(cards) <= fields, f'Cards absent from API response: {set(cards) - fields}'
    assert {'total_patients', 'total_doctors', 'total_nurses', 'total_lab_technicians', 'pending_requests', 'approved_users'} <= set(cards)
