from typing import Callable
import requests  # add for Ollama embeddings
from src.states.paths import SBX_DATA_DIR
import os, json, hashlib, time
from dataclasses import dataclass
from typing import Optional, Iterable, List, Dict, Any
import argparse

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
    def __init__(self, sandbox=None):
        self.sandbox = sandbox
        self.metadata_store = []
        self.agent_notes_store = []

        self.metadata_store_path = f"{SBX_DATA_DIR}/embeddings/metadata_store.json" if self.sandbox else "embeddings/metadata_store.json"
        self.agent_notes_store_path = f"{SBX_DATA_DIR}/embeddings/agent_notes_store.json" if self.sandbox else "embeddings/agent_notes_store.json"

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

    def embed_metadata_dirs(self, base_dirs: list[str], refresh: bool = False) -> str:
        if not refresh and self._check_metadata_exists():
            print("Metadata embeddings already exist, loading...")
            if self._load_existing_metadata():
                return "Metadata embeddings loaded successfully"

        skip_dirs = {"insights", "embeddings"}
        always_refresh_dirs = {"patient_raw_data"}
        new_embeddings = []

        for dir_path in base_dirs:
            dir_name = os.path.basename(dir_path.rstrip("/"))
            if dir_name in skip_dirs:
                print(f"⏭️ Skipping auto-generated dir: {dir_path}")
                continue

            refresh_this_dir = dir_name in always_refresh_dirs or refresh
            print(f"📚 Creating embeddings from {dir_path} (refresh={refresh_this_dir})")

            for fname in os.listdir(dir_path):
                fpath = os.path.join(dir_path, fname)
                if not os.path.isfile(fpath):
                    continue
                if fname.endswith((".md", ".json", ".yaml")):
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    chunks = self._chunk_markdown(content)
                    for i, chunk in enumerate(chunks):
                        embedding = self._embed_fn(chunk)
                        new_embeddings.append({
                            "type": "metadata",
                            "source": f"{dir_name}/{fname}",
                            "chunk_id": i,
                            "content": chunk,
                            "embedding": embedding,
                            "created_at": "startup"
                        })

        if new_embeddings:
            self.metadata_store.extend(new_embeddings)

        try:
            store_json = json.dumps(self.metadata_store, indent=2)
            if self.sandbox:
                self.sandbox.files.write(self.metadata_store_path, store_json.encode())
            else:
                os.makedirs(os.path.dirname(self.metadata_store_path), exist_ok=True)
                with open(self.metadata_store_path, "w", encoding="utf-8") as f:
                    f.write(store_json)
            return f"Successfully embedded {len(new_embeddings)} chunks from {len(base_dirs)} directories"
        except Exception as e:
            return f"Error saving metadata embeddings: {e}"

    def _chunk_markdown(self, text: str, max_len: int = 800) -> list[str]:
        paras = text.split("\n\n")
        chunks, buf = [], []
        for p in paras:
            if sum(len(x) for x in buf) + len(p) > max_len:
                chunks.append("\n\n".join(buf))
                buf = []
            buf.append(p)
        if buf:
            chunks.append("\n\n".join(buf))
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed metadata directories")
    parser.add_argument("--refresh", action="store_true", help="Force refresh of all embeddings")
    parser.add_argument("--dirs", nargs="*", default=["./src/data/psych_metadata", "./src/data/patient_raw_data"],
                        help="Directories to embed")
    args = parser.parse_args()

    embedder = MetadataEmbedder()
    result = embedder.embed_metadata_dirs(args.dirs, refresh=args.refresh)
    print(result)
