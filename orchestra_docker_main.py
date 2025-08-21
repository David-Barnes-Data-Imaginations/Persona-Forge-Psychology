# HALF FINISHED ORCHESTRA VERSION THAT RUNS FROM A DOCKER CONTAINER
# TO BE FINISHED LATER
import asyncio, os, base64
# Python
from src.executors.docker_python_executor import DockerPythonExecutor, DockerSandboxConfig
from src.client.telemetry import TelemetryManager
from src.utils.metadata_embedder import MetadataEmbedder
from src.client.agent import ToolFactory, CustomAgent
from src.client.ui.chat import GradioUI as gradio_ui
from src.utils.ollama_utils import check_ollama_server, wait_for_ollama_server, start_ollama_server_background, pull_model

HF_TOKEN = os.getenv('HF_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
LANGFUSE_PUBLIC_KEY= os.getenv('LANGFUSE_PUBLIC_KEY')
LANGFUSE_SECRET_KEY= os.getenv('LANGFUSE_SECRET_KEY')
LANGFUSE_AUTH=base64.b64encode(f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()).decode()

openai_api_key = os.getenv("OPENAI_API_KEY")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")

global agent, chat_interface, metadata_embedder

def _has_docker_access() -> bool:
    # True if a socket/host is present; SELinux perms are checked during actual connect
    if os.environ.get("DOCKER_HOST"):
        return True
    return os.path.exists("/var/run/docker.sock")

def _ensure_paths():
    # Create app-local dirs
    os.makedirs("/app/src/data", exist_ok=True)
    os.makedirs("/app/states", exist_ok=True)
    os.makedirs("/app/embeddings", exist_ok=True)

    # Back-compat: old code expects /data and /states absolute paths
    try:
        if not os.path.exists("/data"):
            os.symlink("/app/src/data", "/data")
    except FileExistsError:
        pass
    try:
        if not os.path.exists("/states"):
            os.symlink("/app/states", "/states")
    except FileExistsError:
        pass

def main():
    os.makedirs("data", exist_ok=True)
    os.makedirs("embeddings", exist_ok=True)
    os.makedirs("states", exist_ok=True)

    print(f"OPENAI_API_KEY is set: {'✅' if openai_api_key else '❌'}")
    print(f"HF_TOKEN is set: {'✅' if HF_TOKEN else '❌'}")
    print(f"LANGFUSE keys set: {'✅' if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY else '❌'}")
    print(f"Using Ollama host: {OLLAMA_HOST}")

    print("📚 Setting up psych_metadata embeddings...")
    metadata_embedder = MetadataEmbedder(sandbox=None)
    result = metadata_embedder.embed_metadata_file("./src/data/psych_metadata/turtle_games_dataset_metadata.md")
    print(f"Metadata embedding result: {result}")

    print("🛠️ Creating tools...")
    tool_factory = ToolFactory(sandbox=None, metadata_embedder=metadata_embedder)
    tools = tool_factory.create_all_tools()

    print("📖 Embedding tool help notes...")
    help_result = metadata_embedder.embed_tool_help_notes(tools)
    print(f"Tool help embedding result: {help_result}")

    # Try to init Docker-backed executor, but fall back on any error (including SELinux PermissionError)
    python_executor = None
    want_docker = os.getenv("USE_DOCKER_EXECUTOR", "true").lower() == "true"
    if want_docker and _has_docker_access():
        try:
            print("Initializing Docker-backed Python executor...")
            python_executor = DockerPythonExecutor(
                DockerSandboxConfig(
                    image="python:3.13-slim",
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
                    install_cmd="python -m pip install --upgrade pip && pip install --no-cache-dir pandas numpy matplotlib seaborn scikit-learn sqlalchemy plotly",
                )
            )
            print("✅ Docker-backed executor ready.")
        except Exception as e:
            print(f"⚠️ Docker executor unavailable ({type(e).__name__}: {e}). Falling back to local execution.")
            python_executor = None
    else:
        print("ℹ️ Docker executor disabled or socket not present. Using local execution.")

    # --- Start of new, simplified Ollama connection logic ---
    print(f"🔌 Connecting to Ollama server at {OLLAMA_HOST}:11434")
    ollama_process = None  # We are not managing the process from this container
    if not wait_for_ollama_server(host=OLLAMA_HOST):
        print(f"❌ Cannot connect to Ollama server at {OLLAMA_HOST}:11434. Please ensure it is running and reachable.")
        return
    # --- End of new logic ---

    pull_model("gpt-oss:20b", host=OLLAMA_HOST)

    agent1 = CustomAgent(
        tools=tools,
        sandbox=None,
        metadata_embedder=metadata_embedder,
        model_id="gpt-oss:20b",
        ollama_host=OLLAMA_HOST,
    )
    agent1.telemetry = TelemetryManager()

    print("🌐 Initializing Gradio interface...")
    ui = gradio_ui(agent1)
    print("✅ Application startup complete!")

    try:
        ui.launch(share=False, server_port=7860, server_name="0.0.0.0")
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal...")
    finally:
        print("🧹 Cleaning up agent resources...")
        agent1.cleanup()
        if ollama_process:
            ollama_process.terminate()
        print("👋 Goodbye!")


if __name__ == "__main__":
    main()