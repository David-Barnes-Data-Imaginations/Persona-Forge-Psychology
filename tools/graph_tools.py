# tools/graph_tools.py
from __future__ import annotations
import json
from typing import Any, Dict
from smolagents import Tool
from jsonschema import validate as js_validate, ValidationError, SchemaError

from src.utils.export_writer import ExportWriter
from src.utils.session_paths import session_templates, session_paths_for_chunk
from src.utils import config as C

def _read_text_host_or_sbx(sandbox, path_sbx: str, path_host: str) -> str:
    """Read a text file from sandbox if available, else host."""
    if sandbox:
        blob = sandbox.files.read(path_sbx)
        return blob.decode("utf-8") if isinstance(blob, (bytes, bytearray)) else str(blob)
    with open(path_host, "r", encoding="utf-8") as f:
        return f.read()

class WriteGraphForChunk(Tool):
    """
    Validate then persist a Graph‑JSON object for chunk k.
    The schema is loaded from psych_metadata/graph_schema.json (sandbox-first).
    """
    name = "write_graph_for_chunk"
    description = "Validate a Graph‑JSON dict for chunk k and persist it to the session export directory."
    inputs = {
        "k": {"type": "integer", "description": "Chunk index (0‑based or 1‑based—use your convention).", "required": True},
        "graph": {"type": "object", "description": "Graph‑JSON payload to validate & save.", "required": True},
    }

    def __init__(self, sandbox=None):
        super().__init__()
        self.sandbox = sandbox

    def run(self, k: int, graph: Dict[str, Any]):
        # Load schema (sandbox-first)
        t = session_templates(C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
        schema_text = _read_text_host_or_sbx(
            self.sandbox,
            path_sbx=t.graph_schema_json,
            path_host="." + t.graph_schema_json if t.graph_schema_json.startswith("/") else t.graph_schema_json
        )
        try:
            schema = json.loads(schema_text)
        except Exception as e:
            return {"ok": False, "error": f"failed_to_parse_schema: {e}"}

        # Validate
        try:
            js_validate(instance=graph, schema=schema)
        except ValidationError as e:
            return {"ok": False, "error": f"validation_error: {e.message}", "path": list(e.path)}
        except SchemaError as e:
            return {"ok": False, "error": f"schema_error: {e.message}"}

        # Persist
        exporter = ExportWriter(
            sandbox=self.sandbox,
            patient_id=C.PATIENT_ID,
            session_type=C.SESSION_TYPE,
            session_date=C.SESSION_DATE,
        )
        paths = exporter.write_graph(k, graph)

        # Quick counters (best-effort)
        utterances = graph.get("utterances", [])
        n_utts = len(utterances)
        return {"ok": True, "paths": paths, "counts": {"utterances": n_utts}, "chunk_id": k}


class WriteCypherForChunk(Tool):
    """
    Persist Cypher text for chunk k under session `cypher/` directory.
    """
    name = "write_cypher_for_chunk"
    description = "Write Cypher text for chunk k to the session's cypher directory."
    inputs = {
        "k": {"type": "integer", "description": "Chunk index.", "required": True},
        "cypher_text": {"type": "string", "description": "Cypher statements to write.", "required": True},
    }

    def __init__(self, sandbox=None):
        super().__init__()
        self.sandbox = sandbox

    def run(self, k: int, cypher_text: str):
        t = session_templates(C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
        # Build a filename
        fname = f"cypher/chunk_{k}.cypher"

        # Reuse ExportWriter.write_text to place file under session export base
        exporter = ExportWriter(
            sandbox=self.sandbox,
            patient_id=C.PATIENT_ID,
            session_type=C.SESSION_TYPE,
            session_date=C.SESSION_DATE,
        )
        paths = exporter.write_text(k, fname, cypher_text)

        # Also return the first few lines for quick inspection (like your prompt asks)
        preview = "\n".join(cypher_text.splitlines()[:15])
        return {"ok": True, "paths": paths, "preview": preview, "chunk_id": k}
