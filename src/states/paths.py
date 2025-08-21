# src/utils/paths.py
from __future__ import annotations
import os
from dataclasses import dataclass


# Host-side canonical roots (git-tracked where sensible)
HOST_ROOT = os.path.abspath(".")
HOST_DATA_DIR = os.path.join(HOST_ROOT, "data")
HOST_EXPORTS_DIR = os.path.join(HOST_ROOT, "exports")
HOST_EMBED_DIR = os.path.join(HOST_ROOT, "embeddings")
HOST_INSIGHTS_DIR = os.path.join(HOST_ROOT, "insights")
HOST_DB_DIR = os.path.join(HOST_ROOT, "db")


# In-sandbox canonical roots (stable, human-readable)
SBX_DATA_DIR = "/workspace/data"
SBX_EXPORTS_DIR = "/workspace/exports"
SBX_EMBED_DIR = "/workspace/embeddings"
SBX_INSIGHTS_DIR = "/workspace/insights"
SBX_DB_DIR = "/workspace/db"


# Default filenames
DEFAULT_DB_NAME = "persona_forge.sqlite"
THERAPY_MD_NAME = "therapy.md"


# Common resolved paths
HOST_DB_PATH = os.path.join(HOST_DB_DIR, DEFAULT_DB_NAME)
SBX_DB_PATH = os.path.join(SBX_DB_DIR, DEFAULT_DB_NAME)
HOST_THERAPY_MD = os.path.join(HOST_ROOT, THERAPY_MD_NAME)
SBX_THERAPY_MD = os.path.join(SBX_DATA_DIR, THERAPY_MD_NAME)


ALL_HOST_DIRS = [HOST_DATA_DIR, HOST_EXPORTS_DIR, HOST_EMBED_DIR, HOST_INSIGHTS_DIR, HOST_DB_DIR]
ALL_SBX_DIRS = [SBX_DATA_DIR, SBX_EXPORTS_DIR, SBX_EMBED_DIR, SBX_INSIGHTS_DIR, SBX_DB_DIR]



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