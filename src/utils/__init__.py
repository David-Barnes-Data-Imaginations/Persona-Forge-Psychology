"""
Utilities module for the data scientist project.

This module provides various utility functions for working with data files,
database operations, and system prompts.
"""
import os
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
from .paths import PathPack, ensure_host_dirs, PathPack, SBX_DATA_DIR, SBX_STATES_DIR, SBX_EXPORTS_DIR, SBX_EMBED_DIR, SBX_DB_DIR, DEFAULT_DB_NAME, THERAPY_MD_NAME, SBX_DB_PATH, HOST_THERAPY_MD, SBX_THERAPY_MD, ALL_HOST_DIRS, ALL_SBX_DIRS, SBX_ROOT, SBX_DATA_DIR, SBX_EXPORTS_DIR, SBX_STATES_DIR, SBX_EMBED_DIR, SBX_DB_DIR, HOST_ROOT, HOST_DATA_DIR, HOST_EXPORTS_DIR, HOST_STATES_DIR, HOST_EMBED_DIR, HOST_DB_DIR
from .prompts import THERAPY_SYSTEM_PROMPT, THERAPY_PASS_A_CLEAN, THERAPY_PASS_B_FILE, THERAPY_PASS_C_GRAPH, THERAPY_TASK_PROMPT, PLANNING_INITIAL_FACTS, DB_SYSTEM_PROMPT
from .config import BASE_EXPORT, CYPHER_DIR, DB_PATH, E2B_MIRROR_DIR, CHUNK_SIZE, PATIENT_ID, SESSION_TYPE, SESSION_DATE
from .io_helpers import write_cypher, write_graph_json, sqlite_upsert_df, save_csv, ensure_dirs, _maybe_mirror_write
from .metadata_embedder import MetadataEmbedder, FS
from .session_paths import make_session_paths
from .export_writer import ExportWriter
from .prompts import build_planning_initial_facts
from .session_paths import SessionPaths, SessionPathTemplates, session_templates, make_session_paths, session_paths_for_chunk
from .sqlite_helpers import PRAGMA_BOOT, init_sqlite, ensure_schema, contextmanager, bulk_insert_qa, run_query
from .chunk_ids import _ensure_schema, _sess_key, next_chunk_id
from .ollama_utils import (
    check_ollama_server,
    wait_for_ollama_server,
    start_ollama_server_background,
    get_available_models,
    pull_model,
    generate_completion,
    chat_completion
)

__all__ = [
    THERAPY_SYSTEM_PROMPT,
    THERAPY_PASS_A_CLEAN,
    THERAPY_PASS_B_FILE,
    THERAPY_PASS_C_GRAPH,
    THERAPY_TASK_PROMPT,
    'MetadataEmbedder',
    BASE_EXPORT,
    CYPHER_DIR,
    DB_PATH,
    E2B_MIRROR_DIR,
    CHUNK_SIZE,
    PATIENT_ID,
    SESSION_TYPE,
    SESSION_DATE,
    'ExportWriter',
    'write_cypher',
    'write_graph_json',
    'sqlite_upsert_df',
    'save_csv',
    'ensure_dirs',
    '_maybe_mirror_write',
    'FS',
    'make_session_paths',
    '_ensure_schema',
    '_sess_key',
    'next_chunk_id',
    PRAGMA_BOOT,
    'init_sqlite',
    'ensure_schema',
    'contextmanager',
    'bulk_insert_qa',
    'run_query',
    'SessionPaths',
    'SessionPathTemplates',
    'session_templates',
    'make_session_paths',
    'session_paths_for_chunk',
    'build_planning_initial_facts',
'ensure_host_dirs',
    'PathPack',
    'SBX_DATA_DIR',
    'SBX_STATES_DIR',
    'SBX_EXPORTS_DIR',
    'SBX_EMBED_DIR',
    'SBX_DB_DIR',
    'DEFAULT_DB_NAME',
    'THERAPY_MD_NAME',
    'SBX_DB_PATH',
    'HOST_THERAPY_MD',
    'SBX_THERAPY_MD',
    'ALL_HOST_DIRS',
    'ALL_SBX_DIRS',
    'SBX_ROOT',
    'SBX_DATA_DIR',
    'SBX_EXPORTS_DIR',
    'SBX_STATES_DIR',
    'SBX_EMBED_DIR',
    'SBX_DB_DIR',
    'HOST_ROOT',
    'HOST_DATA_DIR',
    'HOST_EXPORTS_DIR',
    'HOST_STATES_DIR',
    'HOST_EMBED_DIR',
    'HOST_DB_DIR'
]
