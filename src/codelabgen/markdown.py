"""Small Markdown helpers shared by the generators and the checks."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def github_slug(text: str) -> str:
    """The anchor GitHub gives a heading (and the site, via pymdownx.slugs case=lower)."""
    text = re.sub(r"<[^>]+>", "", text)  # inline HTML
    # Drop code ticks, emphasis stars, strikethrough and link targets. Underscores stay:
    # GitHub and pymdownx.slugs both keep them (`path_map` -> #path_map).
    text = re.sub(r"[`*~]|\[|\]\([^)]*\)", "", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """(line number, line) for every line outside fenced code blocks."""
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
                continue
            if marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
                continue
        if fence is None:
            yield number, line


def code_blocks(text: str, language: str) -> Iterator[tuple[int, str]]:
    """(starting line, body) of every fenced block with the given language."""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^\s*(`{3,}|~{3,})\s*(\S*)", lines[index])
        if not match:
            index += 1
            continue
        marker, lang = match.group(1), match.group(2)
        start, body = index + 1, []
        index += 1
        while index < len(lines) and not lines[index].strip().startswith(marker):
            body.append(lines[index])
            index += 1
        index += 1
        if lang == language:
            yield start, "\n".join(body)


def heading_slugs(text: str) -> set[str]:
    """Anchors of all headings, with GitHub's -1, -2 suffixes for repeats."""
    seen: dict[str, int] = {}
    slugs = set()
    for _, line in prose_lines(text):
        match = HEADING.match(line)
        if not match:
            continue
        slug = github_slug(match.group(2))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        slugs.add(slug if count == 0 else f"{slug}-{count}")
    slugs.update(re.findall(r'<a\s+(?:id|name)="([^"]+)"', text))
    return slugs


def relative_link(from_file: Path, to_file: Path) -> str:
    return Path(os.path.relpath(to_file, from_file.parent)).as_posix()
