from smolagents import Tool
from typing import Optional, Dict, Any  # make sure these are imported somewhere above
from src.utils.export_writer import ExportWriter
from src.utils.session_paths import session_templates
from src.utils import config as C

class WriteCypherForChunk(Tool):
    """
    Persist Cypher text for chunk k under session `cypher/` directory.
    """
    name = "write_cypher_for_chunk"
    description = "Write Cypher text for chunk k to the session's cypher directory."

    # Permissive for smolagents (nullable True), enforce in forward()
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
        # Optional: echo schema before validation happens in Tool.__init__
        try:
            from pprint import pformat
            print("[W C F C] inputs ->", pformat(self.inputs))
        except Exception:
            pass
        super().__init__()
        self.sandbox = sandbox

    def forward(self, k: Optional[int], cypher_text: Optional[str]):
        # Hard enforce requireds at runtime
        if k is None:
            return {"ok": False, "error": "missing_required_argument: k"}
        if cypher_text is None or not str(cypher_text).strip():
            return {"ok": False, "error": "missing_required_argument: cypher_text"}

        cypher_text = str(cypher_text)

        # Build session‑scoped filename
        t = session_templates(C.PATIENT_ID, C.SESSION_TYPE, C.SESSION_DATE)
        fname = f"cypher/chunk_{k}.cypher"

        # Persist via ExportWriter
        exporter = ExportWriter(
            sandbox=self.sandbox,
            patient_id=C.PATIENT_ID,
            session_type=C.SESSION_TYPE,
            session_date=C.SESSION_DATE,
        )
        paths = exporter.write_text(k, fname, cypher_text)

        preview = "\n".join(cypher_text.splitlines()[:15])
        return {"ok": True, "paths": paths, "preview": preview, "chunk_id": k}
