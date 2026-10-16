"""`codelabgen diagrams render`: D2 and Graphviz sources in docs/diagrams/ -> SVG.

Both the source and the SVG are committed, so GitHub shows the diagram without
a build step. Graphviz SVGs have a transparent background; D2 SVGs carry a light
and a dark palette and follow the reader's color scheme.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

RENDERERS = {
    ".d2": (
        "d2",
        lambda src, out: [
            "d2",
            "--theme",
            "0",
            "--dark-theme",
            "200",
            "--pad",
            "20",
            "--omit-version",
            str(src),
            str(out),
        ],
    ),
    ".dot": (
        "dot",
        lambda src, out: ["dot", "-Tsvg", "-Gbgcolor=transparent", str(src), "-o", str(out)],
    ),
}


@dataclass
class RenderReport:
    rendered: list[Path] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def sources(lesson_dir: Path) -> list[Path]:
    folder = lesson_dir / "docs" / "diagrams"
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix in RENDERERS)


def is_stale(source: Path) -> bool:
    svg = source.with_suffix(".svg")
    return not svg.exists() or svg.stat().st_mtime < source.stat().st_mtime


def render(lesson_dir: Path, force: bool = False) -> RenderReport:
    report = RenderReport()
    for source in sources(lesson_dir):
        if not (force or is_stale(source)):
            continue
        tool, argv = RENDERERS[source.suffix]
        if shutil.which(tool) is None:
            report.problems.append(
                f"{source.name}: `{tool}` is not installed (see codelabgen doctor)"
            )
            continue
        out = source.with_suffix(".svg")
        proc = subprocess.run(argv(source, out), capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout).strip().splitlines()
            report.problems.append(f"{source.name}: {message[-1] if message else 'render failed'}")
            continue
        report.rendered.append(out)
    return report
