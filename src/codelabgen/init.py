"""`codelabgen init`: create a course directory with an empty `.codelabgen/`."""

from __future__ import annotations

import os
from pathlib import Path

from codelabgen.course import META_DIR, Course, atomic_write, dump_json
from codelabgen.models import Config, State
from codelabgen.state import StateStore


class InitError(Exception):
    pass


def plugin_root() -> Path | None:
    """The codelabgen plugin checkout, if this package runs from one."""
    if env := os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return Path(env).resolve()
    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / ".claude-plugin" / "plugin.json").is_file() else None


def init_course(
    target: Path,
    topic: str,
    language: str = "en",
    version: str | None = None,
    sources: list[str] | None = None,
    force: bool = False,
) -> Course:
    target = target.expanduser().resolve()
    root = plugin_root()
    if root and (target == root or root in target.parents):
        raise InitError(f"the course must live outside the plugin directory ({root})")
    if (target / META_DIR).exists():
        raise InitError(f"{target} is already a codelabgen course; use /codelabgen:resume")
    if target.exists() and not target.is_dir():
        raise InitError(f"{target} exists and is not a directory")
    if target.exists() and any(target.iterdir()) and not force:
        raise InitError(f"{target} is not empty; pass --force to use it anyway")

    course = Course(target)
    course.meta.mkdir(parents=True, exist_ok=True)
    config = Config(
        topic=topic,
        version=version,
        language=language,
        target=str(target),
        user_sources=sources or [],
    )
    course.save_config(config)
    atomic_write(course.state_path, dump_json(State()))
    course.events_path.touch()
    StateStore(course).log("init", topic=topic, language=language, version=version)
    return course
