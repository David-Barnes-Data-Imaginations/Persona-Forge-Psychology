from __future__ import annotations
import os, json
from typing import Any
from . import config as C
from .session_paths import session_paths_for_chunk

"""
This creates the nested directories and files (like './export/{PATIENT_ID}/...' for usage as 'PATIENT_ID / SESSION_TYPE / SESSION_DATE')
It hands back stable paths (e.g. csv_path, graph_path) and writes the file content in both host and sandbox so persistence works.

Example usage:
```
from utils.export_writer import ExportWriter
from utils.config import PATIENT_ID, SESSION_TYPE, SESSION_DATE

exporter = ExportWriter(sandbox, PATIENT_ID, SESSION_TYPE, SESSION_DATE)

csv_host, csv_sbx = exporter.path(f"qa_chunk_{chunk_number}.csv")
graph_host, graph_sbx = exporter.path(f"graph_chunk_{chunk_number}.json")
```
# When saving:
```
exporter.write(f"qa_chunk_{chunk_number}.csv", csv_content)
exporter.write(f"graph_chunk_{chunk_number}.json", json.dumps(graph_data, indent=2))
```
This way there's no need to hard-code './export/...' in prompts or tools anymore.
Router / Passes: your Pass B / Pass C instructions now reference:

- CSV path template: /workspace/export/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/qa_chunk_{k}.csv
- Graph JSON template: /workspace/export/{PATIENT_ID}/{SESSION_TYPE}/{SESSION_DATE}/graph_chunk_{k}.json
- Tools: when the model needs to save, either:
- call a CSV save tool / Graph save tool that internally uses session_paths_for_chunk(..., k) and os.makedirs, or
- call ExportWriter.write_csv(k, df) and ExportWriter.write_graph(k, obj).
- Persistence: persist.on_shutdown() pulls /workspace/export → ./export, so the results show on host.

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
