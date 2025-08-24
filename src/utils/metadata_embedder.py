from src.utils.embeddings import get_embedder_from_env, BaseEmbedder
from dataclasses import dataclass
import os, json, hashlib
from typing import Optional, Dict, List, Any
import argparse
try:
    # If you added the helper earlier, prefer it:
    from src.utils.embeddings import get_embedder_from_env, BaseEmbedder
except Exception:
    # Fallback inline minimal embedders (dummy + OpenAI if available)
    class BaseEmbedder:  # type: ignore
        name: str = "dummy"
        dim: int = 10
        def embed(self, text: str) -> List[float]:
            v = float(len(text) % 10)
            return [v] * self.dim
        def batch_embed(self, texts): return [self.embed(t) for t in texts]

    def get_embedder_from_env():  # type: ignore
        # Try OpenAI only if key exists
        if os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                class OpenAIEmbedder(BaseEmbedder):
                    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
                        self.client = OpenAI(api_key=api_key)
                        self.model = model
                        self.name = f"openai:{model}"
                        self.dim = 1536
                    def embed(self, text: str) -> List[float]:
                        resp = self.client.embeddings.create(model=self.model, input=text)
                        return resp.data[0].embedding
                return OpenAIEmbedder(os.getenv("OPENAI_API_KEY"))
            except Exception:
                pass
        # Dummy fallback
        return BaseEmbedder()

SUPPORTED_EXTS = (".md", ".json", ".yaml", ".yml", ".txt")

def _is_supported_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTS

def _doc_id(source_path: str) -> str:
    return hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:12]

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
      - ALWAYS dirs: re-embed every run (patient_raw_data) when include_corpus=True
      - ONCE dirs  : embed only if store missing (unless refresh=True)
      - EXCLUDE    : insights/, embeddings/, .git, __pycache__
      - De-dupe via content hashing could be added later if needed
    """
    def __init__(self, sandbox=None, embedder: Optional[BaseEmbedder]=None):
        self.sandbox = sandbox
        # ✅ define store paths
        self.metadata_store_path = "embeddings/metadata_store.json"
        self.agent_notes_store_path = "embeddings/agent_notes_store.json"

        # ✅ embedder backend
        self.embedder = embedder or get_embedder_from_env()

        # in‑memory stores
        self.metadata_store = []
        self.agent_notes_store = []

    # -------- store IO --------
    def _check_metadata_exists(self) -> bool:
        """Check if metadata embeddings already exist"""
        if self.sandbox:
            try:
                self.sandbox.files.read(self.metadata_store_path)
                return True
            except Exception:
                return False
        return os.path.exists(self.metadata_store_path)

    def _load_existing_metadata(self) -> bool:
        try:
            if self.sandbox:
                raw = self.sandbox.files.read(self.metadata_store_path)
                store_data = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
            else:
                with open(self.metadata_store_path, "r", encoding="utf-8") as f:
                    store_data = f.read()
            self.metadata_store = json.loads(store_data) or []
            print(f"Loaded existing metadata embeddings: {len(self.metadata_store)} items")
            return True
        except Exception as e:
            print(f"Error loading metadata embeddings: {e}")
            return False

    # -------- main API --------
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
        - Record fields: kind ("metadata"|"corpus"), source, doc_id, chunk_index, content, embedding(+model/dim)
        """
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
                if verbose: print(f"⏭️  Not found or not a directory: {dir_path}")
                continue

            dir_name = os.path.basename(dir_path.rstrip("/"))
            if dir_name in skip_dirs:
                if verbose: print(f"⏭️  Skipping auto-generated dir: {dir_path}")
                continue

            is_corpus = (dir_name == "patient_raw_data")
            if is_corpus and not include_corpus:
                if verbose: print(f"⏭️  Skipping corpus dir (disabled): {dir_path}")
                continue

            if verbose:
                print(f"📚 Creating embeddings from {dir_path} (refresh={refresh})")

            try:
                names = os.listdir(dir_path)
            except Exception as e:
                if verbose: print(f"⚠️  Unable to list {dir_path}: {e}")
                continue

            for fname in names:
                fpath = os.path.join(dir_path, fname)
                if not os.path.isfile(fpath):
                    if verbose: print(f"  ⟶ skip: {fpath} (not a file)")
                    continue
                total_considered += 1

                if not _is_supported_file(fpath):
                    if verbose: print(f"  ⟶ skip: {fpath} (unsupported extension)")
                    continue

                # Read content
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    if verbose: print(f"  ⟶ skip: {fpath} (read error: {e})")
                    continue

                # Chunk, trimming tiny/empty bits
                chunks = self._chunk_markdown(content, max_len=800, min_len=min_chunk_len)
                docid = _doc_id(f"{dir_name}/{fname}")
                added = 0

                for i, chunk in enumerate(chunks):
                    if not chunk or len(chunk.strip()) < min_chunk_len:
                        continue

                    # ✅ This is the 'rec' you were unsure about — append one per chunk
                    rec = {
                        "kind": ("corpus" if is_corpus else "metadata"),
                        "source": f"{dir_name}/{fname}",
                        "doc_id": docid,
                        "chunk_index": i,  # per-document index
                        "content": chunk,
                        "embedding": self._embed_fn(chunk),
                        "embedding_model": getattr(self.embedder, "name", "unknown"),
                        "embedding_dim": getattr(self.embedder, "dim", 0),
                        "created_at": "refresh" if refresh else "startup",
                    }
                    new_records.append(rec)
                    added += 1

                total_embedded += added
                if verbose:
                    print(f"  ✔ embed: {fpath} (chunks={added})")

        if new_records:
            self.metadata_store.extend(new_records)

        # Persist
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

    # -------- helpers --------
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

    def _embed_fn(self, chunk: str) -> List[float]:
        # unified entrypoint to backend
        return self.embedder.embed(chunk)

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
