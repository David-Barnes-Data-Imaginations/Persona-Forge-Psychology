import asyncio, os, base64
from dotenv import load_dotenv
load_dotenv()
from e2b_code_interpreter import Sandbox
from src.client.telemetry import TelemetryManager
from src.utils.metadata_embedder import MetadataEmbedder
from src.client.agent import ToolFactory, CustomAgent
from src.client.ui.chat import GradioUI as gradio_ui
from src.utils.ollama_utils import wait_for_ollama_server, start_ollama_server_background, pull_model

# Load .env early so both PyCharm and CLI see the same env vars
  # <-- ensure .env gets loaded

HF_TOKEN = os.getenv('HF_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
LANGFUSE_PUBLIC_KEY= os.getenv('LANGFUSE_PUBLIC_KEY')
LANGFUSE_SECRET_KEY= os.getenv('LANGFUSE_SECRET_KEY')
LANGFUSE_AUTH=base64.b64encode(f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()).decode()

# Feature flags / toggles
USE_E2B = os.getenv("USE_E2B", "false").lower() == "true"  # default off unless explicitly enabled

# Get API key from host env
openai_api_key = os.getenv("OPENAI_API_KEY")

# Temporarily disable telemetry to focus on tool parsing issues
# os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://cloud.langfuse.com" # EU data region
# os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"

# Global memory (replace these with a controlled registry in production / CA via the below 'with open' etc..)
global sandbox, agent, chat_interface, metadata_embedder
import e2b_code_interpreter

# In your main function:
def main():

    # Create E2B sandbox only if explicitly enabled and API key is present
    sandbox = None
    if USE_E2B:
        e2b_api_key = os.getenv("E2B_API_KEY")
        if not e2b_api_key:
            raise RuntimeError("USE_E2B=true but E2B_API_KEY is missing. Set it in your environment or .env")
        sandbox = Sandbox(api_key=e2b_api_key)
        # Upload requirements.txt and install dependencies here to give time for upload before calling install
        with open("requirements.txt", "rb") as f:
            sandbox.files.write("requirements.txt", f)
        # Upload dataset to sandbox
        with open("./src/data/tg_database.db", "rb") as f:
            dataset_path_in_sandbox = sandbox.files.write("/data/tg_database.db", f)
        # Upload dataset to sandbox

    # Initialize metadata embedder and embed metadata file
    print("📚 Setting up metadata embeddings...")
    metadata_embedder = MetadataEmbedder(sandbox)

    # Use sandbox path if E2B is enabled, otherwise local path
    metadata_path = "/data/metadata/turtle_games_dataset_metadata.md" if USE_E2B else "./src/data/metadata/turtle_games_dataset_metadata.md"
    result = metadata_embedder.embed_metadata_file(metadata_path)
    print(f"Metadata embedding result: {result}")

    # Create agent, tool factory and tools
    print("🛠️ Creating tools...")
    tool_factory = ToolFactory(sandbox, metadata_embedder)
    tools = tool_factory.create_all_tools()

    # Embed tool help notes
    print("📖 Embedding tool help notes...")
    help_result = metadata_embedder.embed_tool_help_notes(tools)
    print(f"Tool help embedding result: {help_result}")

    # Start Ollama server and pull model
    ollama_process = start_ollama_server_background()
    if not wait_for_ollama_server():
        print("❌ Failed to start Ollama server. Exiting.")
        if ollama_process:
            ollama_process.terminate()
        return
    pull_model("gpt-oss:20b", host="localhost", port=11434)

    # Create agent with context manager support for cleanup
    agent = CustomAgent(
        tools=tools,
        sandbox=sandbox,
        metadata_embedder=metadata_embedder,
        model_id="gpt-oss:20b",
    )
    agent.telemetry = TelemetryManager()

    # Initialize chat interface using your custom GradioUI
    print("🌐 Initializing Gradio interface...")
    ui = gradio_ui(agent)  # Pass the CustomAgent instance here!

    print("✅ Application startup complete!")

    try:
        # Launch the interface
        ui.launch(share=False, server_port=7860)
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