from __future__ import annotations
import json
from typing import Any, Dict
from smolagents import Tool
from jsonschema import validate as js_validate, ValidationError, SchemaError
from datetime import datetime
import re

from src.utils.export_writer import ExportWriter
from src.utils.session_paths import session_templates
from src.utils import config as C

def _read_text_host_or_sbx(sandbox, path_sbx: str, path_host: str) -> str:
    if sandbox:
        blob = sandbox.files.read(path_sbx)
        return blob.decode("utf-8") if isinstance(blob, (bytes, bytearray)) else str(blob)
    with open(path_host, "r", encoding="utf-8") as f:
        return f.read()

def _coerce_date(d: str) -> str:
    """Return YYYY-MM-DD if possible; otherwise pass through."""
    if not d:
        return d
    # Accept common variants like 19/08/2025, 19-08-25, etc.
    m = re.match(r"^(\d{2})[/-](\d{2})[/-](\d{2,4})$", d)
    if m:
        dd, mm, yy = m.groups()
        yy = yy if len(yy) == 4 else ("20" + yy)
        try:
            return datetime(int(yy), int(mm), int(dd)).strftime("%Y-%m-%d")
        except Exception:
            return d
    return d

def _clamp(x: float, lo: float, hi: float) -> float:
    try:
        return min(hi, max(lo, float(x)))
    except Exception:
        return x

def _as_list(x) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]

def _normalize_graph(graph: Dict[str, Any], *, k: int) -> Dict[str, Any]:
    g = dict(graph or {})
    # Top-level fills
    g.setdefault("patient_id", C.PATIENT_ID)
    g.setdefault("session_date", C.SESSION_DATE)
    g["session_date"] = _coerce_date(g.get("session_date") or C.SESSION_DATE)
    g.setdefault("session_type", C.SESSION_TYPE)
    g.setdefault("chunk_index", k)

    # Ensure utterances list
    utts = g.get("utterances")
    if utts is None:
        g["utterances"] = []
    elif not isinstance(utts, list):
        g["utterances"] = [utts]

    # Per‑utterance normalization (best‑effort, conservative)
    for u in g["utterances"]:
        if not isinstance(u, dict):
            continue
        # speaker, turn_id
        if "speaker" in u and isinstance(u["speaker"], str):
            s = u["speaker"].strip().lower()
            if "therap" in s: u["speaker"] = "Therapist"
            elif "client" in s or "patient" in s: u["speaker"] = "Client"
        # annotations block
        ann = u.get("annotations") or {}
        if not isinstance(ann, dict): ann = {}
        # lists
        for key in ["distortions", "emotions_primary", "schemas", "defense_mechanisms"]:
            ann[key] = _as_list(ann.get(key))
        if "attachment_style" in ann and ann["attachment_style"] is None:
            ann["attachment_style"] = "Unknown"
        # sentiment2d
        if "sentiment2d" in ann and isinstance(ann["sentiment2d"], dict):
            va = ann["sentiment2d"]
            if "valence" in va: va["valence"] = _clamp(va["valence"], -1.0, 1.0)
            if "arousal" in va: va["arousal"] = _clamp(va["arousal"], -1.0, 1.0)
        # big5
        if "big5" in ann and isinstance(ann["big5"], dict):
            for t in list(ann["big5"].keys()):
                ann["big5"][t] = _clamp(ann["big5"][t], 0.0, 1.0)
        u["annotations"] = ann
    return g

class WriteGraphForChunk(Tool):
    name = "write_graph_for_chunk"
    description = "Normalize, validate, and persist a Graph‑JSON dict for chunk k."
    inputs = {
        "k": {"type": "integer", "description": "Chunk index.", "required": True},
        "graph": {"type": "object", "description": "Graph‑JSON payload.", "required": True},
        "autofill": {"type": "boolean", "description": "If true, fill patient_id/session_date/type/chunk_index.", "required": False}
    }

    def __init__(self, sandbox=None):
        super().__init__()
        self.sandbox = sandbox

    def run(self, k: int, graph: Dict[str, Any], autofill: bool = True):
        # 1) Load schema (sandbox‑first)
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

        # 2) Normalize / autofill
        g = _normalize_graph(graph, k=k) if autofill else graph

        # 3) Validate
        try:
            js_validate(instance=g, schema=schema)
        except ValidationError as e:
            return {"ok": False, "error": f"validation_error: {e.message}", "path": list(e.path)}
        except SchemaError as e:
            return {"ok": False, "error": f"schema_error: {e.message}"}

        # 4) Persist
        exporter = ExportWriter(self.sandbox, C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
        paths = exporter.write_graph(k, g)
        return {
            "ok": True,
            "paths": paths,
            "counts": {"utterances": len(g.get("utterances", []))},
            "chunk_id": k
        }

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
