from __future__ import annotations
import os, json
from typing import Any, Dict
from . import config as C
from .session_paths import session_paths_for_chunk
import sqlite3

"""
This creates the nested directories and files (like './export/{PATIENT_ID}/...' for usage as 'PATIENT_ID / SESSION_TYPE / SESSION_DATE')
It hands back stable paths (e.g. csv_path, graph_path) and writes the file content in both host and sandbox so persistence works.

Example usage:
# ... existing code ...
"""

class ExportWriter:
    """
    Writes session exports (CSV/Graph) using sandbox-first paths.
    Use with: exporter = ExportWriter(sandbox); exporter.write_csv(k, df); exporter.write_graph(k, obj)
    """
    def __init__(self, sandbox=None, patient_id: str | None = None,
                 session_type: str | None = None, session_date: str | None = None):
        self.sandbox = sandbox
        self.pid = patient_id or C.PATIENT_ID
        self.st = session_type or C.SESSION_TYPE
        self.sd = session_date or C.SESSION_DATE

        # Derive canonical session export base once (sandbox-first), and its host mirror.
        base_paths = session_paths_for_chunk(self.pid, self.st, self.sd, k=1)
        self.export_base_sbx = base_paths["export_base"]  # e.g., /workspace/exports/PID/TYPE/DATE
        self.export_base_host = "." + self.export_base_sbx if self.export_base_sbx.startswith("/") else self.export_base_sbx

        # Canonical SQLite location (sandbox-first) and host mirror
        self.sqlite_path_sbx = base_paths["sqlite_db"]    # e.g., /workspace/exports/therapy.db
        self.sqlite_path_host = "." + self.sqlite_path_sbx if self.sqlite_path_sbx.startswith("/") else self.sqlite_path_sbx

    def _ensure_dir(self, path: str):
        # host-side mkdir
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _write_text(self, sbx_path: str, host_path: str, text: str):
        # sandbox
        if self.sandbox:
            # ensure dir
            try:
                self.sandbox.files.mkdir(os.path.dirname(sbx_path))
            except Exception:
                pass
            self.sandbox.files.write(sbx_path, text.encode("utf-8"))
        # host (useful when running outside sandbox)
        self._ensure_dir(host_path)
        with open(host_path, "w", encoding="utf-8") as f:
            f.write(text)

    def write_text(self, k: int, filename: str, text: str) -> dict[str, str]:
        """
        Write an arbitrary text file for chunk k (e.g., insights markdown).
        Returns {"sandbox": "...", "host": "..."} paths.
        """
        # Re-use the session path templates
        from .session_paths import session_paths_for_chunk

        paths = session_paths_for_chunk(self.pid, self.st, self.sd, k)
        # Put the text under the same export/{pid}/{type}/{date} tree
        # Note: we DON'T hardcode a subfolder; you control it via filename.
        sbx_path = f'{paths["export_base"]}/{filename}'
        host_path = "." + sbx_path if sbx_path.startswith("/") else sbx_path

        # ensure dirs & write
        try:
            # sandbox
            if self.sandbox:
                try:
                    self.sandbox.files.mkdir(paths["export_base"])
                except Exception:
                    pass
                self.sandbox.files.write(sbx_path, text.encode("utf-8"))
        finally:
            # host
            os.makedirs(os.path.dirname(host_path), exist_ok=True)
            with open(host_path, "w", encoding="utf-8") as f:
                f.write(text)

        return {"sandbox": sbx_path, "host": host_path}

    def write_csv(self, k: int, df) -> dict[str, str]:
        paths = session_paths_for_chunk(self.pid, self.st, self.sd, k)
        csv_sbx = paths["csv_path"]
        # Host mirror path: replace '/workspace' with '.' for local runs
        csv_host = "." + csv_sbx if csv_sbx.startswith("/") else csv_sbx
        # Write
        csv_text = df.to_csv(index=False)
        self._write_text(csv_sbx, csv_host, csv_text)
        return {"sandbox": csv_sbx, "host": csv_host}

    def write_graph(self, k: int, graph_obj: dict[str, Any]) -> dict[str, str]:
        paths = session_paths_for_chunk(self.pid, self.st, self.sd, k)
        graph_sbx = paths["graph_path"]
        graph_host = "." + graph_sbx if graph_sbx.startswith("/") else graph_sbx
        graph_text = json.dumps(graph_obj, indent=2)
        self._write_text(graph_sbx, graph_host, graph_text)
        return {"sandbox": graph_sbx, "host": graph_host}

    def write_sql(self, filename: str = "therapy.db") -> Dict[str, Any]:
        """
        Ensure the session-scoped SQLite DB exists and return paths.
        Canonical (sandbox-first): /workspace/exports/therapy.db
        Host mirror (used by sqlite3): ./workspace/exports/therapy.db
        """
        # Use the host path for sqlite3 in this Python process
        host_path = self.sqlite_path_host
        os.makedirs(os.path.dirname(host_path), exist_ok=True)

        # Touch DB file if missing on host
        if not os.path.exists(host_path):
            conn = sqlite3.connect(host_path)
            conn.close()

        paths: Dict[str, str] = {"host": host_path}

        # Optional: ensure a mirror in the sandbox for inspection
        if self.sandbox:
            sbx_path = self.sqlite_path_sbx
            try:
                self.sandbox.files.mkdir(os.path.dirname(sbx_path))
            except Exception:
                pass
            try:
                # Touch in sandbox (SQLite file will be created/overwritten as needed)
                self.sandbox.files.write(sbx_path, b"")
                paths["sandbox"] = sbx_path
            except Exception:
                pass

        return {"db_path": host_path, "paths": paths}