from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from src.states.paths import PathPack, ensure_host_dirs


class PersistenceManager:
    """Bi‑directional sync of key files between host and e2b sandbox.
    Host → Sandbox on boot; Sandbox → Host on shutdown.
    """
    def __init__(self, sandbox=None, paths: Optional[PathPack]=None):
        self.sandbox = sandbox
        self.paths = paths or PathPack()


    # --- internal utils ---
    def _sbx_mkdir(self, d: str):
        if not self.sandbox:
            return
        try:
            self.sandbox.files.mkdir(d)
        except Exception:
            pass # exists


    def _sbx_write_bytes(self, dest: str, data: bytes):
        assert self.sandbox is not None
        self._sbx_mkdir(str(Path(dest).parent))
        self.sandbox.files.write(dest, data)


    # --- public single file sync ---
    def push_file(self, host_path: str, sbx_path: str):
        if not self.sandbox:
            return
        with open(host_path, "rb") as f:
            self._sbx_write_bytes(sbx_path, f.read())


    def pull_file(self, sbx_path: str, host_path: str):
        if not self.sandbox:
            return
        blob = self.sandbox.files.read(sbx_path)
        data = blob if isinstance(blob, (bytes, bytearray)) else blob.encode()
        Path(host_path).parent.mkdir(parents=True, exist_ok=True)
        with open(host_path, "wb") as f:
            f.write(data)


    # --- public directory sync (recursive) ---
    def push_dir(self, host_dir: str, sbx_dir: str):
        if not self.sandbox:
            return
        host_dir_p = Path(host_dir)
        for p in host_dir_p.rglob("*"):
            if p.is_file():
                rel = p.relative_to(host_dir_p)
                dest = str(Path(sbx_dir) / rel)
                self.push_file(str(p), dest)


    def pull_dir(self, sbx_dir: str, host_dir: str):
        if not self.sandbox:
            return
        # e2b has no 'os.walk' so list children with sandbox API
        try:
            entries = self.sandbox.files.list(sbx_dir)
        except Exception:
            return
        for entry in entries:
            name = entry["name"]
            is_dir = entry.get("is_dir", False)
            sbx_child = f"{sbx_dir.rstrip('/')}/{name}"
            self.pull_file(self.paths.sbx_db, self.paths.host_db)
            host_child = str(Path(host_dir) / name)
            if is_dir:
                Path(host_child).mkdir(parents=True, exist_ok=True)
                self.pull_dir(sbx_child, host_child)
            else:
                self.pull_file(sbx_child, host_child)

    # --- lifecycle hooks ---
    def on_boot(self):
        ensure_host_dirs()
        for d in self.paths.sbx_dirs:
            self._sbx_mkdir(d)

        if not self.sandbox:
            return
        # Push canonical resources
        if os.path.exists(self.paths.host_db):
            self.push_file(self.paths.host_db, self.paths.sbx_db)
        if os.path.exists(self.paths.host_therapy_md):
            self.push_file(self.paths.host_therapy_md, self.paths.sbx_therapy_md)


    def on_shutdown(self):
        if not self.sandbox:
            return
        # Pull back canonical artifacts
        self.pull_file(self.paths.sbx_db, self.paths.host_db)

    def get_next_chunk_index(path="states/chunk_index.txt") -> int:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = int(f.read().strip())
        except FileNotFoundError:
            current = -1
        current += 1
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(current))
        return current