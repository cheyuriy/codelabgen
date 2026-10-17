"""`codelabgen doctor`: which external tools are available and what a missing one disables."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    command: str
    feature: str
    required: bool = False
    version_args: tuple[str, ...] = ("--version",)
    # A command that must succeed for the tool to be usable, not just installed.
    probe_args: tuple[str, ...] | None = None


TOOLS = [
    Tool("uv", "running the CLI and Python lessons", required=True),
    Tool("git", "course repository and repo clones", required=True),
    Tool(
        "docker",
        "services (Postgres, Redis…) in lessons and verification",
        probe_args=("info", "--format", "{{.ServerVersion}}"),
    ),
    Tool("gh", "GitHub search, repo metadata and issues (source discovery)"),
    Tool("d2", "D2 architecture diagrams"),
    Tool("dot", "Graphviz diagrams", version_args=("-V",)),
    Tool("asciinema", "terminal recordings"),
    Tool("agg", "converting terminal recordings to GIF"),
    Tool("node", "Node courses (with npm); Mermaid and LaTeX checks"),
    Tool("go", "Go courses", version_args=("version",)),
    Tool("yt-dlp", "talk transcripts (without it, `uvx yt-dlp` is used)"),
]


@dataclass
class ToolStatus:
    tool: Tool
    path: str | None
    version: str | None
    problem: str | None = None  # installed but not usable

    @property
    def usable(self) -> bool:
        return bool(self.path) and self.problem is None


def _first_line(path: str, args: tuple[str, ...]) -> tuple[int, str | None]:
    try:
        proc = subprocess.run([path, *args], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return 1, "timed out"
    except OSError as exc:
        return 1, str(exc)
    lines = (proc.stdout.strip() or proc.stderr.strip()).splitlines()
    return proc.returncode, lines[0] if lines else None


def check_tools() -> list[ToolStatus]:
    results = []
    for tool in TOOLS:
        path = shutil.which(tool.command)
        status = ToolStatus(tool, path, None)
        if path:
            _, status.version = _first_line(path, tool.version_args)
            if tool.probe_args:
                code, output = _first_line(path, tool.probe_args)
                if code != 0:
                    status.problem = output or f"`{tool.command} {tool.probe_args[0]}` failed"
        results.append(status)
    return results
