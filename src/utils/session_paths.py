# A file to centrally manage the duality of the paths in my $PROJECT_DIR vs The Sandbox paths via 'export'
# src/utils/session_paths.py
from __future__ import annotations
import os
from dataclasses import dataclass
from src.utils.paths import SBX_DATA_DIR, SBX_EXPORTS_DIR, SBX_DB_DIR

@dataclass
class SessionPaths:
    base: str
    csv_path: str
    graph_path: str

@dataclass(frozen=True)
class SessionPathTemplates:
    """Sandbox-first templates for a session. Use {k} for chunk number."""
    export_base: str                  # /workspace/export/PID/TYPE/DATE
    csv_template: str                 # /workspace/export/.../qa_chunk_{k}.csv
    graph_template: str               # /workspace/export/.../graph_chunk_{k}.json
    cypher_dir: str                   # /workspace/export/.../cypher (optional)
    sqlite_db: str                    # /workspace/export/therapy.db
    therapy_md: str                   # /workspace/data/patient_raw_data/therapy.md
    psych_frameworks_md: str          # /workspace/data/psych_metadata/psych_frameworks.md
    graph_schema_json: str            # /workspace/data/psych_metadata/graph_schema.json

def session_templates(patient_id: str, session_type: str, session_date: str) -> SessionPathTemplates:
    export_base = f"{SBX_EXPORTS_DIR}/{patient_id}/{session_type}/{session_date}"
    cypher_dir = f"{export_base}/cypher"
    return SessionPathTemplates(
        export_base=export_base,
        csv_template=f"{export_base}/qa_chunk_{{k}}.csv",
        graph_template=f"{export_base}/graph_chunk_{{k}}.json",
        cypher_dir = f"{export_base}/cypher",
        sqlite_db=f"{SBX_EXPORTS_DIR}/therapy.db",
        therapy_md=f"{SBX_DATA_DIR}/patient_raw_data/therapy.md",
        psych_frameworks_md=f"{SBX_DATA_DIR}/psych_metadata/psych_frameworks.md",
        graph_schema_json=f"{SBX_DATA_DIR}/psych_metadata/graph_schema.json",
    )
def make_session_paths(patient_id: str, session_type: str, session_date: str, chunk_id: int) -> SessionPaths:
    base = f"{SBX_EXPORTS_DIR}/{patient_id}/{session_type}/{session_date}"
    """
    Here the 'os.makedirs/writes' operate INSIDE the sandbox (e.g. /workspace/export/) 
    We need to fill the missing imports and path definitions to ensure the code compiles.
    Then on the 'host', the persistence.py code handles this:
    - At Boot: Option to push an existing DB into the sandbox
    - At Shutdown: pull the sandbox export tree back.
    """
    # Try to create inside sandbox path; if running locally, fallback to host mirror (prefix ".")
    try:
        os.makedirs(base, exist_ok=True)  # SANDBOX side when running in sandbox
        base_dir_for_creation = base
    except PermissionError:
        host_mirror = "." + base if base.startswith("/") else base
        os.makedirs(host_mirror, exist_ok=True)
        base_dir_for_creation = host_mirror

    return SessionPaths(
        base=base,  # keep the sandbox-first path as the canonical reference
        csv_path=f"{base}/qa_chunk_{chunk_id}.csv",
        graph_path=f"{base}/graph_chunk_{chunk_id}.json",
    )


# concrete paths for a specific chunk index
def session_paths_for_chunk(patient_id: str, session_type: str, session_date: str, k: int) -> dict[str, str]:
    t = session_templates(patient_id, session_type, session_date)
    return {
        "export_base": t.export_base,
        "csv_path": t.csv_template.format(k=k),
        "graph_path": t.graph_template.format(k=k),
        "cypher_dir": t.cypher_dir,
        "sqlite_db": t.sqlite_db,
        "therapy_md": t.therapy_md,
        "psych_frameworks_md": t.psych_frameworks_md,
        "graph_schema_json": t.graph_schema_json,
    }
