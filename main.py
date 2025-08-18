import asyncio, os, base64
from fastapi import FastAPI, Request
from src.client.telemetry import TelemetryManager
from src.utils.metadata_embedder import MetadataEmbedder
from src.client.agent import ToolFactory, CustomAgent
from src.client.ui.chat import GradioUI as gradio_ui
from src.utils.ollama_utils import check_ollama_server, wait_for_ollama_server, start_ollama_server_background, \
    pull_model
from dotenv import load_dotenv

HF_TOKEN = os.getenv('HF_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
LANGFUSE_PUBLIC_KEY = os.getenv('LANGFUSE_PUBLIC_KEY')
LANGFUSE_SECRET_KEY = os.getenv('LANGFUSE_SECRET_KEY')
LANGFUSE_AUTH = base64.b64encode(f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()).decode()

# Get API key from host env
openai_api_key = os.getenv("OPENAI_API_KEY")

# Get Ollama host from environment (default to localhost if not set)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")

# Global memory (replace these with a controlled registry in production / CA via the below 'with open' etc..)
global agent, chat_interface, metadata_embedder


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
        ollama_host=OLLAMA_HOST  # Pass the Ollama host to the agent
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