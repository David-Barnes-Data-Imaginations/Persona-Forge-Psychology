import os
import json
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables at module level
load_dotenv()


class MetadataEmbedder:
    """Class for embedding metadata and storing them locally"""

    def __init__(self, sandbox=None):
        self.sandbox = sandbox  # Keep for backward compatibility but use local files

        # Try multiple approaches to get the API key
        openai_api_key = os.getenv("OPENAI_API_KEY")

        # Debug print - will be removed in production
        if not openai_api_key:
            print("WARNING: No OpenAI API key found in environment!")
            print(f"Current environment keys: {[k for k in os.environ.keys() if not k.startswith('_')]}")

        try:
            self.openai_client = OpenAI(api_key=openai_api_key)
        except Exception as e:
            print(f"Error initializing OpenAI client: {e}")
            print("Creating mock client for development")
            # Create a mock client for development
            self.openai_client = None

        # Separate storage for metadata vs agent notes (using numpy instead of faiss)
        self.metadata_store_path = "embeddings/metadata_store.json"
        self.agent_notes_store_path = "embeddings/agent_notes_store.json"

        # Initialize stores (numpy-based)
        self.metadata_store = []
        self.agent_notes_store = []

    def _check_metadata_exists(self) -> bool:
        """Check if metadata embeddings already exist locally"""
        try:
            # Check if metadata store exists locally
            return os.path.exists(self.metadata_store_path)
        except:
            return False

    def _load_existing_metadata(self):
        """Load existing metadata embeddings"""
        try:
            # Load metadata store from local file
            with open(self.metadata_store_path, 'r') as f:
                self.metadata_store = json.load(f)

            print(f"Loaded existing metadata embeddings: {len(self.metadata_store)} items")
            return True
        except Exception as e:
            print(f"Error loading metadata embeddings: {e}")
            return False

    def embed_metadata_file(self, file_path: str, force_refresh: bool = False) -> str:
        """Embed the metadata markdown file at startup"""

        # Check if already exists and not forcing refresh
        if not force_refresh and self._check_metadata_exists():
            print("Metadata embeddings already exist, loading...")
            if self._load_existing_metadata():
                return "Metadata embeddings loaded successfully"

        # If no OpenAI client is available, return early with a message
        if self.openai_client is None:
            print("⚠️ Skipping metadata embedding - OpenAI client not available")
            return "Metadata embedding skipped - OpenAI client not available"

        print("Creating new metadata embeddings...")

        # Read the metadata file locally
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                metadata_content = f.read()
        except Exception as e:
            return f"Error reading metadata file: {e}"

        # Split into chunks to make the file easier for the llm to read
        chunks = self._chunk_markdown(metadata_content)

        # Create embeddings
        embeddings = []
        for i, chunk in enumerate(chunks):
            try:
                response = self.openai_client.embeddings.create(
                    input=chunk,
                    model="text-embedding-3-small"
                )
                embedding = response.data[0].embedding
                embeddings.append(embedding)

                # Store metadata about this chunk including embedding
                self.metadata_store.append({
                    "type": "metadata",
                    "source": "turtle_games_dataset_metadata.md",
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

        # Save locally (embeddings are now stored in metadata_store)
        try:
            # Ensure embeddings directory exists
            os.makedirs(os.path.dirname(self.metadata_store_path), exist_ok=True)

            # Save metadata store with embeddings
            with open(self.metadata_store_path, 'w') as f:
                json.dump(self.metadata_store, f, indent=2)

            return f"Successfully embedded metadata file: {len(chunks)} chunks created"

        except Exception as e:
            return f"Error saving metadata embeddings: {e}"

    def _chunk_markdown(self, content: str, chunk_size: int = 1000) -> list:
        """Split markdown content into chunks"""
        # Simple chunking by lines - you might want more sophisticated chunking
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

        # If no OpenAI client is available, return a placeholder message
        if self.openai_client is None:
            print("⚠️ Skipping metadata search - OpenAI client not available")
            return [
                {"content": "Metadata search not available - OpenAI client not configured", "similarity_score": 1.0}]

        try:
            # Create query embedding
            response = self.openai_client.embeddings.create(
                input=query,
                model="text-embedding-3-small"
            )
            query_embedding = np.array(response.data[0].embedding)

            # Calculate similarities with all stored embeddings
            similarities = []
            for i, item in enumerate(self.metadata_store):
                if "embedding" in item:
                    stored_embedding = np.array(item["embedding"])

                    # Normalize embeddings
                    norm_query = query_embedding / np.linalg.norm(query_embedding)
                    norm_stored = stored_embedding / np.linalg.norm(stored_embedding)

                    # Calculate cosine similarity
                    similarity = np.dot(norm_query, norm_stored)
                    similarities.append((similarity, i))

            # Sort by similarity and take top k
            similarities.sort(key=lambda x: x[0], reverse=True)
            top_similarities = similarities[:k]

            # Build results
            results = []
            for similarity, idx in top_similarities:
                result = self.metadata_store[idx].copy()
                result['similarity_score'] = float(similarity)
                results.append(result)

            return results

        except Exception as e:
            print(f"Error searching metadata: {e}")
            return []

    def embed_tool_help_notes(self, tools: list) -> str:
        """
        Embeds the help_notes field from each tool into the metadata index.

        Args:
            tools (list): List of tool instances

        Returns:
            str: Success message with count of embedded help notes
        """
        if not tools:
            return "No tools provided"

        # If no OpenAI client is available, return early with a message
        if self.openai_client is None:
            print("⚠️ Skipping tool help notes embedding - OpenAI client not available")
            return "Tool help notes embedding skipped - OpenAI client not available"

        help_notes_count = 0
        embeddings = []

        for tool in tools:
            if hasattr(tool, "help_notes") and tool.help_notes:
                try:
                    # Create embedding for the help notes
                    response = self.openai_client.embeddings.create(
                        input=tool.help_notes,
                        model="text-embedding-3-small"
                    )
                    embedding = response.data[0].embedding
                    embeddings.append(embedding)

                    # Store metadata about this tool help including embedding
                    self.metadata_store.append({
                        "type": "tool_help",
                        "tool_name": tool.name,
                        "content": tool.help_notes,
                        "embedding": embedding,
                        "created_at": "startup"
                    })
                    help_notes_count += 1

                except Exception as e:
                    print(f"Error embedding help notes for tool {tool.name}: {e}")
                    continue

        if embeddings:
            # Save updated store with embeddings locally
            try:
                # Ensure embeddings directory exists
                os.makedirs(os.path.dirname(self.metadata_store_path), exist_ok=True)

                with open(self.metadata_store_path, 'w') as f:
                    json.dump(self.metadata_store, f, indent=2)

            except Exception as e:
                return f"Error saving tool help embeddings: {e}"

        return f"Successfully embedded help notes for {help_notes_count} tools"
