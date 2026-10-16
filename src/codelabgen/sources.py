"""The source registry: `.codelabgen/sources.jsonl` and the review sheet `sources.md`.

Source hunters add rows with `codelabgen sources add` (validated, URL-normalized,
deduplicated under a lock, so hunters can run in parallel). The orchestrator
renders `sources.md` for the user, who ticks, unticks and adds sources; `apply`
reads the sheet back into the registry.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from filelock import FileLock

from codelabgen.course import Course, atomic_write
from codelabgen.i18n import labels
from codelabgen.models import Source

TRACKING = re.compile(r"^(utm_\w+|ref|ref_src|source|fbclid|gclid|mc_cid|mc_eid)$")
TYPE_ORDER = [
    "official-docs",
    "release-notes",
    "official-blog",
    "package-internals",
    "github-repo",
    "article",
    "qa",
    "paper-spec",
    "talk-workshop",
    "university",
    "book-course",
]
KEEP_THRESHOLD = 0.6


class SourcesError(Exception):
    pass


@dataclass
class AddReport:
    added: list[str] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)


def registry(course: Course) -> Path:
    return course.meta / "sources.jsonl"


def sheet(course: Course) -> Path:
    return course.meta / "sources.md"


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = parts.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parts.path) or ""
    if host == "github.com":
        path = re.sub(r"\.git$", "", path)
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if not TRACKING.match(k)))
    return urlunsplit((scheme, host, path, query, ""))


def make_id(source: Source) -> str:
    host = urlsplit(source.url).netloc.removeprefix("www.").split(":")[0]
    host = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
    digest = hashlib.sha1(source.url.encode()).hexdigest()[:6]
    return f"{source.type}--{host}--{digest}"


def load(course: Course) -> list[Source]:
    path = registry(course)
    if not path.is_file():
        return []
    return [
        Source.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
    ]


def save(course: Course, items: list[Source]) -> None:
    order = {t: i for i, t in enumerate(TYPE_ORDER)}
    items = sorted(items, key=lambda s: (order.get(s.type, 99), -s.score, s.id))
    text = "".join(s.model_dump_json(exclude_none=True) + "\n" for s in items)
    atomic_write(registry(course), text)


def add(course: Course, rows: list[dict]) -> AddReport:
    """Validate and merge rows into the registry. Same URL = same source."""
    incoming = []
    for row in rows:
        source = Source.model_validate(row)
        source.url = normalize_url(source.url)
        if not source.id:
            source.id = make_id(source)
        incoming.append(source)
    report = AddReport()
    with FileLock(str(course.meta / "sources.lock"), timeout=30):
        items = load(course)
        by_url = {s.url: s for s in items}
        for source in incoming:
            existing = by_url.get(source.url)
            if existing is None:
                items.append(source)
                by_url[source.url] = source
                report.added.append(source.id)
                continue
            # Merge: keep the better score and reason, union the roles, keep user status.
            existing.roles = sorted(set(existing.roles) | set(source.roles))
            if source.score > existing.score:
                existing.score, existing.reason = source.score, source.reason
            for name in ("version", "date", "language"):
                if getattr(existing, name) is None:
                    setattr(existing, name, getattr(source, name))
            report.merged.append(existing.id)
        save(course, items)
    return report


def query(
    course: Course,
    status: list[str] | None = None,
    type_: str | None = None,
    role: str | None = None,
) -> list[Source]:
    return [
        s
        for s in load(course)
        if (not status or s.status in status)
        and (not type_ or s.type == type_)
        and (not role or role in s.roles)
    ]


# --- review sheet --------------------------------------------------------------------------

SHEET_INTRO = {
    "en": (
        "Review the proposed sources. Ticked sources are used for the course.\n"
        "Untick a source to drop it, tick one to keep it. To add your own sources, put one URL\n"
        "per line in the last section, optionally followed by ` — why`. Then tell Claude you\n"
        "are done (or run `/codelabgen:sources`)."
    ),
    "ru": (
        "Проверьте предложенные источники. Отмеченные будут использованы для курса.\n"
        "Снимите отметку, чтобы исключить источник, или поставьте, чтобы оставить. Свои\n"
        "источники добавьте в последний раздел: по одному URL в строке, после него можно\n"
        "написать ` — зачем`. Затем скажите Claude, что готово\n"
        "(или выполните `/codelabgen:sources`)."
    ),
}
ADD_HEADING = {"en": "Add your sources", "ru": "Добавить свои источники"}
LINE = re.compile(r"^- \[(?P<mark>[ xX])\] .*?<!-- id: (?P<id>[^ ]+) -->\s*$")


def render(course: Course) -> Path:
    config = course.load_config()
    language = config.language if config.language in SHEET_INTRO else "en"
    items = load(course)
    title = labels(config.language)["sources"]
    lines = [
        f"# {title}: {config.topic}" + (f" {config.version}" if config.version else ""),
        "",
        SHEET_INTRO[language],
        "",
    ]
    for type_ in TYPE_ORDER:
        group = [s for s in items if s.type == type_]
        if not group:
            continue
        lines += [f"## {type_}", ""]
        for s in group:
            checked = s.status in ("kept", "user") or (
                s.status == "proposed" and s.score >= KEEP_THRESHOLD
            )
            meta = [f"{s.score:.2f}", ", ".join(s.roles)]
            meta += [x for x in (s.language, s.version, s.date) if x]
            lines.append(
                f"- [{'x' if checked else ' '}] [{s.title}]({s.url}) — {s.reason} "
                f"*({' · '.join(meta)})* <!-- id: {s.id} -->"
            )
        lines.append("")
    lines += [f"## {ADD_HEADING[language]}", "", "<!-- https://… — why -->", ""]
    atomic_write(sheet(course), "\n".join(lines))
    return sheet(course)


def guess_type(url: str) -> str:
    host, path = urlsplit(url).netloc.lower(), urlsplit(url).path.lower()
    if "github.com" in host:
        return "qa" if "/issues" in path or "/discussions" in path else "github-repo"
    if "arxiv.org" in host or path.endswith(".pdf"):
        return "paper-spec"
    if "youtube.com" in host or "youtu.be" in host:
        return "talk-workshop"
    if "stackoverflow.com" in host:
        return "qa"
    return "article"


def apply(course: Course) -> dict:
    """Read the user's edits from sources.md back into the registry."""
    path = sheet(course)
    if not path.is_file():
        raise SourcesError(f"{path} does not exist; run `codelabgen sources render` first")
    marks: dict[str, bool] = {}
    added_rows: list[dict] = []
    in_add_section = False
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            in_add_section = line[3:].strip() in ADD_HEADING.values()
            continue
        match = LINE.match(line.strip())
        if match:
            marks[match.group("id")] = match.group("mark").lower() == "x"
            continue
        if in_add_section:
            url_match = re.search(r"https?://\S+", line)
            if url_match and not line.strip().startswith("<!--"):
                url = url_match.group(0).rstrip(").,")
                why = line[url_match.end() :].strip(" —-:\t") or "Added by the user"
                added_rows.append(
                    {
                        "url": url,
                        "type": guess_type(url),
                        "roles": ["concepts"],
                        "title": url,
                        "score": 1.0,
                        "reason": why,
                        "status": "user",
                    }
                )
    with FileLock(str(course.meta / "sources.lock"), timeout=30):
        items = load(course)
        known = {s.id for s in items}
        unknown = [i for i in marks if i not in known]
        if unknown:
            raise SourcesError(f"sources.md mentions unknown ids: {', '.join(unknown)}")
        kept = dropped = 0
        for source in items:
            if source.id not in marks:
                continue
            if source.status == "user" and marks[source.id]:
                continue  # the user's own source stays "user"
            source.status = "kept" if marks[source.id] else "dropped"
            kept += source.status == "kept"
            dropped += source.status == "dropped"
        save(course, items)
    report = add(course, added_rows) if added_rows else AddReport()
    return {"kept": kept, "dropped": dropped, "added": report.added, "merged": report.merged}


def rows_from_text(text: str) -> list[dict]:
    """JSON object, JSON array or JSON lines."""
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    if text.startswith("{") and "\n" not in text:
        return [json.loads(text)]
    return [json.loads(line) for line in text.splitlines() if line.strip()]
