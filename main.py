import asyncio, os, base64
from fastapi import FastAPI, Request
from src.client.telemetry import TelemetryManager
from src.utils.metadata_embedder import MetadataEmbedder
from src.client.agent import ToolFactory, CustomAgent
from src.client.ui.chat import GradioUI as gradio_ui
from src.utils.ollama_utils import check_ollama_server, wait_for_ollama_server, start_ollama_server_background, \
    pull_model
from dotenv import load_dotenv
from src.executors import docker_python_executor

# Load environment variables from .env file
load_dotenv()

# Print environment variables for debugging (remove in production)
print("Environment variables loaded from .env file")

HF_TOKEN = os.getenv('HF_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
LANGFUSE_PUBLIC_KEY = os.getenv('LANGFUSE_PUBLIC_KEY')
LANGFUSE_SECRET_KEY = os.getenv('LANGFUSE_SECRET_KEY')
LANGFUSE_AUTH = base64.b64encode(f"{LANGFUSE_PUBLIC_KEY or ''}:{LANGFUSE_SECRET_KEY or ''}".encode()).decode()

# Get API key from host env
openai_api_key = os.getenv("OPENAI_API_KEY")

# Get Ollama host from environment (default to localhost if not set)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")

# Global memory (replace these with a controlled registry in production / CA via the below 'with open' etc..)
global agent, chat_interface, metadata_embedder


# Check if Docker is available for agent executor
def _has_docker_access() -> bool:
    # True if a socket/host is present; SELinux perms are checked during actual connect
    if os.environ.get("DOCKER_HOST"):
        return True
    return os.path.exists("/var/run/docker.sock")


# In your main function:
def main():
    # No need for E2B sandbox - files are now local in Docker container

    # Ensure required directories exist
    os.makedirs("data", exist_ok=True)
    os.makedirs("embeddings", exist_ok=True)
    os.makedirs("states", exist_ok=True)

    # Verify environment variables are set
    print(f"OPENAI_API_KEY is set: {'✅' if openai_api_key else '❌'}")
    print(f"HF_TOKEN is set: {'✅' if HF_TOKEN else '❌'}")
    print(f"LANGFUSE keys set: {'✅' if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY else '❌'}")
    print(f"Using Ollama host: {OLLAMA_HOST}")

    # Initialize metadata embedder and embed metadata file
    print("📚 Setting up metadata embeddings...")
    metadata_embedder = MetadataEmbedder(sandbox=None)  # No sandbox needed for local execution
    result = metadata_embedder.embed_metadata_file("./src/data/metadata/turtle_games_dataset_metadata.md")
    print(f"Metadata embedding result: {result}")

    # Create agent, tool factory and tools
    print("🛠️ Creating tools...")
    tool_factory = ToolFactory(sandbox=None, metadata_embedder=metadata_embedder)  # No sandbox needed
    tools = tool_factory.create_all_tools()

    # Embed tool help notes
    print("📖 Embedding tool help notes...")
    help_result = metadata_embedder.embed_tool_help_notes(tools)
    print(f"Tool help embedding result: {help_result}")

    # Try to init Docker-backed executor for the agent
    python_executor = docker_python_executor
    want_docker = os.getenv("USE_DOCKER_EXECUTOR", "false").lower() == "true"

    if want_docker and _has_docker_access():
        try:
            # Import here to avoid errors if Docker is not available
            from src.executors.docker_python_executor import DockerPythonExecutor, DockerSandboxConfig

            print("🐳 Initializing Docker-backed Python executor...")
            DockerSandboxConfig(
                image="python:3.12-slim",
                container_name="agent-exec-1",
                workdir="/workspace",
                user="nobody",
                env={
                    "HF_TOKEN": os.getenv("HF_TOKEN", ""),
                    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                },
                volumes={
                    os.path.abspath("./src/data"): {"bind": "/workspace/data", "mode": "ro"},
                    os.path.abspath("./states"): {"bind": "/workspace/states", "mode": "rw"},
                    os.path.abspath("./embeddings"): {"bind": "/workspace/embeddings", "mode": "rw"},
                },
                mem_limit="1g",
                cpu_quota=100000,
                pids_limit=256,
                security_opt=("no-new-privileges",),
                cap_drop=("ALL",),
                read_only=False,
                manage_container=True,
                install_cmd="python -m pip install --upgrade pip && pip install --no-cache-dir pandas numpy matplotlib seaborn smolagents datetime json pathlib hashlib re"
            )

            print("✅ Docker-backed executor ready.")
        except Exception as e:
            print(f"⚠️ Docker executor unavailable ({type(e).__name__}: {e}). Falling back to local execution.")
            python_executor = None
    else:
        print("ℹ️ Docker executor disabled or socket not present. Using local execution.")

    # Check if we should use the host's Ollama server
    use_host_ollama = os.getenv("USE_HOST_OLLAMA", "").lower() == "true"

    if use_host_ollama:
        print(f"🔌 Using host's Ollama server at {OLLAMA_HOST}:11434")
        ollama_process = None
        if not wait_for_ollama_server(host=OLLAMA_HOST):
            print(f"❌ Cannot connect to Ollama server at {OLLAMA_HOST}:11434. Please ensure it's running.")
            return
    else:
        # Only start Ollama server if not using host's
        print("🚀 Starting Ollama server...")
        ollama_process = start_ollama_server_background()
        if not wait_for_ollama_server():
            print("❌ Failed to start Ollama server. Exiting.")
            if ollama_process:
                ollama_process.terminate()
            return

    # Pull model (this will use the configured host)
    pull_model("gpt-oss:20b", host=OLLAMA_HOST)

    # Create agent with context manager support for cleanup
    agent = CustomAgent(
        tools=tools,
        sandbox=None,  # No sandbox needed for local execution
        metadata_embedder=metadata_embedder,
        model_id="gpt-oss:20b",
        ollama_host=OLLAMA_HOST,  # Pass the Ollama host to the agent
        # python_executor=docker_python_executor,  # Pass the executor (which might be None)
    )
    agent.telemetry = TelemetryManager()

    # Initialize chat interface using your custom GradioUI
    print("🌐 Initializing Gradio interface...")
    ui = gradio_ui(agent)  # Pass the CustomAgent instance here!

    print("✅ Application startup complete!")

    try:
        # Launch the interface
        ui.launch(share=False, server_port=7860, server_name="0.0.0.0")
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal...")
    finally:
        # Cleanup agent resources
        print("🧹 Cleaning up agent resources...")
        agent.cleanup()
        if ollama_process:
            ollama_process.terminate()
        print("👋 Goodbye!")


if __name__ == "__main__":
    main()
