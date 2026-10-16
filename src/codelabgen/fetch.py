"""`codelabgen fetch`: download pages once into `.codelabgen/cache/` as Markdown.

Every fetched URL becomes one Markdown file with YAML front matter (url, final
url, title, fetch time, content type). Agents read these files instead of
fetching the same page again. HTML is converted with trafilatura, PDFs with
PyMuPDF; Markdown and plain text are kept as they are.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import yaml

from codelabgen.course import Course, atomic_write
from codelabgen.models import now

USER_AGENT = "codelabgen/0.1 (course research; +https://github.com/cheyuriy/codelabgen)"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MAX_BYTES = 25 * 1024 * 1024
MIN_HOST_INTERVAL_S = 1.0
_last_request: dict[str, float] = {}


class FetchError(Exception):
    pass


@dataclass
class Page:
    url: str
    final_url: str
    title: str | None
    content_type: str
    path: Path
    chars: int
    cached: bool


def cache_dir(course: Course) -> Path:
    return course.meta / "cache"


def cache_path(course: Course, url: str) -> Path:
    digest = hashlib.sha1(url.encode()).hexdigest()[:16]
    host = re.sub(r"[^a-z0-9.-]", "", urlsplit(url).netloc.lower())[:40] or "local"
    return cache_dir(course) / f"{host}-{digest}.md"


def resolve_special(url: str) -> str:
    """Rewrite URLs whose useful form lives elsewhere (arXiv abstract -> PDF)."""
    parts = urlsplit(url)
    if parts.netloc.endswith("arxiv.org") and parts.path.startswith("/abs/"):
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path.replace("/abs/", "/pdf/", 1), "", "")
        )
    return url


def read_cached(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    if text.startswith("---\n"):
        _, header, body = text.split("---\n", 2)
        return yaml.safe_load(header) or {}, body
    return {}, text


def fetch(course: Course, url: str, refresh: bool = False) -> Page:
    path = cache_path(course, url)
    if path.exists() and not refresh:
        meta, body = read_cached(path)
        return Page(
            url,
            meta.get("final_url", url),
            meta.get("title"),
            meta.get("content_type", ""),
            path,
            len(body),
            cached=True,
        )

    target = resolve_special(url)
    response = _get(target)
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    final_url = str(response.url)
    title, body = convert(response.content, content_type, final_url)
    if not body.strip():
        raise FetchError(f"{url}: no readable content ({content_type or 'unknown type'})")

    meta = {
        "url": url,
        "final_url": final_url,
        "title": title,
        "content_type": content_type,
        "fetched": now().isoformat(),
    }
    header = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    atomic_write(path, f"---\n{header}---\n{body.strip()}\n")
    return Page(url, final_url, title, content_type, path, len(body), cached=False)


def _get(url: str) -> httpx.Response:
    host = urlsplit(url).netloc
    wait = MIN_HOST_INTERVAL_S - (time.monotonic() - _last_request.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()
    try:
        with httpx.Client(
            follow_redirects=True, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        raise FetchError(f"{url}: {exc.__class__.__name__}: {exc}") from exc
    if response.status_code >= 400:
        raise FetchError(f"{url}: HTTP {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise FetchError(f"{url}: larger than {MAX_BYTES // 1024 // 1024} MiB")
    return response


def convert(content: bytes, content_type: str, url: str) -> tuple[str | None, str]:
    """(title, Markdown or text) for a downloaded document."""
    path = urlsplit(url).path.lower()
    if content_type == "application/pdf" or path.endswith(".pdf"):
        return pdf_to_text(content)
    if content_type in ("text/markdown", "text/x-markdown") or path.endswith((".md", ".txt")):
        text = content.decode("utf-8", errors="replace")
        heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        return (heading.group(1).strip() if heading else None), text
    if content_type.startswith("text/plain") or content_type in ("application/json",):
        return None, content.decode("utf-8", errors="replace")
    return html_to_markdown(content.decode("utf-8", errors="replace"), url)


def html_to_markdown(html: str, url: str) -> tuple[str | None, str]:
    import trafilatura

    body = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        include_formatting=True,
        include_comments=False,
        favor_recall=True,
    )
    metadata = trafilatura.extract_metadata(html, default_url=url)
    title = metadata.title if metadata else None
    return title, body or ""


def pdf_to_text(content: bytes) -> tuple[str | None, str]:
    import pymupdf

    with pymupdf.open(stream=content, filetype="pdf") as document:
        title = (document.metadata or {}).get("title") or None
        pages = [page.get_text() for page in document]
    text = "\n\n".join(f"<!-- page {i} -->\n{t.strip()}" for i, t in enumerate(pages, 1))
    return title, text


def llms_txt(course: Course, site: str) -> list[Page]:
    """Fetch llms.txt / llms-full.txt from the site root and from the given path, if present."""
    parts = urlsplit(site if "://" in site else f"https://{site}")
    bases = {f"{parts.scheme}://{parts.netloc}"}
    if parts.path.strip("/"):
        bases.add(f"{parts.scheme}://{parts.netloc}/{parts.path.strip('/')}")
    found = []
    for base in sorted(bases):
        for name in ("llms.txt", "llms-full.txt"):
            try:
                page = fetch(course, f"{base}/{name}")
            except FetchError:
                continue
            if page.content_type.startswith("text/html"):
                page.path.unlink(missing_ok=True)  # a soft 404 page, not an llms.txt
                continue
            found.append(page)
    return found
