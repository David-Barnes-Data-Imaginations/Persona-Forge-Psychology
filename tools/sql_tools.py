from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from smolagents import Tool
import os
import sqlite3
from src.utils.export_writer import ExportWriter
from src.utils.session_paths import session_templates
from src.utils import config as C

class WriteQAtoSQLite(Tool):
    name = "write_qa_to_sqlite"
    description = "Insert a QA pair (patient_id, session_date, question, answer) into the SQLite database."

    inputs = {
        "qa": {
            "type": "object",
            "description": "QA payload: {patient_id, session_date, question, answer}.",
            "nullable": True
        }
    }

    output_schema = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "db_path": {"type": "string"},
            "rows_affected": {"type": "integer"},
            "message": {"type": "string"}
        },
        "required": ["ok", "db_path", "rows_affected", "message"]
    }
    output_type = "object"

    def __init__(self, sandbox=None, db_path: Optional[str] = None):
        super().__init__()
        self.sandbox = sandbox

        if db_path:
            self.db_path = db_path
            self.paths = {"host": db_path}
        else:
            exporter = ExportWriter(self.sandbox, C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
            info = exporter.write_sql(filename="therapy.db")
            self.db_path = info["db_path"]
            self.paths = info["paths"]

    def forward(self, qa: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if qa is None:
            return {"ok": False, "db_path": self.db_path, "rows_affected": 0,
                    "message": "missing_required_argument: qa"}

        patient_id = qa.get("patient_id")
        session_date = qa.get("session_date")
        question = qa.get("question")
        answer = qa.get("answer")

        missing = [k for k, v in [("patient_id", patient_id),
                                  ("session_date", session_date),
                                  ("question", question),
                                  ("answer", answer)] if v in (None, "")]
        if missing:
            return {"ok": False, "db_path": self.db_path, "rows_affected": 0,
                    "message": f"missing_fields: {', '.join(missing)}"}

        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS qa_pairs (
                    patient_id   TEXT,
                    session_date TEXT,
                    question     TEXT,
                    answer       TEXT
                )
            """)
            cur.execute(
                "INSERT INTO qa_pairs (patient_id, session_date, question, answer) VALUES (?, ?, ?, ?)",
                (patient_id, session_date, question, answer)
            )
            conn.commit()
            # sqlite3's rowcount is unreliable for INSERT; treat as 1 on success
            rows = 1
            conn.close()
            return {"ok": True, "db_path": self.db_path, "rows_affected": rows,
                    "message": f"Inserted QA for {patient_id} @ {session_date}"}
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            return {"ok": False, "db_path": self.db_path, "rows_affected": 0,
                    "message": f"sqlite_error: {e}"}

class QuerySQLite(Tool):
    name = "query_sqlite"
    description = "Run a read-only SQL query (SELECT/PRAGMA) on the session's therapy.db and return rows."

    inputs = {
        "sql": {"type": "string", "description": "SQL (SELECT/PRAGMA only).", "nullable": True},
        "params": {"type": "array", "description": "Optional parameter list.", "nullable": True},
        "limit": {"type": "integer", "description": "Max rows to return.", "nullable": True}
    }

    output_schema = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "db_path": {"type": "string"},
            "rowcount": {"type": "integer"},
            "columns": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "array", "items": {"type": "array"}},
            "message": {"type": "string"}
        },
        "required": ["ok", "db_path", "rowcount", "columns", "rows", "message"]
    }
    output_type = "object"

    def __init__(self, sandbox=None, db_path: Optional[str] = None):
        super().__init__()
        self.sandbox = sandbox

        if db_path:
            self.db_path = db_path
        else:
            exporter = ExportWriter(self.sandbox, C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
            info = exporter.write_sql(filename="therapy.db")
            self.db_path = info["db_path"]

    def forward(self,
                sql: Optional[str] = None,
                params: Optional[List[Any]] = None,
                limit: Optional[int] = None) -> Dict[str, Any]:
        if not sql:
            return {"ok": False, "db_path": self.db_path, "rowcount": 0,
                    "columns": [], "rows": [], "message": "missing_required_argument: sql"}

        s = sql.strip().lower()
        if not (s.startswith("select") or s.startswith("pragma")):
            return {"ok": False, "db_path": self.db_path, "rowcount": 0,
                    "columns": [], "rows": [],
                    "message": "only_read_only_statements_allowed (SELECT/PRAGMA)"}

        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(sql, tuple(params or []))
            rows = cur.fetchall()
            if isinstance(limit, int) and limit > 0:
                rows = rows[:limit]
            cols = [d[0] for d in (cur.description or [])]
            conn.close()
            return {"ok": True, "db_path": self.db_path, "rowcount": len(rows),
                    "columns": cols, "rows": rows, "message": "ok"}
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            return {"ok": False, "db_path": self.db_path, "rowcount": 0,
                    "columns": [], "rows": [], "message": f"sqlite_error: {e}"}

