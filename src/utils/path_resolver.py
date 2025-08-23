from __future__ import annotations
import os

def ensure_dir(sandbox, path_sbx: str, path_host: str):
    """Create a directory either in sandbox or host, depending on context."""
    if sandbox:
        # mkdir -p semantics (parent creation handled by e2b internally)
        try:
            sandbox.files.mkdir(path_sbx)
        except Exception:
            pass
    else:
        os.makedirs(path_host, exist_ok=True)

def choose(sandbox, path_sbx: str, path_host: str) -> str:
    """Return the right path for the current context."""
    return path_sbx if sandbox else path_host