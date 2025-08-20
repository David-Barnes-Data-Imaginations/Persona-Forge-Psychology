from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from typing import Iterable, Mapping, Any, Optional

# SQLAlchemy optional (nice for pandas / ORM)
try:
    from sqlalchemy import create_engine, text
    SQLA_OK = True
except Exception:
    SQLA_OK = False

PRAGMA_BOOT = [
"PRAGMA journal_mode=WAL;",
"PRAGMA synchronous=NORMAL;",
"PRAGMA temp_store=MEMORY;",
"PRAGMA mmap_size=134217728;", # 128MB
]

def init_sqlite(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        for p in PRAGMA_BOOT:
            cur.execute(p)
        conn.commit()

def ensure_schema(db_path: str) -> None:
    """Create minimal tables used by your pipeline; extend as needed."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            session_type TEXT,
            session_date TEXT,
            q TEXT,
            a TEXT,
            source TEXT
            );
            """
        )
        cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            session_date TEXT,
            kind TEXT, -- e.g. DISTORTION, EMOTION, STAGE
            payload TEXT, -- JSON blob
            created_at TEXT DEFAULT (datetime('now'))
            );
        """
        )
        conn.commit()

@contextmanager
def sqlite_conn(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()

def bulk_insert_qa(db_path: str, rows: Iterable[Mapping[str, Any]]):
    with sqlite_conn(db_path) as conn:
        cur = conn.cursor()
        cur.executemany(
        """
            INSERT INTO qa_pairs (patient_id, session_type, session_date, q, a, source)
            VALUES (:patient_id, :session_type, :session_date, :q, :a, :source)
            """,
            list(rows),
        )
        conn.commit()

def run_query(db_path: str, sql: str, params: Optional[dict]=None):
    if SQLA_OK:
        eng = create_engine(f"sqlite:///{db_path}")
        with eng.connect() as cx:
            res = cx.execute(text(sql), params or {})
            return [dict(r._mapping) for r in res]

# fallback to sqlite3
    with sqlite_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql, params or {})
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]