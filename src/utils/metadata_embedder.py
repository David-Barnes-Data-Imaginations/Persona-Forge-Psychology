import numpy as np
from typing import Callable
import requests  # add for Ollama embeddings
from src.states.paths import SBX_DATA_DIR
import os, json, hashlib, time
from dataclasses import dataclass
from typing import Optional, Iterable, Tuple, List, Dict, Any
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # Handle absence gracefully

from dotenv import load_dotenv
load_dotenv()

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

@dataclass
class StorePaths:
    # where the embedder keeps its caches/stores
    embeddings_dir: str = "embeddings"
    metadata_store_file: str = "embeddings/metadata_store.json"  # vector store (toy)
    index_file: str = "embeddings/metadata_index.json"           # file → hash & chunks

class FS:
    """Abstract FS that can be backed by e2b sandbox or local disk."""
    def __init__(self, sandbox=None):
        self.sandbox = sandbox

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        if self.sandbox:
            blob = self.sandbox.files.read(path)
            return blob.decode(encoding) if isinstance(blob, (bytes, bytearray)) else blob
        with open(path, "r", encoding=encoding) as f:
            return f.read()

    def read_bytes(self, path: str) -> bytes:
        if self.sandbox:
            blob = self.sandbox.files.read(path)
            return blob if isinstance(blob, (bytes, bytearray)) else bytes(blob, "utf-8")
        with open(path, "rb") as f:
            return f.read()

    def write_text(self, path: str, text: str, encoding: str = "utf-8") -> None:
        if self.sandbox:
            # ensure parent exists
            parent = os.path.dirname(path)
            try:
                self.sandbox.files.mkdir(parent)
            except Exception:
                pass
            self.sandbox.files.write(path, text.encode(encoding))
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(text)

    def exists(self, path: str) -> bool:
        if self.sandbox:
            try:
                self.sandbox.files.read(path)
                return True
            except Exception:
                return False
        return os.path.exists(path)

    def list_dir(self, path: str) -> List[Dict[str, Any]]:
        """Return entries: {name, is_dir} (sandbox & local)."""
        out: List[Dict[str, Any]] = []
        if self.sandbox:
            try:
                for e in self.sandbox.files.list(path):
                    out.append({"name": e["name"], "is_dir": e.get("is_dir", False)})
            except Exception:
                pass
            return out
        try:
            for name in os.listdir(path):
                full = os.path.join(path, name)
                out.append({"name": name, "is_dir": os.path.isdir(full)})
        except FileNotFoundError:
            pass
        return out


class MetadataEmbedder:
    """
    Smart embedder:
      - ALWAYS dirs: re-embed every run (patient_raw_data)
      - ONCE dirs  : embed only if store missing (or refresh=True)
      - EXCLUDE    : skip
      - Content-hash de-dupe: unchanged files are not re-embedded
    """
    def __init__(self, sandbox=None, store: Optional[StorePaths] = None):
        self.fs = FS(sandbox)
        self.store = store or StorePaths()
        self._store_data: List[Dict[str, Any]] = []  # naïve vector store
        self._index: Dict[str, Dict[str, Any]] = {}  # path -> {sha256, chunks, updated_at}

        # Embedding backends
        self.use_openai = os.getenv("USE_OPENAI_EMBEDDINGS", "false").lower() == "true"
        self.use_ollama_embed = os.getenv("USE_OLLAMA_EMBEDDINGS", "false").lower() == "false"

        # OpenAI init (opt-in)
        self.openai_client = None
        if self.use_openai:
            if OpenAI is None:
                raise RuntimeError("USE_OPENAI_EMBEDDINGS=true but the 'openai' package is not installed.")
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise RuntimeError("USE_OPENAI_EMBEDDINGS=true but OPENAI_API_KEY is missing.")
            self.openai_client = OpenAI(api_key=openai_api_key)

        # Ollama settings (opt-in)
        self.ollama_host = os.getenv("OLLAMA_HOST", "localhost")
        self.ollama_port = int(os.getenv("OLLAMA_PORT", "11434"))
        self.ollama_embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

        # Choose embedding function by precedence: OpenAI -> Ollama -> Local
        if self.openai_client:
            self._embed_fn: Callable[[str], list[float]] = self._embed_with_openai
        elif self.use_ollama_embed:
            self._embed_fn = self._embed_with_ollama
        else:
            self._embed_fn = self._embed_locally  # deterministic local fallback

        self.metadata_store_path = f"{SBX_DATA_DIR}/embeddings/metadata_store.json" if self.sandbox else "embeddings/metadata_store.json"
        self.agent_notes_store_path = f"{SBX_DATA_DIR}/embeddings/agent_notes_store.json" if self.sandbox else "embeddings/agent_notes_store.json"

        self.metadata_store = []
        self.agent_notes_store = []

        # -------- public API --------
        def embed_many(
                self,
                *,
                always: Iterable[str] = (),
                once: Iterable[str] = (),
                exclude: Iterable[str] = (),
                refresh: bool = False,
        ) -> str:
            """High-level driver for your main.py"""
            self._load_stores()

            exclude_set = {os.path.abspath(p) for p in exclude}

            # 1) always re-embed (patient_raw_data)
            total_chunks = 0
            for base in always:
                total_chunks += self._embed_dir(base, exclude_set=exclude_set, mode="always", refresh=True)

            # 2) embed-once dirs (psych_metadata)
            for base in once:
                total_chunks += self._embed_dir(base, exclude_set=exclude_set, mode="once", refresh=refresh)

            self._save_stores()
            return f"Embedded {total_chunks} chunks (always={list(always)}, once={list(once)}, refresh={refresh})"

    # -------- internals --------
    def _load_stores(self):
        # metadata_store
        if self.fs.exists(self.store.metadata_store_file):
            try:
                text = self.fs.read_text(self.store.metadata_store_file)
                self._store_data = json.loads(text)
            except Exception:
                self._store_data = []
        else:
            self._store_data = []

        # index
        if self.fs.exists(self.store.index_file):
            try:
                text = self.fs.read_text(self.store.index_file)
                self._index = json.loads(text)
            except Exception:
                self._index = {}
        else:
            self._index = {}

    def _save_stores(self):
        os.makedirs(self.store.embeddings_dir, exist_ok=True)
        self.fs.write_text(self.store.metadata_store_file, json.dumps(self._store_data, indent=2))
        self.fs.write_text(self.store.index_file, json.dumps(self._index, indent=2))

    def _should_skip(self, abs_path: str, exclude_set: set[str]) -> bool:
        # skip by prefix
        for ex in exclude_set:
            if abs_path.startswith(ex):
                return True
        # ignore hidden/system
        name = os.path.basename(abs_path)
        return name.startswith(".") or name.lower() in {"thumbs.db", "__pycache__"}

    def _iter_files(self, base_dir: str) -> Iterable[str]:
        base = os.path.abspath(base_dir)
        for root, dirs, files in os.walk(base):
            # prune embeddings/insights if someone passed a parent folder
            dirs[:] = [d for d in dirs if d not in {"embeddings", "insights", "__pycache__"}]
            for fn in files:
                yield os.path.join(root, fn)

    def _embed_dir(self, base_dir: str, *, exclude_set: set[str], mode: str, refresh: bool) -> int:
        """
        mode='always'  -> always re-embed files in base_dir
        mode='once'    -> embed only if not present in index (unless refresh=True)
        """
        base_dir = os.path.abspath(base_dir)
        if not os.path.isdir(base_dir):
            return 0

        chunks_written = 0
        for fpath in self._iter_files(base_dir):
            if self._should_skip(os.path.abspath(fpath), exclude_set):
                continue

            # only embed certain file types (md, json, yaml, txt)
            if not fpath.lower().endswith((".md", ".json", ".yaml", ".yml", ".txt")):
                continue

            rel = os.path.relpath(fpath, start=os.path.abspath("."))  # relative to repo root
            b = open(fpath, "rb").read()
            digest = _sha256(b)

            idx = self._index.get(rel)
            if mode == "once" and not refresh and idx and idx.get("sha256") == digest:
                # unchanged → skip
                continue

            text = b.decode("utf-8", errors="ignore")
            chunks = self._chunk(text)
            vectors = [self._embed(c) for c in chunks]

            # append to store (very naïve vector store)
            for i, (c, v) in enumerate(zip(chunks, vectors)):
                self._store_data.append({
                    "type": "metadata",
                    "source": rel,
                    "chunk_id": i,
                    "content": c,
                    "embedding": v,
                    "created_at": "startup"
                })

            # update index
            self._index[rel] = {
                "sha256": digest,
                "chunks": len(chunks),
                "updated_at": int(time.time()),
                "mode": mode,
            }
            chunks_written += len(chunks)

        return chunks_written

    # ------- chunker & embed stub (replace with your API call) -------
    def _chunk(self, text: str, max_chars: int = 1400) -> List[str]:
        parts, buf = [], []
        for para in text.split("\n\n"):
            if sum(len(x) for x in buf) + len(para) + 2 > max_chars:
                parts.append("\n\n".join(buf));
                buf = []
            buf.append(para)
        if buf:
            parts.append("\n\n".join(buf))
        return parts

        """        
        def _embed(self, chunk: str) -> List[float]:
        # TODO: replace with OpenAI/HF embedding call
        # Deterministic toy vector to keep structure intact
        s = int(hashlib.md5(chunk.encode("utf-8")).hexdigest(), 16)
        return [(s >> (i * 8)) % 997 / 997.0 for i in range(10)]
        """

    def _embed_with_openai(self, chunk: str) -> list[float]:
        """Create an embedding using OpenAI"""
        response = self.openai_client.embeddings.create(
            input=chunk,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding

    def _embed_with_ollama(self, chunk: str) -> list[float]:
        """Create an embedding using Ollama's /api/embeddings"""
        url = f"http://{self.ollama_host}:{self.ollama_port}/api/embeddings"
        r = requests.post(url, json={"model": self.ollama_embed_model, "prompt": chunk}, timeout=60)
        r.raise_for_status()
        data = r.json()
        # Ollama returns {"embedding": [floats], ...}
        embedding = data.get("embedding")
        if not embedding:
            raise RuntimeError(f"Ollama embedding response missing 'embedding' field: {data}")
        return embedding
