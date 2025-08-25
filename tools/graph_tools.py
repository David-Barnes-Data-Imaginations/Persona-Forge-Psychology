from __future__ import annotations
import json
from typing import Any, Dict, Optional
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

    # Keep schema permissive (nullable True) to satisfy smolagents, enforce in code.
    inputs = {
        "k": {
            "type": "integer",
            "description": "Chunk index.",
            "nullable": True
        },
        "graph": {
            "type": "object",
            "description": "Graph‑JSON payload.",
            "nullable": True
        },
        "autofill": {
            "type": "boolean",
            "description": "If true, fill patient_id/session_date/type/chunk_index.",
            "default": True,
            "nullable": False
        }
    }
    output_type = "object"

    def __init__(self, sandbox=None):
        # Probe before super().__init__ triggers validation
        try:
            from pprint import pformat
            print("[WGFC] inputs right now ->", pformat(self.inputs))
        except Exception:
            pass
        super().__init__()
        self.sandbox = sandbox

    def forward(self, k: Optional[int], graph: Optional[Dict[str, Any]], autofill: bool = True):
        # Hard enforcement so the tool behaves like a required API.
        if k is None:
            return {"ok": False, "error": "missing_required_argument: k"}
        if graph is None:
            return {"ok": False, "error": "missing_required_argument: graph"}

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
    Persist Cypher text for chunk k under the session `cypher/` directory.
    """
    name = "write_cypher_for_chunk"
    description = "Write Cypher text for chunk k to the session's cypher directory."

    # Keep schema permissive (nullable True) to satisfy smolagents; enforce in code.
    inputs = {
        "k": {
            "type": "integer",
            "description": "Chunk index.",
            "nullable": True
        },
        "cypher_text": {
            "type": "string",
            "description": "Cypher statements to write.",
            "nullable": True
        },
    }
    output_type = "object"

    def __init__(self, sandbox=None):
        # Probe before super().__init__ triggers validation (handy while iterating)
        try:
            from pprint import pformat
            print("[W CYC] inputs right now ->", pformat(self.inputs))
        except Exception:
            pass
        super().__init__()
        self.sandbox = sandbox

    def forward(self, k: Optional[int], cypher_text: Optional[str]):
        # Hard enforcement so the tool behaves like a required API.
        if k is None:
            return {"ok": False, "error": "missing_required_argument: k"}
        if cypher_text is None:
            return {"ok": False, "error": "missing_required_argument: cypher_text"}

        text = cypher_text.strip()
        if not text:
            return {"ok": False, "error": "empty_cypher_text"}

        t = session_templates(C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
        fname = f"cypher/chunk_{k}.cypher"

        exporter = ExportWriter(
            sandbox=self.sandbox,
            patient_id=C.PATIENT_ID,
            session_type=C.SESSION_TYPE,
            session_date=C.SESSION_DATE,
        )
        # Ensure trailing newline for POSIX-y niceness
        payload = text if text.endswith("\n") else text + "\n"
        paths = exporter.write_text(k, fname, payload)

        preview = "\n".join(text.splitlines()[:15])
        return {"ok": True, "paths": paths, "preview": preview, "chunk_id": k}
