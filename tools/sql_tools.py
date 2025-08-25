from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from smolagents import Tool
import os
import sqlite3
import json
from src.utils.export_writer import ExportWriter
from src.utils.session_paths import session_templates
from src.utils import config as C

# Existing single-qa tool retained for convenience
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
                                                                patient_id   TEXT NOT NULL,
                                                                session_type TEXT NOT NULL,
                                                                session_date TEXT NOT NULL,
                                                                turn_id      INTEGER NOT NULL,
                                                                speaker      TEXT,
                                                                text_raw     TEXT,
                                                                text_clean   TEXT,
                                                                PRIMARY KEY (patient_id, session_type, session_date, turn_id)
                            )
                        """)
            # For single QA, map to a single "turn_id" row as needed (optional)
            cur.execute(
                "INSERT INTO qa_pairs (patient_id, session_type, session_date, turn_id, speaker, text_raw, text_clean) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(patient_id, session_type, session_date, turn_id) DO UPDATE SET "
                "speaker=excluded.speaker, text_raw=excluded.text_raw, text_clean=excluded.text_clean",
                (patient_id, C.SESSION_TYPE, session_date, 1, "Client", question, answer)
            )
            conn.commit()
            rows = 1
            conn.close()
            return {"ok": True, "db_path": self.db_path, "rows_affected": rows,
                    "message": f"Upserted QA for {patient_id} @ {session_date}"}
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            return {"ok": False, "db_path": self.db_path, "rows_affected": 0,
                    "message": f"sqlite_error: {e}"}

class UpsertDFCleanToSQLite(Tool):
    """
    Bulk-upsert rows from Pass A's df_clean into /workspace/exports/therapy.db (host-mirrored).
    Accept either `csv_text` (preferred for memory) or `records` (list of dicts).
    Schema/PK enforced:
      - Columns: patient_id, session_type, session_date, turn_id, speaker, text_raw, text_clean
      - PRIMARY KEY (patient_id, session_type, session_date, turn_id)
    """
    name = "upsert_df_clean_to_sqlite"
    description = "Upsert df_clean rows into the session SQLite database."

    inputs = {
        "csv_text": {
            "type": "string",
            "description": "CSV with columns: session_date,session_type,turn_id,speaker,text_raw,text_clean",
            "nullable": True
        },
        "records": {
            "type": "array",
            "items": {"type": "object"},
            "description": "List of row dicts matching df_clean columns.",
            "nullable": True
        },
        "patient_id": {
            "type": "string",
            "description": "Patient identifier; if omitted, uses config.PATIENT_ID.",
            "nullable": True
        },
        "session_type": {
            "type": "string",
            "description": "Session type; if omitted, uses config.SESSION_TYPE.",
            "nullable": True
        },
        "session_date": {
            "type": "string",
            "description": "Session date; if omitted, uses config.SESSION_DATE.",
            "nullable": True
        }
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

    def _rows_from_csv(self, csv_text: str) -> Tuple[List[str], List[List[Any]]]:
        import pandas as pd
        from io import StringIO
        df = pd.read_csv(StringIO(csv_text))
        expected = ["session_date","session_type","turn_id","speaker","text_raw","text_clean"]
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise ValueError(f"missing_required_columns: {missing}")
        cols = expected
        rows = df[cols].values.tolist()
        return cols, rows

    def _rows_from_records(self, records: List[Dict[str, Any]]) -> Tuple[List[str], List[List[Any]]]:
        import pandas as pd
        df = pd.DataFrame.from_records(records or [])
        expected = ["session_date","session_type","turn_id","speaker","text_raw","text_clean"]
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise ValueError(f"missing_required_columns: {missing}")
        cols = expected
        rows = df[cols].values.tolist()
        return cols, rows

    def forward(
            self,
            csv_text: Optional[str] = None,
            records: Optional[List[Dict[str, Any]]] = None,
            patient_id: Optional[str] = None,
            session_type: Optional[str] = None,
            session_date: Optional[str] = None,
    ):
        if (csv_text is None and records is None) or (csv_text and records):
            return {"ok": False, "error": "Provide exactly one of `csv_text` or `records`."}

        pid = patient_id or C.PATIENT_ID
        stype = session_type or C.SESSION_TYPE
        sdate = session_date or C.SESSION_DATE

        try:
            if csv_text is not None:
                cols, rows = self._rows_from_csv(csv_text)
            else:
                cols, rows = self._rows_from_records(records or [])
        except Exception as e:
            return {"ok": False, "error": f"input_parse_error: {e}"}

        if not rows:
            return {"ok": True, "db_path": self.db_path, "upserts": 0, "message": "no_rows"}

        # Upsert into the host-mirror DB (safe from the host Python process)
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                        CREATE TABLE IF NOT EXISTS qa_pairs (
                                                                patient_id   TEXT NOT NULL,
                                                                session_type TEXT NOT NULL,
                                                                session_date TEXT NOT NULL,
                                                                turn_id      INTEGER NOT NULL,
                                                                speaker      TEXT,
                                                                text_raw     TEXT,
                                                                text_clean   TEXT,
                                                                PRIMARY KEY (patient_id, session_type, session_date, turn_id)
                            )
                        """)
            # Prepare upsert
            sql = (
                "INSERT INTO qa_pairs (patient_id, session_type, session_date, turn_id, speaker, text_raw, text_clean) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(patient_id, session_type, session_date, turn_id) DO UPDATE SET "
                "speaker=excluded.speaker, text_raw=excluded.text_raw, text_clean=excluded.text_clean"
            )
            count = 0
            for r in rows:
                # r order: session_date, session_type, turn_id, speaker, text_raw, text_clean
                sd, st, tid, spk, raw, clean = r
                cur.execute(sql, (pid, stype or st, sdate or sd, int(tid), spk, raw, clean))
                count += 1
            conn.commit()
            conn.close()

            # Optional: mirror the updated DB into the sandbox so the file is visible at /workspace/exports/therapy.db
            try:
                if self.sandbox and "sandbox" in getattr(self, "paths", {}):
                    with open(self.db_path, "rb") as f:
                        blob = f.read()
                    sbx_path = self.paths.get("sandbox")
                    if sbx_path:
                        # ensure dir then write
                        try:
                            self.sandbox.files.mkdir(os.path.dirname(sbx_path))
                        except Exception:
                            pass
                        self.sandbox.files.write(sbx_path, blob)
            except Exception:
                # Mirroring errors are non-fatal
                pass

            return {"ok": True, "db_path": self.db_path, "upserts": count, "message": f"upserted {count} rows"}
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            return {"ok": False, "db_path": self.db_path, "upserts": 0, "message": f"sqlite_error: {e}"}

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