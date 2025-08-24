from __future__ import annotations
from typing import Any, Dict, List, Optional
from smolagents import Tool
import os
import json
from src.utils.embeddings import get_embedder_from_env

# Default store locations (host or sandbox paths are identical strings)
METADATA_STORE_PATH = "embeddings/metadata_store.json"
CORPUS_STORE_PATH   = "embeddings/corpus_store.json"
AGENT_NOTES_PATH    = "embeddings/agent_notes_store.json"

SUPPORTED_KINDS = {"metadata", "corpus", "any"}

def _cosine(a: List[float], b: List[float]) -> float:
    # robust cosine (no numpy dep)
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = sum(a[i] * a[i] for i in range(n)) ** 0.5
    nb = sum(b[i] * b[i] for i in range(n)) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

def _dummy_embed(text: str) -> List[float]:
    """
    Matches the current MetadataEmbedder._embed_fn behavior:
    a 10-dim vector of (len(text) % 10).
    Used for testing and note real metadata.
    """
    v = float(len(text) % 10)
    return [v] * 10

def _read_json_local(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None

class SearchMetadataChunks(Tool):
    """
    Semantic search across metadata/corpus/agent notes embeddings.

    Inputs:
      - query (str): search text
      - top_k (int): number of results (default 5)
      - kind (str): "metadata" | "corpus" | "any" (default "metadata")
      - include_notes (bool): also search agent_notes_store.json (default True)
      - min_score (float): filter low scores (default 0.0)
      - include_content (bool): return full content (default False; else preview)
      - preview_chars (int): length of preview if include_content=False (default 240)

    Output: {"results":[{score, kind, source, doc_id, chunk_index, preview|content}]}
    """
    name = "search_metadata_chunks"
    description = "Search vectorized metadata/corpus/agent notes and return the most similar chunks."
    inputs = {
        "query": {"type": "string", "description": "Search text", "required": True, "nullable": True},
        "top_k": {"type": "integer", "description": "Number of hits", "required": False, "nullable": True},
        "kind":  {"type": "string",  "description": "metadata|corpus|any", "required": False, "nullable": True},
        "include_notes": {"type": "boolean", "description": "Search agent notes too", "required": False, "nullable": False},
        "min_score": {"type": "number", "description": "Score threshold 0..1", "required": False, "nullable": True},
        "include_content": {"type": "boolean", "description": "Return full content instead of preview", "required": False, "nullable": False},
        "preview_chars": {"type": "integer", "description": "Preview char count", "required": False, "nullable": True},
    }
    output_type = "object"

    def __init__(self, sandbox=None):
        super().__init__()
        self.sandbox = sandbox

    # ---- IO helpers ----
    def _sbx_read(self, path: str) -> Optional[str]:
        if not self.sandbox:
            return _read_json_local(path)
        try:
            blob = self.sandbox.files.read(path)
            return blob.decode() if isinstance(blob, (bytes, bytearray)) else str(blob)
        except Exception:
            return None

    def _load_store(self, path: str) -> List[Dict[str, Any]]:
        raw = self._sbx_read(path)
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            # Some stores might be a dict wrapper later; handle gracefully
            if isinstance(data, dict) and "items" in data:
                return data["items"]
        except Exception:
            pass
        return []

    # ---- main ----
    def run(
        self,
        query: str,
        top_k: int = 5,
        kind: str = "metadata",
        include_notes: bool = True,
        min_score: float = 0.0,
        include_content: bool = False,
        preview_chars: int = 240,
    ):
        embedder = get_embedder_from_env()
        qv = embedder.embed(query)
        kind = (kind or "metadata").lower()
        if kind not in SUPPORTED_KINDS:
            kind = "metadata"


        # Load stores
        results_pool: List[Dict[str, Any]] = []
        if kind in ("metadata", "any"):
            results_pool.extend(self._load_store(METADATA_STORE_PATH))
        if kind in ("corpus", "any"):
            results_pool.extend(self._load_store(CORPUS_STORE_PATH))
        if include_notes:
            # Agent notes may not have vectors; degrade gracefully
            notes = self._load_store(AGENT_NOTES_PATH)
            for n in notes:
                if "content" not in n and "notes" in n:
                    n = {
                        "kind": "notes",
                        "source": "agent_notes_store.json",
                        "doc_id": n.get("doc_id") or "notes",
                        "chunk_index": n.get("chunk") or 0,
                        "content": n.get("notes", ""),
                        "embedding": n.get("embedding") or _dummy_embed(n.get("notes", "")),
                        "created_at": n.get("created_at", "unknown"),
                    }
                results_pool.append(n)

        if not results_pool:
            return {"results": [], "info": "No stores found or empty."}

        embedder = get_embedder_from_env()
        qv = embedder.embed(query)

        store_models = set()
        for rec in results_pool:
            m = rec.get("embedding_model")
            if m: store_models.add(m)

        info = None
        if store_models and (getattr(embedder, "name", None) not in store_models):
            info = f"Query embedder {getattr(embedder, 'name', '?')} differs from store models {sorted(store_models)}; scores may be less comparable."

        # Score
        scored: List[Dict[str, Any]] = []
        for rec in results_pool:
            emb = rec.get("embedding")
            if not isinstance(emb, list) or not emb:
                # fallback: embed content on the fly
                emb = _dummy_embed(rec.get("content", ""))
            score = _cosine(qv, emb)
            if score >= min_score:
                kind_out = rec.get("kind", "metadata")
                source = rec.get("source", "")
                doc_id = rec.get("doc_id") or ""
                idx = rec.get("chunk_index") if "chunk_index" in rec else rec.get("chunk_id", 0)
                content = rec.get("content", "")
                out = {
                    "score": round(float(score), 4),
                    "kind": kind_out,
                    "source": source,
                    "doc_id": doc_id,
                    "chunk_index": idx,
                }
                if include_content:
                    out["content"] = content
                else:
                    preview = content[:preview_chars].replace("\n", " ")
                    out["preview"] = preview + ("…" if len(content) > preview_chars else "")
                scored.append(out)

        scored.sort(key=lambda x: x["score"], reverse=True)
        out = {"results": scored[: max(1, int(top_k))]}
        if info: out["info"] = info
        return out
