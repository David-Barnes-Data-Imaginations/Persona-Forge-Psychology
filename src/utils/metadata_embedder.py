import os
import json
import numpy as np
from typing import Callable
import requests  # add for Ollama embeddings

# Optional OpenAI client
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # Handle absence gracefully

from dotenv import load_dotenv
load_dotenv()

class MetadataEmbedder:
    """Class for embedding metadata and storing them in a sandbox"""
    def __init__(self, sandbox=None):
        self.sandbox = sandbox

        # Embedding backends
        self.use_openai = os.getenv("USE_OPENAI_EMBEDDINGS", "false").lower() == "true"
        self.use_ollama = os.getenv("USE_OLLAMA_EMBEDDINGS", "false").lower() == "true"

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
        elif self.use_ollama:
            self._embed_fn = self._embed_with_ollama
        else:
            self._embed_fn = self._embed_locally  # deterministic local fallback

        # Separate storage for metadata vs agent notes
        self.metadata_store_path = "embeddings/metadata_store.json"
        self.agent_notes_store_path = "embeddings/agent_notes_store.json"

        self.metadata_store = []
        self.agent_notes_store = []

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
        """Load existing metadata embeddings"""
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

    def embed_metadata_file(self, file_path: str, force_refresh: bool = False) -> str:
        """Embed the metadata markdown file at startup"""
        if not force_refresh and self._check_metadata_exists():
            print("Metadata embeddings already exist, loading...")
            if self._load_existing_metadata():
                return "Metadata embeddings loaded successfully"

        print("Creating new metadata embeddings...")

        # Read metadata content
        try:
            if self.sandbox:
                metadata_content = self.sandbox.files.read(file_path)
                if isinstance(metadata_content, bytes):
                    metadata_content = metadata_content.decode()
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    metadata_content = f.read()
        except Exception as e:
            return f"Error reading metadata file: {e}"

        chunks = self._chunk_markdown(metadata_content)

        embeddings = []
        for i, chunk in enumerate(chunks):
            try:
                embedding = self._embed_fn(chunk)
                embeddings.append(embedding)
                self.metadata_store.append({
                    "type": "metadata",
                    "source": os.path.basename(file_path),
                    "chunk_id": i,
                    "content": chunk,
                    "embedding": embedding,
                    "created_at": "startup"
                })
            except Exception as e:
                print(f"Error creating embedding for chunk {i}: {e}")
                continue

        if not embeddings:
            return "Error: No embeddings created"

        # Save store (sandbox or local)
        try:
            store_json = json.dumps(self.metadata_store, indent=2)
            if self.sandbox:
                self.sandbox.files.write(self.metadata_store_path, store_json.encode())
            else:
                os.makedirs(os.path.dirname(self.metadata_store_path), exist_ok=True)
                with open(self.metadata_store_path, "w", encoding="utf-8") as f:
                    f.write(store_json)
            return f"Successfully embedded metadata file: {len(chunks)} chunks created"
        except Exception as e:
            return f"Error saving metadata embeddings: {e}"

    def _embed_with_openai(self, text: str) -> list[float]:
        """Create an embedding using OpenAI"""
        response = self.openai_client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding

    def _embed_with_ollama(self, text: str) -> list[float]:
        """Create an embedding using Ollama's /api/embeddings"""
        url = f"http://{self.ollama_host}:{self.ollama_port}/api/embeddings"
        r = requests.post(url, json={"model": self.ollama_embed_model, "prompt": text}, timeout=60)
        r.raise_for_status()
        data = r.json()
        # Ollama returns {"embedding": [floats], ...}
        embedding = data.get("embedding")
        if not embedding:
            raise RuntimeError(f"Ollama embedding response missing 'embedding' field: {data}")
        return embedding

    def _embed_locally(self, text: str, dim: int = 384) -> list[float]:
        """Deterministic local fallback embedding (hash-based)"""
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        vec = rng.standard_normal(dim)
        vec = vec / np.linalg.norm(vec)
        return vec.astype(float).tolist()

    def _chunk_markdown(self, content: str, chunk_size: int = 1000) -> list:
        """Split markdown content into chunks"""
        lines = content.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0

        for line in lines:
            if current_size + len(line) > chunk_size and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_size = len(line)
            else:
                current_chunk.append(line)
                current_size += len(line)

        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        return chunks

    def search_metadata(self, query: str, k: int = 3) -> list:
        """Search metadata embeddings using numpy cosine similarity"""
        if not self.metadata_store:
            return []
        try:
            query_embedding = np.array(self._embed_fn(query))
            similarities = []
            for i, item in enumerate(self.metadata_store):
                if "embedding" in item:
                    stored_embedding = np.array(item["embedding"])
                    norm_query = query_embedding / np.linalg.norm(query_embedding)
                    norm_stored = stored_embedding / np.linalg.norm(stored_embedding)
                    similarity = np.dot(norm_query, norm_stored)
                    similarities.append((similarity, i))
            similarities.sort(key=lambda x: x[0], reverse=True)
            top = similarities[:k]
            results = []
            for sim, idx in top:
                result = self.metadata_store[idx].copy()
                result["similarity_score"] = float(sim)
                results.append(result)
            return results
        except Exception as e:
            print(f"Error searching metadata: {e}")
            return []

    def embed_tool_help_notes(self, tools: list) -> str:
        """Embeds the help_notes field from each tool into the metadata index."""
        if not tools:
            return "No tools provided"

        help_notes_count = 0
        embeddings = []

        for tool in tools:
            if hasattr(tool, "help_notes") and tool.help_notes:
                try:
                    embedding = self._embed_fn(tool.help_notes)
                    embeddings.append(embedding)
                    self.metadata_store.append({
                        "type": "tool_help",
                        "tool_name": getattr(tool, "name", tool.__class__.__name__),
                        "content": tool.help_notes,
                        "embedding": embedding,
                        "created_at": "startup"
                    })
                    help_notes_count += 1
                except Exception as e:
                    print(f"Error embedding help notes for tool {getattr(tool, 'name', tool.__class__.__name__)}: {e}")
                    continue

        if embeddings:
            try:
                store_json = json.dumps(self.metadata_store, indent=2)
                if self.sandbox:
                    self.sandbox.files.write(self.metadata_store_path, store_json.encode())
                else:
                    os.makedirs(os.path.dirname(self.metadata_store_path), exist_ok=True)
                    with open(self.metadata_store_path, "w", encoding="utf-8") as f:
                        f.write(store_json)
            except Exception as e:
                return f"Error saving tool help embeddings: {e}"

        return f"Successfully embedded help notes for {help_notes_count} tools"