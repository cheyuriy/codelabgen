"""Code regions copied into Markdown (PLAN.md §3.4).

In code, a region is marked with comment lines in the file's comment syntax:

    # region build_graph
    ...
    # endregion

In Markdown, a snippet is a pair of comment markers. `sync` fills the space
between them with a fenced code block holding the region:

    <!-- snippet: src/l1_1_hello/graph.py#build_graph -->
    ```python
    ...
    ```
    <!-- /snippet -->

Paths are relative to the lesson directory (the folder that holds `docs/`).
Without `#region` the whole file is used. Region marker lines never appear in
the copied code.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

REGION_START = re.compile(r"^\s*(?:#|//|--|;|%)\s*region\s+([A-Za-z0-9_.-]+)\s*$")
REGION_END = re.compile(r"^\s*(?:#|//|--|;|%)\s*endregion\b.*$")
SNIPPET = re.compile(
    r"(?P<open><!--\s*snippet:\s*(?P<ref>[^\s#]+)(?:#(?P<region>[A-Za-z0-9_.-]+))?\s*-->)"
    r"(?P<body>.*?)"
    r"(?P<close><!--\s*/snippet\s*-->)",
    re.DOTALL,
)
OPEN_ONLY = re.compile(r"<!--\s*snippet:")

LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".sql": "sql",
    ".sh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".dockerfile": "dockerfile",
    ".env": "bash",
}


class RegionError(Exception):
    pass


@dataclass
class Problem:
    file: Path
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.message}"


def parse_regions(text: str) -> dict[str, str]:
    """Region name -> its code, with nested marker lines removed and dedented."""
    regions: dict[str, list[str]] = {}
    stack: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if start := REGION_START.match(line):
            name = start.group(1)
            if name in regions:
                raise RegionError(f"line {number}: region '{name}' is defined twice")
            regions[name] = []
            stack.append(name)
            continue
        if REGION_END.match(line):
            if not stack:
                raise RegionError(f"line {number}: endregion without a region")
            stack.pop()
            continue
        for name in stack:
            regions[name].append(line)
    if stack:
        raise RegionError(f"region '{stack[-1]}' is not closed")
    return {name: textwrap.dedent("\n".join(lines)).strip("\n") for name, lines in regions.items()}


def strip_markers(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not (REGION_START.match(line) or REGION_END.match(line))
    ).strip("\n")


def lesson_dir_for(markdown: Path) -> Path:
    """The lesson directory: the parent of the nearest enclosing `docs/` folder."""
    for parent in markdown.resolve().parents:
        if parent.name == "docs":
            return parent.parent
    return markdown.resolve().parent


def fence_for(code: str) -> str:
    longest = max((len(m) for m in re.findall(r"`{3,}", code)), default=2)
    return "`" * max(3, longest + 1)


def render_snippet(base: Path, ref: str, region: str | None) -> str:
    path = (base / ref).resolve()
    if not path.is_file():
        raise RegionError(f"snippet file {ref} not found")
    text = path.read_text()
    if region is None:
        code = strip_markers(text)
    else:
        regions = parse_regions(text)
        if region not in regions:
            known = ", ".join(sorted(regions)) or "none"
            raise RegionError(f"{ref} has no region '{region}' (regions: {known})")
        code = regions[region]
    language = LANGUAGES.get(path.suffix.lower(), "")
    fence = fence_for(code)
    return f"\n{fence}{language}\n{code}\n{fence}\n"


def sync_text(markdown: Path, text: str) -> tuple[str, list[Problem]]:
    """New Markdown text with every snippet refreshed, plus problems found."""
    base = lesson_dir_for(markdown)
    problems: list[Problem] = []

    def replace(match: re.Match) -> str:
        try:
            body = render_snippet(base, match.group("ref"), match.group("region"))
        except RegionError as exc:
            problems.append(Problem(markdown, str(exc)))
            return match.group(0)
        return match.group("open") + body + match.group("close")

    new_text = SNIPPET.sub(replace, text)
    opened = len(OPEN_ONLY.findall(text))
    closed = len(SNIPPET.findall(text))
    if opened != closed:
        problems.append(
            Problem(markdown, f"{opened - closed} snippet marker(s) without <!-- /snippet -->")
        )
    return new_text, problems


def markdown_files(lesson_dir: Path) -> list[Path]:
    docs = lesson_dir / "docs"
    return sorted(docs.rglob("*.md")) if docs.is_dir() else []


def code_files(lesson_dir: Path) -> list[Path]:
    return sorted(
        p
        for folder in ("src", "tests")
        if (lesson_dir / folder).is_dir()
        for p in (lesson_dir / folder).rglob("*")
        if p.is_file() and p.suffix in LANGUAGES and "__pycache__" not in p.parts
    )


def sync(lesson_dir: Path, write: bool = True) -> tuple[list[Path], list[Problem]]:
    """Refresh snippets in a lesson's docs. Returns (changed or stale files, problems).

    With write=False nothing is written; the returned files are the ones out of date.
    """
    changed: list[Path] = []
    problems: list[Problem] = []
    for path in code_files(lesson_dir):
        try:
            parse_regions(path.read_text())
        except RegionError as exc:
            problems.append(Problem(path, str(exc)))
    for markdown in markdown_files(lesson_dir):
        text = markdown.read_text()
        new_text, found = sync_text(markdown, text)
        problems.extend(found)
        if new_text != text:
            changed.append(markdown)
            if write:
                markdown.write_text(new_text)
    return changed, problems
