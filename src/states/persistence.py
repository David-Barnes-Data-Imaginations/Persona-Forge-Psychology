# src/utils/persistence.py
from __future__ import annotations
import os
from typing import Optional
from .paths import PathPack, ensure_host_dirs

class PersistenceManager:
    """Bi-directional sync of key files between host and e2b sandbox.
    Host is source of truth at boot; sandbox is source of truth at shutdown.
    """
    def __init__(self, sandbox=None, paths: Optional[PathPack]=None):
        self.sandbox = sandbox
        self.paths = paths or PathPack()


    def _sbx_mkdirs(self):
        if not self.sandbox:
            return
        for d in self.paths.sbx_dirs:
            try:
                self.sandbox.files.mkdir(d)
            except Exception:
                # may already exist
                pass

    def on_boot(self):
        ensure_host_dirs()
        self._sbx_mkdirs()
        if not self.sandbox:
            return

        # Upload DB if exists
        if os.path.exists(self.paths.host_db):
            with open(self.paths.host_db, "rb") as f:
                self.sandbox.files.write(self.paths.sbx_db, f)

        # Upload therapy-gpt.md so the agent can read it
        if os.path.exists(self.paths.host_therapy_md):
            with open(self.paths.host_therapy_md, "rb") as f:
                self.sandbox.files.write(self.paths.sbx_therapy_md, f)

    def on_shutdown(self):
        if not self.sandbox:
            return
    # Pull DB back down (authoritative latest state)
        try:
            blob = self.sandbox.files.read(self.paths.sbx_db)
            os.makedirs(os.path.dirname(self.paths.host_db), exist_ok=True)
            with open(self.paths.host_db, "wb") as f:
                f.write(blob if isinstance(blob, (bytes, bytearray)) else blob.encode())
        except Exception:
            pass