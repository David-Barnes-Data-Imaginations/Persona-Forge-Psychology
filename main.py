# Python
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

# GPT-OSS Configuration
GPT_OSS_BASE_URL = os.getenv("GPT_OSS_BASE_URL", "http://localhost:8000")
MODEL_ID = os.getenv("MODEL_ID", "gpt-oss-20b")

global agent, chat_interface, metadata_embedder


def create_agent_with_gpt_oss(tools, python_executor=None, use_gpt_oss=True):
    """
    Factory function to create your CustomAgent with GPT-OSS support
    """
    try:
        agent = CustomAgent(
            tools=tools,
            python_executor=python_executor,
            use_gpt_oss=use_gpt_oss,
            gpt_oss_url=GPT_OSS_BASE_URL,
            gpt_oss_model=MODEL_ID,
            # Add any other kwargs you need
        )
        print(f"✅ Agent created successfully with GPT-OSS: {use_gpt_oss}")
        return agent

    except Exception as e:
        print(f"❌ Failed to create agent with GPT-OSS: {e}")
        if use_gpt_oss:
            print("🔄 Falling back to vLLM configuration...")
            # Fallback to vLLM if GPT-OSS fails
            return CustomAgent(
                tools=tools,
                python_executor=python_executor,
                use_gpt_oss=False,
                model_id=MODEL_ID
            )
        else:
            raise


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

    # Ensure paths exist
    _ensure_paths()

    print(f"OPENAI_API_KEY is set: {'✅' if openai_api_key else '❌'}")
    print(f"HF_TOKEN is set: {'✅' if HF_TOKEN else '❌'}")
    print(f"LANGFUSE keys set: {'✅' if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY else '❌'}")
    print(f"Using OpenAI-compatible base: {GPT_OSS_BASE_URL}")
    print(f"Serving model: {MODEL_ID}")

    print("📚 Setting up metadata embeddings...")
    metadata_embedder = MetadataEmbedder(sandbox=None)
    result = metadata_embedder.embed_metadata_file("./src/data/metadata/turtle_games_dataset_metadata.md")
    print(f"Metadata embedding result: {result}")

    # Check Docker access
    if not _has_docker_access():
        print("⚠️ Docker access not available")

    print("🛠️ Creating tools...")
    tool_factory = ToolFactory(sandbox=None, metadata_embedder=metadata_embedder)
    tools = tool_factory.create_all_tools()

    print("📖 Embedding tool help notes...")
    help_result = metadata_embedder.embed_tool_help_notes(tools)
    print(f"Tool help embedding result: {help_result}")

    # Create Docker executor if available
    python_executor = None
    if _has_docker_access():
        try:
            print("Initializing Docker-backed Python executor...")
            config = DockerSandboxConfig(
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
                    install_cmd="bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh -s -- --yes && \
                    /root/.local/bin/uv pip install -U pip && \
                    /root/.local/bin/uv pip install -r /workspace/agent_requirements.txt || \
                    /root/.local/bin/uv pip install pandas numpy matplotlib seaborn scikit-learn sqlalchemy plotly'",
            )
            python_executor = DockerPythonExecutor(config)
            print("✅ Docker Python executor created")
        except Exception as e:
            print(f"⚠️ Failed to create Docker executor: {e}")

    agent = create_agent_with_gpt_oss(
        tools=tools,
        sandbox=None,
        metadata_embedder=metadata_embedder,
        python_executor=python_executor,
        use_gpt_oss=True  # Set to False to use vLLM instead
    )

 #   agent1.telemetry = TelemetryManager()

    print("🌐 Initializing Gradio interface...")
    chat_interface = gradio_ui(agent=agent)
    print("✅ Application startup complete!")

    try:
        chat_interface.launch(
            server_name="0.0.0.0",
            server_port=7860,
            share=False
        )
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal...")
    finally:
        print("🧹 Cleaning up agent resources...")
        agent.cleanup()
        print("👋 Goodbye!")


if __name__ == "__main__":
    main()