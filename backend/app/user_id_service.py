from datetime import datetime
import psycopg
from app.database import get_db

ROLE_PREFIXES = {
    "Patient": "PAT",
    "Doctor": "DOC",
    "Nurse": "NUR",
    "Lab Technician": "LAB",
    "Administrator": "ADM"
}

def _next_sequence(prefix: str, year: int) -> int:
    """Atomically claim the next number in a (prefix, year) counter."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO UserIdSequences (role_prefix, year, last_sequence)
                VALUES (%s, %s, 1)
                ON CONFLICT (role_prefix, year)
                DO UPDATE SET last_sequence = UserIdSequences.last_sequence + 1
                RETURNING last_sequence;
            """, (prefix, year))
            result = cur.fetchone()
            if not result:
                raise Exception("Failed to generate sequence number")
            conn.commit()
            return result[0]


def generate_report_number() -> tuple[str, str]:
    """Allocate a laboratory report number and its accession number.

    Returns ``(report_no, accession_no)`` — e.g. ``('LR-2026-000117',
    'ACC-2026-000117')``. Both share a sequence so a report and the specimen it
    came from can be cross-referenced by eye on a printed page, which is how
    laboratory staff actually match them.
    """
    year = datetime.now().year
    sequence = _next_sequence("LR", year)
    return f"LR-{year}-{sequence:06d}", f"ACC-{year}-{sequence:06d}"


def generate_user_id(role: str) -> str:
    """Generates a unique User ID formatted as ROLE-YYYY-XXXXXX."""
    prefix = ROLE_PREFIXES.get(role)
    if not prefix:
        raise ValueError(f"Invalid role for User ID generation: {role}")
        
    year = datetime.now().year
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Try to update existing sequence or insert a new one
            # Use RETURNING to get the updated sequence number
            cur.execute("""
                INSERT INTO UserIdSequences (role_prefix, year, last_sequence)
                VALUES (%s, %s, 1)
                ON CONFLICT (role_prefix, year) 
                DO UPDATE SET last_sequence = UserIdSequences.last_sequence + 1
                RETURNING last_sequence;
            """, (prefix, year))
            
            result = cur.fetchone()
            if not result:
                raise Exception("Failed to generate sequence number")
                
            sequence = result[0]
            conn.commit()
            
    # Format: PREFIX-YYYY-XXXXXX
    return f"{prefix}-{year}-{sequence:06d}"
