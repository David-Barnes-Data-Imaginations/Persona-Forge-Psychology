from pathlib import Path
import os

# Where to persist artifacts on the host
BASE_EXPORT = Path(os.getenv("BASE_EXPORT", "./export")).resolve()
CYTHER_DIR = "cypher"
DB_PATH = BASE_EXPORT / "therapy.db"

# Optional: mirror writes inside an e2b sandbox (for in‑session inspection)
# Set E2B_MIRROR_DIR in env if you want a second copy, e.g. /data/export
E2B_MIRROR_DIR = os.getenv("E2B_MIRROR_DIR", "")

# Chunking defaults
CHUNK_SIZE_DEFAULT = int(os.getenv("CHUNK_SIZE", "50"))

# Session defaults (override per run)
DEFAULT_PATIENT_ID = os.getenv("PATIENT_ID", "Client_345")
DEFAULT_SESSION_TYPE = os.getenv("SESSION_TYPE", "therapy_text")
DEFAULT_SESSION_DATE = os.getenv("SESSION_DATE", "2025-08-19")