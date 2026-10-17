"""`codelabgen check …`: consistency checks over the generated course.

Each check returns a list of problems as strings, `path:line: message`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from codelabgen import curriculum as cur
from codelabgen import diagrams, runtimes, snippets
from codelabgen.course import Course
from codelabgen.markdown import IMAGE, LINK, code_blocks, heading_slugs, prose_lines

MERMAID_TYPES = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "erDiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
    "gitGraph",
    "quadrantChart",
    "block-beta",
    "architecture-beta",
    "sankey-beta",
    "xychart-beta",
    "packet-beta",
    "kanban",
)
FORBIDDEN = [
    (
        re.compile(r"^\s*(!!!|\?\?\?\+?)\s*\w"),
        "admonition syntax `!!!`/`???`; use > [!NOTE] alerts",
    ),
    (re.compile(r'^\s*===\+?\s+"'), "content tabs `===`; they don't render on GitHub"),
    (re.compile(r"--8<--"), "`--8<--` include; use <!-- snippet: … --> markers"),
    (re.compile(r"\(\d+\)!"), "code annotations `(1)!`; they don't render on GitHub"),
]
BAD_MATH = [
    (re.compile(r"\\\(|\\\)"), "math with \\( \\); use $…$"),
    (re.compile(r"\\\[.*\\\]"), "math with \\[ \\]; use $$…$$ on its own lines"),
    (re.compile(r"\S\s*\$\$|\$\$\s*\S.*\$\$"), "$$…$$ must stand on lines of its own"),
]


def course_markdown(course: Course) -> list[Path]:
    """Every Markdown page of the course (not .codelabgen, not virtualenvs)."""
    skip = {".codelabgen", ".venv", "node_modules", "site", ".git"}
    return sorted(
        p
        for p in course.root.rglob("*.md")
        if not skip.intersection(p.relative_to(course.root).parts)
        and p.relative_to(course.root).as_posix() != "assets/glossary-abbr.md"
    )


def where(course: Course, path: Path, line: int | None = None) -> str:
    rel = path.relative_to(course.root).as_posix()
    return f"{rel}:{line}" if line else rel


def check_links(course: Course) -> list[str]:
    """Relative links and images resolve; #anchors exist in the target page."""
    problems = []
    slug_cache: dict[Path, set[str]] = {}
    for page in course_markdown(course):
        text = page.read_text()
        for number, line in prose_lines(text):
            for pattern in (LINK, IMAGE):
                for target in pattern.findall(line):
                    if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("//"):
                        continue  # external URL, mailto:, …
                    path_part, _, anchor = target.partition("#")
                    resolved = page if not path_part else (page.parent / path_part).resolve()
                    if path_part and not resolved.exists():
                        problems.append(f"{where(course, page, number)}: broken link {target}")
                        continue
                    if anchor and resolved.suffix == ".md":
                        if resolved not in slug_cache:
                            slug_cache[resolved] = heading_slugs(resolved.read_text())
                        if anchor not in slug_cache[resolved]:
                            problems.append(
                                f"{where(course, page, number)}: no heading #{anchor} in "
                                f"{where(course, resolved)}"
                            )
    return problems


def check_render(course: Course) -> list[str]:
    """No syntax that breaks on GitHub; every D2/Graphviz SVG is up to date."""
    problems = []
    for page in course_markdown(course):
        for number, line in prose_lines(page.read_text()):
            for pattern, message in FORBIDDEN:
                if pattern.search(line):
                    problems.append(f"{where(course, page, number)}: {message}")
    for lesson in lessons(course):
        for source in diagrams.sources(course.root / lesson.rel_dir):
            if diagrams.is_stale(source):
                problems.append(
                    f"{where(course, source)}: SVG missing or older than the source; "
                    "run codelabgen diagrams render"
                )
    return problems


def check_math(course: Course) -> list[str]:
    """Math uses only $…$ and $$…$$, without spaces inside inline delimiters."""
    problems = []
    for page in course_markdown(course):
        for number, line in prose_lines(page.read_text()):
            stripped = re.sub(r"`[^`]*`", "", line)  # inline code may contain anything
            for pattern, message in BAD_MATH:
                if pattern.search(stripped):
                    problems.append(f"{where(course, page, number)}: {message}")
            if any(not f or f != f.strip() for f in inline_formulas(stripped)):
                problems.append(f"{where(course, page, number)}: space just inside $…$ delimiters")
    return problems


def inline_formulas(line: str) -> list[str]:
    """Contents of $…$ pairs on a line, pairing unescaped single dollars left to right."""
    line = line.replace("$$", "")  # block delimiters are checked separately
    dollars = [m.start() for m in re.finditer(r"(?<!\\)\$", line)]
    return [line[a + 1 : b] for a, b in zip(dollars[::2], dollars[1::2], strict=False)]


def check_mermaid(course: Course) -> list[str]:
    """Every Mermaid block starts with a known diagram type."""
    problems = []
    for page in course_markdown(course):
        for start, body in code_blocks(page.read_text(), "mermaid"):
            lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
            lines = [ln for ln in lines if not ln.startswith("%%")]
            if lines and lines[0] == "---":  # front matter (title, config)
                end = lines.index("---", 1) if "---" in lines[1:] else len(lines)
                lines = lines[end + 1 :]
            first = lines[0].split()[0] if lines else ""
            if first not in MERMAID_TYPES:
                problems.append(
                    f"{where(course, page, start)}: Mermaid block does not start "
                    f"with a diagram type (found {first or 'nothing'!r})"
                )
    return problems


def check_structure(course: Course) -> list[str]:
    """Every lesson has code, tests, README, docs/readalong.md and docs/notes.md."""
    problems = []
    runtime = runtimes.for_course(course)
    for lesson in lessons(course):
        folder = course.root / lesson.rel_dir
        required = {
            "lesson code": bool(runtimes.real_code_files(runtime, folder, lesson)),
            "tests": bool(runtime.test_files(folder, lesson)),
            "docs/readalong.md": (folder / "docs" / "readalong.md").is_file(),
            "docs/notes.md": (folder / "docs" / "notes.md").is_file(),
            "README.md": (folder / "README.md").is_file(),
        }
        missing = [name for name, present in required.items() if not present]
        if missing:
            problems.append(f"{lesson.rel_dir.as_posix()}: missing {', '.join(missing)}")
    return problems


def check_snippets(course: Course) -> list[str]:
    """Snippet markers point at existing regions and their copies are up to date."""
    problems = []
    for lesson in lessons(course):
        stale, found = snippets.sync(course.root / lesson.rel_dir, write=False)
        problems += [
            f"{where(course, p)}: out of date, run codelabgen snippets sync" for p in stale
        ]
        problems += [str(p) for p in found]
    return problems


def lessons(course: Course):
    return cur.lessons(cur.load(course))


CHECKS: dict[str, Callable[[Course], list[str]]] = {
    "structure": check_structure,
    "snippets": check_snippets,
    "links": check_links,
    "render": check_render,
    "math": check_math,
    "mermaid": check_mermaid,
}
