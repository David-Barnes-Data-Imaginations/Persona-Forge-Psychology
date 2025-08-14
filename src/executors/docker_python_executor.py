# Python
import os
import textwrap
import uuid
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import docker


@dataclass
class DockerSandboxConfig:
    image: str = "python:3.13-slim"
    container_name: Optional[str] = None  # if None, auto-generate
    workdir: str = "/workspace"
    user: str = "nobody"
    env: Dict[str, str] = None
    volumes: Dict[str, Dict[str, str]] = None  # e.g. {"/host/data": {"bind": "/workspace/data", "mode": "ro"}}
    mem_limit: str = "1g"
    cpu_quota: int = 100000  # 100000 = 1 CPU, 200000 = 2 CPUs
    pids_limit: int = 256
    security_opt: Tuple[str, ...] = ("no-new-privileges",)
    cap_drop: Tuple[str, ...] = ("ALL",)
    read_only: bool = False
    network: Optional[str] = None  # attach to custom docker network if needed
    manage_container: bool = True  # create/run container if missing
    attach_only: bool = False      # only attach to existing container
    install_cmd: Optional[str] = None  # optional one-time setup cmd, e.g. "pip install -r /workspace/requirements.txt"


class DockerPythonExecutor:
    """
    Drop-in replacement for smolagents' Python executor that runs code inside a Docker container.
    Intended to be passed to CodeAgent via python_executor=...

    Security notes:
    - Runs as non-root user by default.
    - Drops all capabilities, sets no-new-privileges.
    - Supports read-only root filesystem.
    - Apply CPU/mem/pids limits.
    """
    def __init__(self, config: DockerSandboxConfig):
        self.config = config
        self._client = docker.from_env()
        self._container = None
        self._ensure_container()

    def _ensure_container(self):
        name = self.config.container_name or f"agent-exec-{uuid.uuid4().hex[:8]}"
        self.config.container_name = name  # freeze it

        try:
            self._container = self._client.containers.get(name)
            if self._container.status != "running":
                self._container.start()
        except docker.errors.NotFound:
            if self.config.attach_only:
                raise RuntimeError(f"Container '{name}' not found and attach_only=True")
            if not self.config.manage_container:
                raise RuntimeError("manage_container=False but container is missing")

            # Pull image if needed
            try:
                self._client.images.pull(self.config.image)
            except Exception:
                # Best-effort; image might be local-only
                pass

            environment = self.config.env or {}
            volumes = self.config.volumes or {}

            self._container = self._client.containers.run(
                image=self.config.image,
                name=name,
                command="tail -f /dev/null",
                working_dir=self.config.workdir,
                user=self.config.user,
                environment=environment,
                volumes=volumes,
                detach=True,
                tty=True,
                mem_limit=self.config.mem_limit,
                cpu_quota=self.config.cpu_quota,
                pids_limit=self.config.pids_limit,
                security_opt=list(self.config.security_opt),
                cap_drop=list(self.config.cap_drop),
                read_only=self.config.read_only,
                network=self.config.network,
            )

            # Optionally run a one-time setup/install command
            if self.config.install_cmd:
                self._exec(["bash", "-lc", self.config.install_cmd], timeout=0)  # no timeout for setup

        # Ensure workdir exists
        self._exec(["bash", "-lc", f"mkdir -p {self.config.workdir} && ls -la {self.config.workdir}"])

    def _exec(self, cmd, timeout: int = 120):
        """
        Run a command in the container. Returns (exit_code, output_str).
        """
        exec_result = self._container.exec_run(cmd=cmd, user=self.config.user, workdir=self.config.workdir)
        # docker SDK returns a tuple in low-level API, but high-level returns an object
        if isinstance(exec_result, tuple):
            exit_code, output = exec_result
        else:
            exit_code = getattr(exec_result, "exit_code", 1)
            output = getattr(exec_result, "output", b"")

        out = output.decode("utf-8", errors="replace") if isinstance(output, (bytes, bytearray)) else str(output)
        return exit_code, out

    def execute(self, code: str, timeout: int = 120) -> str:
        """
        Execute Python code inside the container and return combined stdout/stderr text.
        Compatible with smolagents' python_interpreter expectations.
        """
        safe_code = textwrap.dedent(code).strip()

        # We wrap code in a small runner to capture exceptions and ensure flush
        py_runner = f"""
import sys, traceback
try:
    __code = \"\"\"{safe_code}\"\"\"
    exec(compile(__code, "<agent>", "exec"), {{}}, {{}})
except SystemExit:
    pass
except Exception:
    traceback.print_exc()
"""
        # Write temp file in the container and execute it
        temp_name = f"/tmp/snippet_{uuid.uuid4().hex}.py"
        # Use bash heredoc to write file atomically
        heredoc = f"cat > {temp_name} << 'PYEOF'\n{py_runner}\nPYEOF\npython {temp_name}\nrm -f {temp_name}"
        exit_code, out = self._exec(["bash", "-lc", heredoc], timeout=timeout)

        # It’s often useful to normalize empty output so the UI shows something
        if not out.strip() and exit_code == 0:
            out = "Execution completed with no stdout."
        elif exit_code != 0 and not out.strip():
            out = f"Execution failed with exit code {exit_code} and no output."

        return out

    # Optional convenience helpers for tools
    def run_shell(self, shell_cmd: str) -> str:
        _, out = self._exec(["bash", "-lc", shell_cmd], timeout=120)
        return out

    def copy_in_requirements(self, host_requirements_path: str, container_requirements_path: str = "/workspace/requirements.txt"):
        """
        Assumes host_requirements_path is mounted into the container via volumes.
        If not mounted, use docker-py put_archive (more complex; omitted for brevity).
        """
        # No-op if volume is already mounted at the right location
        return

    def shutdown(self):
        if self._container and self.config.manage_container:
            try:
                self._container.stop()
            except Exception:
                pass
            try:
                self._container.remove()
            except Exception:
                pass
            self._container = None