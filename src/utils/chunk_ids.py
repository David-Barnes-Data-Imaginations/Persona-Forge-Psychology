from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Tuple

def _ensure_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key TEXT NOT NULL,
        patient_id TEXT NOT NULL,
        session_type TEXT NOT NULL,
        session_date TEXT NOT NULL,
        chunk_id INTEGER NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(session_key, chunk_id)
    );
    """)
    conn.commit()

def _sess_key(pid: str, stype: str, sdate: str) -> str:
    return f"{pid}|{stype}|{sdate}"

def next_chunk_id(db_path: str, *, patient_id: str, session_type: str, session_date: str) -> int:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _ensure_schema(conn)
        cur = conn.cursor()
        skey = _sess_key(patient_id, session_type, session_date)
        cur.execute("SELECT COALESCE(MAX(chunk_id)+1, 0) FROM chunks WHERE session_key = ?", (skey,))
        nxt, = cur.fetchone()
        cur.execute("""
            INSERT INTO chunks(session_key, patient_id, session_type, session_date, chunk_id)
            VALUES (?, ?, ?, ?, ?)
        """, (skey, patient_id, session_type, session_date, int(nxt)))
        conn.commit()
        return int(nxt)
