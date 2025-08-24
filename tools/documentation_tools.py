from __future__ import annotations
import json
from smolagents import Tool  # or from smolagents.tools import Tool
from datetime import datetime

from src.utils.export_writer import ExportWriter
from src.utils.config import PATIENT_ID, SESSION_TYPE, SESSION_DATE
from src.utils.chunk_ids import next_chunk_id_counter  # runtime-safe (host/sandbox aware)


class RetrieveMetadata(Tool):
    name = "RetrieveMetadata"
    description = """Search the dataset psych_metadata for relevant information RetrieveMetadata(query="field types", k=5)"""
    inputs = {
        "query": {"type": "string", "description": "What to search for in the psych_metadata"},
        "k": {"type": "integer", "description": "Number of results to return (default: 3)", "nullable": True}
    }
    output_type = "string"
    help_notes = """ RetrieveMetadata(query="field types", k=5) """

    def __init__(self, sandbox=None, metadata_embedder=None):
        super().__init__()
        self.sandbox = sandbox
        self.metadata_embedder = metadata_embedder

    def run(self, query, k=3):

        if not self.metadata_embedder:
            return "Error: Metadata embedder not available"

        results = self.metadata_embedder.search_metadata(query, k)

        if not results:
            return "No relevant metadata found"

        response = "Relevant metadata:\n\n"
        for i, result in enumerate(results, 1):
            response += f"**Result {i}** (similarity: {result['similarity_score']:.3f})\n"
            response += f"{result['content']}\n\n"

        return response

class DocumentLearningInsights(Tool):
    """
    Persist a lightweight per-chunk insight (markdown + json) under the session export tree.
    Also (optionally) index the note for semantic retrieval if a MetadataEmbedder is provided.
    """
    name = "document_learning_insights"
    description = "Persist analyst/agent insights (markdown + json) for the current chunk."
    inputs = {
        "title": {
            "type": "string",
            "description": "Short heading for this insight block.",
            "required": False
        },
        "notes_markdown": {
            "type": "string",
            "description": "Freeform markdown notes for this chunk.",
            "required": True
        },
        "metadata": {
            "type": "object",
            "description": "Optional JSON-safe dict of extra fields (e.g., counts, timings).",
            "required": False
        },
        "index": {
            "type": "boolean",
            "description": "If true, also index this note for retrieval (embeddings).",
            "required": False
        }
    }
    # ✅ smolagents requires this:
    output_type = "object"
    # Optional but nice: schema for the returned object
    output_schema = {
        "type": "object",
        "required": ["chunk_id", "markdown", "json", "message"],
        "properties": {
            "chunk_id": {"type": "integer"},
            "markdown": {
                "type": "object",
                "properties": {"sandbox": {"type": "string"}, "host": {"type": "string"}},
                "required": ["sandbox"]
            },
            "json": {
                "type": "object",
                "properties": {"sandbox": {"type": "string"}, "host": {"type": "string"}},
                "required": ["sandbox"]
            },
            "message": {"type": "string"}
        }
    }

    def __init__(self, sandbox=None, indexer=None):
        """
        sandbox: e2b sandbox (optional)
        indexer: callable to index notes, e.g. metadata_embedder.index_agent_note
                 signature: indexer(chunk_id:int, title:str, notes:str, metadata:dict) -> None
        """
        super().__init__()
        self.sandbox = sandbox
        self.indexer = indexer  # pass MetadataEmbedder.index_agent_note if you want inline indexing

    def run(self, title: str = "Analysis Insights", notes_markdown: str = "", metadata: dict | None = None, index: bool = False):
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

        # 5) Write both files via ExportWriter (directories are auto-created)
        md_paths   = exporter.write_text(k, md_name, md)
        json_paths = exporter.write_text(k, json_name, json.dumps(json_obj, indent=2))

        # 6) Optionally index this note for retrieval (embeddings)
        if index and callable(self.indexer):
            try:
                self.indexer(k, title, notes_markdown, meta)
            except Exception as e:
                # Don't fail the tool if indexing hiccups; just record it in the message
                return {
                    "chunk_id": k,
                    "markdown": md_paths,
                    "json": json_paths,
                    "message": f"Saved insights for chunk {k} (indexing error ignored: {e})"
                }

        return {
            "chunk_id": k,
            "markdown": md_paths,  # {"sandbox": "...", "host": "..."} (host may be absent when running purely in sandbox)
            "json": json_paths,
            "message": f"Saved insights for chunk {k}."
        }

class RetrieveSimilarChunks(Tool):
    name = "RetrieveSimilarChunks"
    description = "Retrieves the most similar past notes based on semantic similarity."
    inputs = {
        "query": {"type": "string", "description": "The query or current goal the agent is working on"},
        "num_results": {"type": "integer", "description": "Number of top similar chunks to return", "optional": True, "nullable": True}
    }
    output_type = "object"  # Returns list of dictionaries


    def __init__(self, sandbox=None):
        super().__init__()
        self.sandbox = sandbox

    def run(self, query, num_results=3):
        """
        Args:
            query (str): The query or current goal the agent is working on.
            num_results (int): Number of top similar chunks to return.

        Returns:
            list of dict: Each item contains { "chunk": int, "notes": str }
        """
        if not self.sandbox:
            return [{"chunk": 0, "notes": "Sandbox not available"}]

        import json
        
        # Simple fallback - just return stored notes without similarity search for now
        try:
            store_data = self.sandbox.files.read("embeddings/agent_notes_store.json").decode()
            agent_store = json.loads(store_data)
            
            # Return first few items limited by num_results
            results = []
            limit = min(num_results, len(agent_store))
            for i in range(limit):
                item = agent_store[i]
                results.append({
                    "chunk": item.get("chunk", i),
                    "notes": item.get("notes", "No notes available")
                })
            
            return results if results else [{"chunk": 0, "notes": "No previous notes found"}]
        except:
            return [{"chunk": 0, "notes": "No previous notes found"}]
