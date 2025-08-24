from __future__ import annotations
from smolagents import Tool # or from smolagents.tools import tool (haven't worked out diff yet
from datetime import datetime
import json

from src.utils.export_writer import ExportWriter
from src.utils.config import PATIENT_ID, SESSION_TYPE, SESSION_DATE
from src.utils.chunk_ids import next_chunk_id_counter  # runtime-safe (host/sandbox aware)

class DocumentLearningInsights(Tool):
    name = "document_learning_insights"
    description = (
        "Persist a markdown note + JSON metadata for the current session. "
        "Optionally index the note into the psych_metadata store for retrieval."
    )
    # Must match forward(...) parameter names exactly:
    inputs = {
        "title": {
            "type": "string",
            "description": "Short title for the note (used in file header).",
            "default": "Analysis Insights",
        },
        "notes_markdown": {
            "type": "string",
            "description": "Body of the note in Markdown.",
            "default": "",
        },
        "metadata": {
            "type": "object",
            "description": "Arbitrary JSON-serializable metadata to store alongside the note.",
            "nullable": True,
            "default": None,
        },
        "index": {
            "type": "boolean",
            "description": "If true, embed this note into the metadata index.",
            "default": False,
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "chunk_id": {"type": "integer"},
            "markdown": {"type": "object"},
            "json": {"type": "object"},
            "message": {"type": "string"},
        },
        "required": ["chunk_id", "markdown", "json", "message"],
    }

    def __init__(self, sandbox=None, indexer=None):
        """
        sandbox: e2b sandbox (optional)
        indexer: callable to index notes, e.g. metadata_embedder.index_agent_note
                 signature: indexer(chunk_id:int, title:str, notes:str, metadata:dict) -> None
        """
        super().__init__()
        self.sandbox = sandbox
        self.indexer = indexer  # injected dependency; not part of inputs

    # <-- smolagents will validate against THIS signature -->
    def forward(
        self,
        title: str = "Analysis Insights",
        notes_markdown: str = "",
        metadata: dict | None = None,
        index: bool = False,
    ):
        # 1) Allocate the next chunk id at runtime (safe in host or sandbox)
        k = next_chunk_id_counter(sandbox=self.sandbox)

        # 2) Build writer bound to the current session
        exporter = ExportWriter(
            sandbox=self.sandbox,
            patient_id=PATIENT_ID,
            session_type=SESSION_TYPE,
            session_date=SESSION_DATE
        )

        # 3) Compose filenames (kept near the data outputs)
        md_name   = f"insights_chunk_{k}.md"
        json_name = f"insights_chunk_{k}.json"

        # 4) Prepare payloads
        ts = datetime.utcnow().isoformat() + "Z"
        md = f"""## {title} — Chunk {k}
_Time:_ {ts}

{(notes_markdown or "").strip()}
"""

        meta = metadata or {}
        json_obj = {
            "patient_id": PATIENT_ID,
            "session_type": SESSION_TYPE,
            "session_date": SESSION_DATE,
            "chunk_id": k,
            "title": title,
            "timestamp_utc": ts,
            "metadata": meta,
        }

        # 5) Write both files via ExportWriter
        md_paths   = exporter.write_text(k, md_name, md)
        json_paths = exporter.write_text(k, json_name, json.dumps(json_obj, indent=2))

        # 6) Optionally index this note for retrieval (embeddings)
        if index and callable(self.indexer):
            try:
                self.indexer(k, title, notes_markdown, meta)
            except Exception as e:
                return {
                    "chunk_id": k,
                    "markdown": md_paths,
                    "json": json_paths,
                    "message": f"Saved insights for chunk {k} (indexing error ignored: {e})"
                }

        return {
            "chunk_id": k,
            "markdown": md_paths,
            "json": json_paths,
            "message": f"Saved insights for chunk {k}."
        }