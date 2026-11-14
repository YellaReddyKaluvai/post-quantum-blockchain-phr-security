import psycopg
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
from .config import get_settings
import os
import logging

settings = get_settings()

logger = logging.getLogger(__name__)

# Connection pool
_pool = None

def init_pool():
    global _pool
    if not _pool:
        db_url = settings.DATABASE_URL
        try:
            _pool = ConnectionPool(db_url, min_size=1, max_size=10)
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")

@contextmanager
def get_db():
    if not _pool:
        init_pool()
    
    if not _pool:
        raise Exception("Database connection pool is not initialized")
        
    with _pool.connection() as conn:
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise e

def init_db():
    """Run schema migration (if not using Alembic)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # We can execute init.sql here if needed
            init_sql_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'init.sql')
            if os.path.exists(init_sql_path):
                with open(init_sql_path, 'r') as f:
                    try:
                        cur.execute(f.read())
                        conn.commit()
                    except Exception as e:
                        logger.error(f"Failed to execute init.sql: {e}")
                        conn.rollback()
                        raise
