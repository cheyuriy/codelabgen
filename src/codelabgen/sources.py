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
            if existing.title == existing.url and source.title != source.url:
                existing.title = source.title  # a user-added URL gets its real title
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


# --- digests --------------------------------------------------------------------------------

USED = ("kept", "user")
DIGEST_SECTIONS = ("Summary", "Topics covered", "Code examples", "Gaps / dig deeper")


def digests_dir(course: Course) -> Path:
    return course.meta / "sources"


def digest_path(course: Course, source_id: str) -> Path:
    return digests_dir(course) / f"{source_id}.md"


def used(course: Course) -> list[Source]:
    """The sources the course is built from: kept by the review or added by the user."""
    return [s for s in load(course) if s.status in USED]


def read_digest(path: Path) -> tuple[dict, str]:
    import yaml

    text = path.read_text()
    if not text.startswith("---\n"):
        return {}, text
    _, header, body = text.split("---\n", 2)
    return yaml.safe_load(header) or {}, body


def digest_problems(course: Course, source: Source) -> list[str]:
    path = digest_path(course, source.id)
    if not path.is_file():
        return ["missing"]
    meta, body = read_digest(path)
    problems = []
    if meta.get("id") != source.id:
        problems.append(f"front matter id is {meta.get('id')!r}")
    headings = set(re.findall(r"^## (.+?)\s*$", body, re.MULTILINE))
    problems += [f"no '## {name}' section" for name in DIGEST_SECTIONS if name not in headings]
    return problems


def pending_digests(course: Course) -> list[Source]:
    return [s for s in used(course) if digest_problems(course, s)]


def batches(course: Course, size: int, only_pending: bool = True) -> list[list[str]]:
    """Source ids in groups of `size` for parallel extractors, in type order, so a group
    mostly holds sources of one type and few groups are left half full."""
    chosen = pending_digests(course) if only_pending else used(course)
    order = {t: i for i, t in enumerate(TYPE_ORDER)}
    ids = [s.id for s in sorted(chosen, key=lambda s: order.get(s.type, 99))]
    return [ids[i : i + size] for i in range(0, len(ids), size)]


def lesson_usage(course: Course) -> dict[str, list[str]]:
    """Source id -> lessons whose curriculum node cites it."""
    from codelabgen import curriculum as cur

    if not (course.meta / "curriculum.yaml").is_file():
        return {}
    usage: dict[str, list[str]] = {}
    try:
        lessons = cur.lessons(cur.load(course))
    except cur.CurriculumError:
        return {}
    for lesson in lessons:
        for source_id in lesson.node.sources:
            usage.setdefault(source_id, []).append(lesson.id)
    return usage


def build_index(course: Course) -> Path:
    """`.codelabgen/sources/index.md`: digests grouped by role, with lesson usage."""
    usage = lesson_usage(course)
    items = used(course)
    lines = [
        "# Source digests",
        "",
        "One digest per source the course uses, in `.codelabgen/sources/<id>.md`. "
        "Grouped by role; a source appears under each of its roles.",
        "",
    ]
    for role in ("structure", "code-truth", "concepts", "pitfalls"):
        group = [s for s in items if role in s.roles]
        if not group:
            continue
        lines += [
            f"## {role}",
            "",
            "| Digest | Type | Score | Lessons | Summary |",
            "|---|---|---|---|---|",
        ]
        for s in sorted(group, key=lambda x: -x.score):
            path = digest_path(course, s.id)
            summary = ""
            if path.is_file():
                _, body = read_digest(path)
                match = re.search(
                    r"^## Summary\s*\n+(.+?)(?:\n\n|\n## |\Z)", body, re.MULTILINE | re.DOTALL
                )
                summary = " ".join(match.group(1).split())[:160] if match else ""
            link = f"[{s.title}]({s.id}.md)" if path.is_file() else f"{s.title} (no digest yet)"
            lines.append(
                f"| {link} | {s.type} | {s.score:.2f} | "
                f"{', '.join(usage.get(s.id, [])) or '—'} | {summary} |"
            )
        lines.append("")
    path = digests_dir(course) / "index.md"
    atomic_write(path, "\n".join(lines))
    return path


def keep_proposed(course: Course, min_score: float) -> dict:
    """Keep the still-proposed sources scoring at least `min_score`, drop the rest.

    Used by extensions: their new sources are digested before the user's review,
    and the user can still drop any of them at the extension's gate.
    """
    kept, dropped = [], []
    with FileLock(str(course.meta / "sources.lock"), timeout=30):
        items = load(course)
        for source in items:
            if source.status != "proposed":
                continue
            if source.score >= min_score:
                source.status = "kept"
                kept.append(source.id)
            else:
                source.status = "dropped"
                dropped.append(source.id)
        save(course, items)
    return {"kept": kept, "dropped": dropped}


def overview(course: Course) -> list[dict]:
    """Sources grouped by type, as the orchestrator presents them to the user."""
    items = load(course)
    groups = []
    for type_ in TYPE_ORDER:
        group = [s for s in items if s.type == type_]
        if not group:
            continue
        groups.append(
            {
                "type": type_,
                "sources": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "url": s.url,
                        "score": s.score,
                        "reason": s.reason,
                        "status": s.status,
                        "default_keep": s.status in ("kept", "user")
                        or (s.status == "proposed" and s.score >= KEEP_THRESHOLD),
                    }
                    for s in group
                ],
            }
        )
    return groups


def decide(course: Course, keep: list[str], drop: list[str], default: bool = False) -> dict:
    """Set sources to kept or dropped by id. With `default`, every still-proposed source
    is decided by its score first (the sheet's default ticks); `keep`/`drop` then override."""
    with FileLock(str(course.meta / "sources.lock"), timeout=30):
        items = load(course)
        known = {s.id for s in items}
        unknown = [i for i in [*keep, *drop] if i not in known]
        if unknown:
            raise SourcesError(f"unknown source ids: {', '.join(unknown)}")
        for source in items:
            if default and source.status == "proposed":
                source.status = "kept" if source.score >= KEEP_THRESHOLD else "dropped"
            if source.id in keep and source.status != "user":
                source.status = "kept"
            if source.id in drop:
                source.status = "dropped"
        save(course, items)
    counts: dict[str, int] = {}
    for source in items:
        counts[source.status] = counts.get(source.status, 0) + 1
    return counts
