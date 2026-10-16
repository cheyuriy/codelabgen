"""Research helpers: package registries, repo clones at the pinned version, transcripts."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import httpx

from codelabgen.course import Course, atomic_write
from codelabgen.fetch import USER_AGENT, cache_dir


class ResearchError(Exception):
    pass


# --- package registries ------------------------------------------------------------------


def pkg_info(ecosystem: str, name: str) -> dict:
    """Latest version, release date and project links from the package registry."""
    headers = {"User-Agent": USER_AGENT}
    try:
        if ecosystem == "pypi":
            data = (
                httpx.get(f"https://pypi.org/pypi/{name}/json", headers=headers, timeout=20)
                .raise_for_status()
                .json()
            )
            info = data["info"]
            files = data["releases"].get(info["version"]) or []
            urls = info.get("project_urls") or {}
            return {
                "ecosystem": "pypi",
                "name": info["name"],
                "version": info["version"],
                "released": files[0]["upload_time"][:10] if files else None,
                "summary": info.get("summary"),
                "requires_python": info.get("requires_python"),
                "homepage": info.get("home_page") or urls.get("Homepage"),
                "docs": urls.get("Documentation") or urls.get("Docs"),
                "repository": urls.get("Repository") or urls.get("Source") or urls.get("Code"),
                "recent_versions": sorted(data["releases"], key=_version_key)[-10:],
            }
        if ecosystem == "npm":
            data = (
                httpx.get(f"https://registry.npmjs.org/{name}", headers=headers, timeout=20)
                .raise_for_status()
                .json()
            )
            latest = data["dist-tags"]["latest"]
            repo = data.get("repository") or {}
            return {
                "ecosystem": "npm",
                "name": name,
                "version": latest,
                "released": (data.get("time") or {}).get(latest, "")[:10] or None,
                "summary": data.get("description"),
                "homepage": data.get("homepage"),
                "repository": repo.get("url") if isinstance(repo, dict) else repo,
                "recent_versions": sorted(data.get("versions", {}), key=_version_key)[-10:],
            }
        if ecosystem == "crates":
            data = (
                httpx.get(f"https://crates.io/api/v1/crates/{name}", headers=headers, timeout=20)
                .raise_for_status()
                .json()
            )
            crate = data["crate"]
            return {
                "ecosystem": "crates",
                "name": name,
                "version": crate["max_stable_version"],
                "released": crate.get("updated_at", "")[:10] or None,
                "summary": crate.get("description"),
                "homepage": crate.get("homepage"),
                "docs": crate.get("documentation"),
                "repository": crate.get("repository"),
            }
        if ecosystem == "go":
            data = (
                httpx.get(
                    f"https://proxy.golang.org/{name.lower()}/@latest", headers=headers, timeout=20
                )
                .raise_for_status()
                .json()
            )
            return {
                "ecosystem": "go",
                "name": name,
                "version": data["Version"],
                "released": data.get("Time", "")[:10] or None,
                "docs": f"https://pkg.go.dev/{name}",
            }
    except httpx.HTTPError as exc:
        raise ResearchError(f"{ecosystem} {name}: {exc}") from exc
    raise ResearchError(f"unknown ecosystem {ecosystem!r}: use pypi, npm, crates or go")


def _version_key(version: str) -> tuple:
    return tuple(int(p) if p.isdigit() else -1 for p in re.split(r"[.\-+]", version))


# --- repo clones ---------------------------------------------------------------------------

INTERESTING = (
    "examples",
    "example",
    "samples",
    "cookbook",
    "tests",
    "test",
    "docs",
    "notebooks",
    "tutorials",
    "templates",
)


def repo_slug(url: str) -> str:
    match = re.search(r"github\.com[/:]([^/]+)/([^/.#?]+)", url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    if re.fullmatch(r"[\w.-]+/[\w.-]+", url):
        return url
    raise ResearchError(f"not a GitHub repository: {url}")


def matching_tag(url: str, version: str | None, package: str | None = None) -> str | None:
    """The tag that marks `version`: v1.2.3, 1.2.3, or monorepo forms like pkg==1.2.3."""
    if not version:
        return None
    proc = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", url], capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        raise ResearchError(f"git ls-remote {url}: {proc.stderr.strip()[:200]}")
    tags = [
        line.split("refs/tags/", 1)[1] for line in proc.stdout.splitlines() if "refs/tags/" in line
    ]
    candidates = [version, f"v{version}"]
    if package:
        candidates += [
            f"{package}=={version}",
            f"{package}@{version}",
            f"{package}-v{version}",
            f"{package}/v{version}",
            f"{package}-{version}",
        ]
    for candidate in candidates:
        if candidate in tags:
            return candidate
    loose = [t for t in tags if re.search(rf"(^|[^\d.]){re.escape(version)}$", t)]
    return loose[0] if len(loose) == 1 else None


def clone(course: Course, url: str, ref: str | None = None, package: str | None = None) -> dict:
    """Shallow clone at `ref` (or the tag of the pinned version, or the default branch)."""
    slug = repo_slug(url)
    git_url = f"https://github.com/{slug}.git" if "://" not in url else url
    version = course.load_config().version
    tag = ref or matching_tag(git_url, version, package)
    target = course.meta / "repos" / f"{slug.replace('/', '__')}@{tag or 'default'}"
    if not target.exists():
        argv = ["git", "clone", "--depth", "1", "--quiet"]
        if tag:
            argv += ["--branch", tag]
        proc = subprocess.run(
            [*argv, git_url, str(target)], capture_output=True, text=True, timeout=600
        )
        if proc.returncode != 0:
            shutil.rmtree(target, ignore_errors=True)
            raise ResearchError(f"git clone {slug}: {proc.stderr.strip()[:300]}")
    found = {}
    for path in sorted(target.rglob("*")):
        if path.is_dir() and path.name.lower() in INTERESTING and ".git" not in path.parts:
            depth = len(path.relative_to(target).parts)
            if depth <= 4:
                files = sum(1 for p in path.rglob("*") if p.is_file())
                found[path.relative_to(target).as_posix()] = files
    return {
        "repo": slug,
        "ref": tag or "default branch",
        "pinned_version": version,
        "version_matched": bool(tag) and not ref,
        "path": str(target.relative_to(course.root)),
        "interesting_dirs": found,
    }


# --- transcripts -------------------------------------------------------------------------


def transcript(course: Course, url: str, languages: str = "en.*,ru.*") -> Path:
    """Subtitles of a talk as plain text in the cache (yt-dlp, run through uvx if missing)."""
    out_dir = cache_dir(course) / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    yt_dlp = ["yt-dlp"] if shutil.which("yt-dlp") else ["uvx", "yt-dlp"]
    template = str(out_dir / "%(id)s.%(ext)s")
    argv = [
        *yt_dlp,
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        languages,
        "--sub-format",
        "vtt",
        "--print",
        "after_move:%(id)s\t%(title)s",
        "--no-simulate",
        "-o",
        template,
        url,
    ]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise ResearchError(f"yt-dlp: {proc.stderr.strip()[-300:]}")
    video_id, _, title = proc.stdout.strip().splitlines()[-1].partition("\t")
    subtitles = sorted(out_dir.glob(f"{video_id}*.vtt"))
    if not subtitles:
        raise ResearchError(f"{url}: no subtitles available")
    preferred = next(
        (s for s in subtitles if ".en" in s.name and "orig" not in s.name), subtitles[0]
    )
    text = vtt_to_text(preferred.read_text(errors="replace"))
    target = out_dir / f"{video_id}.md"
    atomic_write(
        target,
        f"---\nurl: {url}\ntitle: {title!r}\nsubtitles: {preferred.name}\n"
        f"---\n# {title}\n\n{text}\n",
    )
    for sub in subtitles:
        sub.unlink()
    return target


def vtt_to_text(vtt: str) -> str:
    """Plain text from WebVTT; drops timings, tags and the repeats of auto-captions."""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        if line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    paragraphs, current = [], []
    for line in lines:
        current.append(line)
        if len(current) >= 8:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)
