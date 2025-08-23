# src/utils/embeddings.py
from __future__ import annotations
import os, json, requests
from typing import List, Sequence, Optional

class BaseEmbedder:
    name: str = "dummy"
    dim: int = 10

    def embed(self, text: str) -> List[float]:
        v = float(len(text) % 10)
        return [v] * self.dim

    def batch_embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]

class OllamaEmbedder(BaseEmbedder):
    """
    Uses Ollama local embeddings API.
    Models to try: "nomic-embed-text", "snowflake-arctic-embed", "mxbai-embed-large"
    """
    def __init__(self, host: str = "localhost", model: str = "nomic-embed-text", timeout: int = 45):
        self.host = host
        self.model = model
        self.url = f"http://{host}:11434/api/embeddings"
        self.timeout = timeout
        self.name = f"ollama:{model}"
        # we don’t know dim until first call; leave as None then set
        self.dim = 0

    def _call(self, text: str) -> List[float]:
        payload = {"model": self.model, "prompt": text}
        r = requests.post(self.url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        vec = data.get("embedding") or data.get("embeddings") or []
        if not isinstance(vec, list) or not vec:
            raise RuntimeError(f"Ollama returned no embedding: {data}")
        if not self.dim:
            self.dim = len(vec)
        return vec

    def embed(self, text: str) -> List[float]:
        return self._call(text)

    def batch_embed(self, texts: Sequence[str]) -> List[List[float]]:
        # simple loop; Ollama supports one text at a time on most builds
        return [self._call(t) for t in texts]

class OpenAIEmbedder(BaseEmbedder):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.name = f"openai:{model}"
        self.dim = 1536  # text-embedding-3-small

    def embed(self, text: str) -> List[float]:
        resp = self.client.embeddings.create(model=self.model, input=text)
        return resp.data[0].embedding

    def batch_embed(self, texts: Sequence[str]) -> List[List[float]]:
        resp = self.client.embeddings.create(model=self.model, input=list(texts))
        return [d.embedding for d in resp.data]

def get_embedder_from_env() -> BaseEmbedder:
    # Prefer Ollama if explicitly enabled
    if os.getenv("USE_OLLAMA_EMBEDDINGS", "false").lower() == "true":
        host = os.getenv("OLLAMA_HOST", "localhost")
        model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        return OllamaEmbedder(host=host, model=model)
    # OpenAI if key present
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIEmbedder(api_key=os.getenv("OPENAI_API_KEY"))
    # Fallback dummy
    return BaseEmbedder()
