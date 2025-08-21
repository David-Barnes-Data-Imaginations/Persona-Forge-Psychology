# src/utils/paths.py
from __future__ import annotations
import os
from dataclasses import dataclass

# Host roots (relative to your project root)
HOST_ROOT = os.path.abspath(".")
HOST_DATA_DIR = os.path.join(HOST_ROOT, "src", "data")
HOST_EXPORTS_DIR = os.path.join(HOST_ROOT, "export")
HOST_STATES_DIR = os.path.join(HOST_ROOT, "src", "states")
HOST_EMBED_DIR = os.path.join(HOST_ROOT, "embeddings")
HOST_DB_DIR = os.path.join(HOST_ROOT, "export") # keep DB alongside exports


# Sandbox roots (single, clean namespace)
SBX_ROOT = "/workspace"
SBX_DATA_DIR = os.path.join(SBX_ROOT, "data")
SBX_EXPORTS_DIR = os.path.join(SBX_ROOT, "export")
SBX_STATES_DIR = os.path.join(SBX_ROOT, "states")
SBX_EMBED_DIR = os.path.join(SBX_ROOT, "embeddings")
SBX_DB_DIR = SBX_EXPORTS_DIR


DEFAULT_DB_NAME = "therapy.db"
THERAPY_MD_NAME = "therapy.md"


# Resolved common paths
HOST_DB_PATH = os.path.join(HOST_DB_DIR, DEFAULT_DB_NAME)
SBX_DB_PATH = os.path.join(SBX_DB_DIR, DEFAULT_DB_NAME)
HOST_THERAPY_MD = os.path.join(HOST_DATA_DIR, THERAPY_MD_NAME)
SBX_THERAPY_MD = os.path.join(SBX_DATA_DIR, THERAPY_MD_NAME)


ALL_HOST_DIRS = [HOST_DATA_DIR, HOST_EXPORTS_DIR, HOST_STATES_DIR, HOST_EMBED_DIR, HOST_DB_DIR]
ALL_SBX_DIRS = [SBX_DATA_DIR, SBX_EXPORTS_DIR, SBX_STATES_DIR, SBX_EMBED_DIR, SBX_DB_DIR]

def ensure_host_dirs() -> None:
    for d in ALL_HOST_DIRS:
        os.makedirs(d, exist_ok=True)


@dataclass
class PathPack:
    host_db: str = HOST_DB_PATH
    sbx_db: str = SBX_DB_PATH
    host_therapy_md: str = HOST_THERAPY_MD
    sbx_therapy_md: str = SBX_THERAPY_MD
    host_dirs: list[str] = None
    sbx_dirs: list[str] = None


    def __post_init__(self):
        self.host_dirs = ALL_HOST_DIRS
        self.sbx_dirs = ALL_SBX_DIRS