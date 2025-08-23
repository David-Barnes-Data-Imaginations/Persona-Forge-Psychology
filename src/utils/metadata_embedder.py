from typing import Callable
import requests  # add for Ollama embeddings
from src.utils.paths import SBX_DATA_DIR
import os, json, hashlib, time
from dataclasses import dataclass
from typing import Optional, Iterable, List, Dict, Any
import argparse

SUPPORTED_EXTS = (".md", ".json", ".yaml", ".yml", ".txt")

def _is_supported_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTS

def _doc_id(source_path: str) -> str:
    import hashlib
    # stable short id per file
    return hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:12]
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # Handle absence gracefully

from dotenv import load_dotenv
load_dotenv()

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_supported_file(path: str) -> bool:
    return path.lower().endswith(SUPPORTED_EXTS)

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
    def __init__(self, sandbox=None):
        self.sandbox = sandbox
        self.corpus_store = []

        self.metadata_store_path = "embeddings/metadata_store.json"
        self.corpus_store_path = "embeddings/corpus_store.json"
        self.agent_notes_store_path = "embeddings/agent_notes_store.json"
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
        self._embed_with_openai

        """        Choose embedding function by precedence: OpenAI -> Ollama -> Local
                if self.openai_client:
                    self._embed_fn: Callable[[str], list[float]] = self._embed_with_openai
                elif self.use_ollama_embed:
                    self._embed_fn = self._embed_with_ollama
                else:
                    self._embed_fn = self._embed_locally  """

        # -------- public API --------

    def _check_metadata_exists(self) -> bool:
        """Check if metadata embeddings already exist"""
        if self.sandbox:
            try:
                self.sandbox.files.read(self.metadata_store_path)
                return True
            except:
                return False
        return os.path.exists(self.metadata_store_path)

    def _load_existing_metadata(self):
        try:
            if self.sandbox:
                store_data = self.sandbox.files.read(self.metadata_store_path).decode()
            else:
                with open(self.metadata_store_path, "r", encoding="utf-8") as f:
                    store_data = f.read()
            self.metadata_store = json.loads(store_data)
            print(f"Loaded existing metadata embeddings: {len(self.metadata_store)} items")
            return True
        except Exception as e:
            print(f"Error loading metadata embeddings: {e}")
            return False

    def embed_metadata_dirs(
            self,
            base_dirs: list[str],
            refresh: bool = False,
            include_corpus: bool = False,
            verbose: bool = False,
            min_chunk_len: int = 30,
    ) -> str:
        """
        Embed files from one or more directories into a single metadata store.
        - refresh=False: reuse existing store if present
        - include_corpus=False: skip ./patient_raw_data (prevents leakage/confusion)
        - Skips agent-generated dirs like insights/ or embeddings/
        - Adds fields: kind ("metadata" | "corpus"), doc_id, chunk_index (per file)
        """
        # Fast path: reuse cache unless refresh requested
        if not refresh and self._check_metadata_exists():
            if verbose:
                print("ℹ️  Store exists, loading cached metadata embeddings...")
            if self._load_existing_metadata():
                return "Metadata embeddings loaded successfully"

        skip_dirs = {"insights", "embeddings", ".git", "__pycache__"}
        total_considered = 0
        total_embedded = 0
        new_records: list[dict] = []

        for dir_path in base_dirs:
            if not os.path.isdir(dir_path):
                if verbose:
                    print(f"⏭️  Not found or not a directory: {dir_path}")
                continue

            dir_name = os.path.basename(dir_path.rstrip("/"))
            if dir_name in skip_dirs:
                if verbose:
                    print(f"⏭️  Skipping auto-generated dir: {dir_path}")
                continue

            is_corpus = (dir_name == "patient_raw_data")
            if is_corpus and not include_corpus:
                if verbose:
                    print(f"⏭️  Skipping corpus dir (disabled): {dir_path}")
                continue

            if verbose:
                print(f"📚 Creating embeddings from {dir_path} (refresh={refresh})")

            try:
                names = os.listdir(dir_path)
            except Exception as e:
                if verbose:
                    print(f"⚠️  Unable to list {dir_path}: {e}")
                continue

            for fname in names:
                fpath = os.path.join(dir_path, fname)
                if not os.path.isfile(fpath):
                    if verbose:
                        print(f"  ⟶ skip: {fpath} (not a file)")
                    continue
                total_considered += 1

                if not _is_supported_file(fpath):
                    if verbose:
                        print(f"  ⟶ skip: {fpath} (unsupported extension)")
                    continue

                # Read content
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    if verbose:
                        print(f"  ⟶ skip: {fpath} (read error: {e})")
                    continue

                # Chunk, trimming tiny/empty bits
                chunks = self._chunk_markdown(content, max_len=800, min_len=min_chunk_len)
                docid = _doc_id(f"{dir_name}/{fname}")
                added = 0

                for i, chunk in enumerate(chunks):
                    # safety, chunker already filters short ones
                    if not chunk or len(chunk.strip()) < min_chunk_len:
                        continue

                    rec = {
                        "kind": ("corpus" if is_corpus else "metadata"),
                        "source": f"{dir_name}/{fname}",
                        "doc_id": docid,
                        "chunk_index": i,  # per-document index
                        "content": chunk,
                        "embedding": self._embed_fn(chunk),
                        "created_at": "refresh" if refresh else "startup",
                    }
                    new_records.append(rec)
                    added += 1

                total_embedded += added
                if verbose:
                    print(f"  ✔ embed: {fpath} (chunks={added})")

        # Extend and persist
        if new_records:
            self.metadata_store.extend(new_records)

        try:
            os.makedirs(os.path.dirname(self.metadata_store_path), exist_ok=True)
            store_json = json.dumps(self.metadata_store, indent=2)
            if self.sandbox:
                self.sandbox.files.write(self.metadata_store_path, store_json.encode())
            else:
                with open(self.metadata_store_path, "w", encoding="utf-8") as f:
                    f.write(store_json)
            return (
                f"Successfully embedded {total_embedded} chunks from "
                f"{len(base_dirs)} directories (considered {total_considered} files)"
            )
        except Exception as e:
            return f"Error saving metadata embeddings: {e}"

    def _chunk_markdown(self, text: str, max_len: int = 800, min_len: int = 30) -> list[str]:
        """Paragraph-ish chunker. Skips empty/tiny chunks, trims whitespace."""
        paras = [p.strip() for p in text.split("\n\n")]
        chunks, buf = [], []
        acc = 0

        for p in paras:
            if not p or len(p) < min_len:
                continue
            if acc + len(p) > max_len and buf:
                joined = "\n\n".join(buf).strip()
                if len(joined) >= min_len:
                    chunks.append(joined)
                buf, acc = [], 0
            buf.append(p)
            acc += len(p)

        if buf:
            joined = "\n\n".join(buf).strip()
            if len(joined) >= min_len:
                chunks.append(joined)
        return chunks

    def _embed_fn(self, chunk: str):
        return [float(len(chunk) % 10)] * 10  # fake vector

    def _embed_with_openai(self, chunk: str) -> list[float]:
        """Create an embedding using OpenAI"""
        response = self.openai_client.embeddings.create(
            input=chunk,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding

    """    def _embed_with_ollama(self, chunk: str) -> list[float]:
            
            url = f"http://{self.ollama_host}:{self.ollama_port}/api/embeddings"
            r = requests.post(url, json={"model": self.ollama_embed_model, "prompt": chunk}, timeout=60)
            r.raise_for_status()
            data = r.json()
            # Ollama returns {"embedding": [floats], ...}
            embedding = data.get("embedding")
            if not embedding:
                raise RuntimeError(f"Ollama embedding response missing 'embedding' field: {data}")
            return embedding
    """


import argparse
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed metadata directories")
    # Compute repo root: .../<project_root>/src/utils/metadata_embedder.py → parents[2]
    repo_root = Path(__file__).resolve().parents[2]
    default_dirs = [
        str(repo_root / "src" / "data" / "psych_metadata"),
        str(repo_root / "src" / "data" / "patient_raw_data"),
    ]
    parser.add_argument("--refresh", action="store_true", help="Force refresh of all embeddings")
    parser.add_argument("--dirs", nargs="*", default=default_dirs, help="Directories to embed")
    parser.add_argument("--verbose", action="store_true", help="Verbose include/exclude logging")
    args = parser.parse_args()

    embedder = MetadataEmbedder()
    # Shows missing dirs
    for d in args.dirs:
        if not os.path.isdir(d):
            print(f"⏭️  Skipping; not a directory: {d}")
    result = embedder.embed_metadata_dirs(args.dirs, refresh=args.refresh, verbose=args.verbose)
    print(result)
