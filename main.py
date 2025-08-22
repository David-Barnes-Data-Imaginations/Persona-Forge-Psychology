import asyncio, os, base64
from dotenv import load_dotenv
load_dotenv() # <-- ensure .env gets loaded
from e2b_code_interpreter import Sandbox
from src.client.telemetry import TelemetryManager
from src.utils.metadata_embedder import MetadataEmbedder
from src.client.agent import ToolFactory, CustomAgent
from src.client.ui.chat import GradioUI as gradio_ui
from src.utils.ollama_utils import wait_for_ollama_server, start_ollama_server_background, pull_model
from pathlib import Path
import argparse
import os
from src.states.persistence import PersistenceManager
from src.client.agent import CustomAgent
from src.client.agent_router import TherapyRouter
from src.utils.config import (
BASE_EXPORT,
DB_PATH,
E2B_MIRROR_DIR,
CHUNK_SIZE,
PATIENT_ID,
SESSION_DATE,
SESSION_TYPE,
)

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


global sandbox, agent, chat_interface, metadata_embedder, chunk_number

# define conventional subdirs similar to the old Docker volumes
INSIGHTS_DIR = (BASE_EXPORT / "insights").resolve()
EMBEDDINGS_DIR = (BASE_EXPORT / "embeddings").resolve()
STATES_DIR = (BASE_EXPORT / "states").resolve()
LOGS_DIR = (BASE_EXPORT / "logs").resolve()

def ensure_runtime_dirs():
    for p in [BASE_EXPORT, INSIGHTS_DIR, EMBEDDINGS_DIR, STATES_DIR, LOGS_DIR, DB_PATH.parent]:
        p.mkdir(parents=True, exist_ok=True)

# ---- Planning facts prompt (compact) ----
# This is generated at runtime so it always reflects real paths.
def build_planning_initial_facts(*, patient_id=None, session_type=None, session_date=None, chunk_size=None) -> str:
    pid = patient_id or PATIENT_ID
    stype = session_type or SESSION_TYPE
    sdate = session_date or SESSION_DATE
    csize = chunk_size or CHUNK_SIZE

    base = (BASE_EXPORT / pid / stype / sdate).resolve()
    cypher_dir = (BASE_EXPORT / "cypher" / pid / stype / sdate).resolve()


    return (
        "Before starting, here are concrete environment facts for this run:\n"
        f"- PATIENT_ID: {pid}\n"
        f"- SESSION_TYPE: {stype}\n"
        f"- SESSION_DATE: {sdate}\n"
        f"- CHUNK_SIZE: {csize}\n"
        f"- EXPORT_BASE: {BASE_EXPORT}\n"
        f"- SESSION_EXPORT_DIR: {base}\n"
        f"- CYPHER_EXPORT_DIR: {cypher_dir}\n"
        f"- SQLITE_DB: {DB_PATH}\n"
        f"- INSIGHTS_DIR: {INSIGHTS_DIR}\n"
        f"- EMBEDDINGS_DIR: {EMBEDDINGS_DIR}\n"
        f"- STATES_DIR: {STATES_DIR}\n"
        f"- LOGS_DIR: {LOGS_DIR}\n"
        f"- E2B_MIRROR_DIR: {E2B_MIRROR_DIR or '(disabled)'}\n"
        
        "Rules:\n"
        "1) Read input transcript from INPUT_PATH (default ./therapy-gpt.md).\n"
        "2) Write CSV/Graph-JSON under SESSION_EXPORT_DIR; write Cypher under CYPHER_EXPORT_DIR.\n"
        "3) Upsert into SQLITE_DB (table qa_pairs).\n"
        "4) Persist chunk notes under INSIGHTS_DIR/STATES_DIR.\n"
        "5) Keep outputs deterministic; no PII beyond pseudonyms.\n"
        )

# ---- CLI wiring ----

def cli():
    parser = argparse.ArgumentParser(description="Therapy agent router")
    parser.add_argument("action", choices=["pass", "pipeline"], help="Run a single pass or full pipeline")
    parser.add_argument("pass_name", nargs="?", help="A|B|C when action=pass")
    parser.add_argument("--input_path", default="./therapy-gpt.md")
    parser.add_argument("--patient_id", default=PATIENT_ID)
    parser.add_argument("--session_type", default=SESSION_TYPE)
    parser.add_argument("--session_date", default=SESSION_DATE)
    parser.add_argument("--chunk_size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--print_facts", action="store_true", help="Print planning facts and exit")
    args = parser.parse_args()

    ensure_runtime_dirs()

    agent = CustomAgent(model_id=os.getenv("MODEL_ID", "gpt-oss:20b"))
    agent.router = TherapyRouter(agent) # ensure attached

    if args.print_facts:
        print(build_planning_initial_facts(
            patient_id=args.patient_id,
            session_type=args.session_type,
            session_date=args.session_date,
            chunk_size=args.chunk_size,
    ))
        return

    # Prepend the planning facts to the first pass request for extra clarity
    planning = build_planning_initial_facts(
        patient_id=args.patient_id,
        session_type=args.session_type,
        session_date=args.session_date,
        chunk_size=args.chunk_size,
    )

    if args.action == "pass":
        if not args.pass_name:
            raise SystemExit("Please supply A, B, or C after 'pass'")
        print(planning)
        out = agent.router.run_pass(
            args.pass_name,
            patient_id=args.patient_id,
            session_type=args.session_type,
            session_date=args.session_date,
            chunk_size=args.chunk_size,
            input_path=args.input_path,
        )
        print(out)
    else:
        print(planning)
        out = agent.router.run_full_pipeline(
        patient_id=args.patient_id,
        session_type=args.session_type,
        session_date=args.session_date,
        chunk_size=args.chunk_size,
        input_path=args.input_path,
        )
    print(out)

def main():

    # Create E2B sandbox only if explicitly enabled and API key is present
    sandbox = None
    if USE_E2B:
        e2b_api_key = os.getenv("E2B_API_KEY")
        if not e2b_api_key:
            raise RuntimeError("USE_E2B=true but E2B_API_KEY is missing. Set it in your environment or .env")


    # Initialize psych_metadata embedder and embed psych_metadata file
    print("📚 Setting up psych_metadata embeddings...")
    metadata_embedder = MetadataEmbedder(sandbox)
    result = metadata_embedder.embed_metadata_dirs([
        "./src/data/psych_metadata",
        "./src/data/patient_raw_data"
    ], refresh=False)
    print(result)

    # Create agent, tool factory and tools
    print("🛠️ Creating tools...")
    tool_factory = ToolFactory(sandbox, metadata_embedder)
    tools = tool_factory.create_all_tools()

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

    build_planning_initial_facts()
    cli()

if __name__ == "__main__":
    main()