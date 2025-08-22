"""
Utilities module for the data scientist project.

This module provides various utility functions for working with data files,
database operations, and system prompts.
"""
import os
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

from .prompts import THERAPY_SYSTEM_PROMPT, THERAPY_PASS_A_CLEAN, THERAPY_PASS_B_FILE, THERAPY_PASS_C_GRAPH, THERAPY_TASK_PROMPT, PLANNING_INITIAL_FACTS, DB_SYSTEM_PROMPT
from .config import BASE_EXPORT, CYPHER_DIR, DB_PATH, E2B_MIRROR_DIR, CHUNK_SIZE, PATIENT_ID, SESSION_TYPE, SESSION_DATE
from .metadata_embedder import MetadataEmbedder
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
]
