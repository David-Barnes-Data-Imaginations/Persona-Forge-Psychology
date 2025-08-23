from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Tuple
import os

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

def next_chunk_id_counter(*, sandbox=None,
                          index_sbx="/workspace/insights/chunk_index.txt",
                          index_host="./insights/chunk_index.txt") -> int:
    """Return next chunk id and persist it where we are (sandbox or host)."""
    def _read_local(p: str) -> int:
        try:
            with open(p, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return -1

    def _write_local(p: str, v: int):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(str(v))

    if sandbox:
        # ensure dir and read
        try:
            sandbox.files.mkdir("/workspace/insights")
        except Exception:
            pass
        try:
            data = sandbox.files.read(index_sbx)
            current = int((data.decode() if isinstance(data, (bytes, bytearray)) else data).strip())
        except Exception:
            current = -1
        chunk = current + 1
        sandbox.files.write(index_sbx, str(chunk).encode())
        return chunk
    else:
        current = _read_local(index_host)
        chunk = current + 1
        _write_local(index_host, chunk)
        return chunk