"""`codelabgen site build|serve`: the MkDocs site, with a pinned toolchain run through uvx."""

from __future__ import annotations

import os
import subprocess

from codelabgen.course import Course
from codelabgen.toc import SITE_MKDOCS, SITE_PLUGINS


def mkdocs_argv(action: str, *extra: str) -> list[str]:
    argv = ["uvx", "--from", SITE_MKDOCS]
    for plugin in SITE_PLUGINS:
        argv += ["--with", plugin]
    return [*argv, "mkdocs", action, *extra]


def run(course: Course, action: str, extra: list[str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env["DISABLE_MKDOCS_2_WARNING"] = "true"  # pinned toolchain; the notice is noise
    capture = action == "build"
    return subprocess.run(
        mkdocs_argv(action, *extra), cwd=course.root, env=env, text=True, capture_output=capture
    )
