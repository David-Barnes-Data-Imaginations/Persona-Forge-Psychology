from __future__ import annotations

from smolagents import Tool
from typing import Optional, Dict, Any
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

    # Match forward(...) exactly:
    inputs = {
        "title": {
            "type": "string",
            "description": "Short title for the note (used in file header).",
            "default": "Analysis Insights",
            "nullable": True,   # allow 'None' if caller passes it
        },
        "notes_markdown": {
            "type": "string",
            "description": "Body of the note in Markdown.",
            "default": "",
            "nullable": True,   # if 'None' (coerce to "")
        },
        "metadata": {
            "type": "object",
            "description": "Arbitrary JSON-serializable metadata to store alongside the note.",
            "default": None,
            "nullable": True,
        },
        "index": {
            "type": "boolean",
            "description": "If true, embed this note into the metadata index.",
            "default": False,
            "nullable": False,  # booleans shouldn't be None
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
    # `output_type` is optional when you provide output_schema; keeping it is harmless:
    output_type = "object"

    def __init__(self, sandbox=None, indexer=None):
        """
        sandbox: e2b sandbox (optional)
        indexer: callable to index notes, e.g. metadata_embedder.index_agent_note
                 signature: indexer(chunk_id:int, title:str, notes:str, metadata:dict) -> None
        """
        super().__init__()
        self.sandbox = sandbox
        self.indexer = indexer  # pass MetadataEmbedder.index_agent_note if you want inline indexing

    # smolagents validates *this* signature against `inputs`
    def forward(
        self,
        title: Optional[str] = "Analysis Insights",
        notes_markdown: Optional[str] = "",
        metadata: Optional[Dict[str, Any]] = None,
        index: bool = False,
    ):
        # normalize Nones for convenience
        title = title or "Analysis Insights"
        notes_markdown = notes_markdown or ""

        return self.run(
            title=title,
            notes_markdown=notes_markdown,
            metadata=metadata,
            index=index,
        )

    # your existing run(...) unchanged
    def run(self, title: str = "Analysis Insights", notes_markdown: str = "", metadata: dict | None = None, index: bool = False):

        k = next_chunk_id_counter(sandbox=self.sandbox)

        exporter = ExportWriter(
            sandbox=self.sandbox,
            patient_id=PATIENT_ID,
            session_type=SESSION_TYPE,
            session_date=SESSION_DATE
        )

        md_name   = f"insights_chunk_{k}.md"
        json_name = f"insights_chunk_{k}.json"

        ts = datetime.utcnow().isoformat() + "Z"
        md = f"""## {title} — Chunk {k}
_Time:_ {ts}

{notes_markdown.strip()}
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

        md_paths   = exporter.write_text(k, md_name, md)
        json_paths = exporter.write_text(k, json_name, json.dumps(json_obj, indent=2))

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
