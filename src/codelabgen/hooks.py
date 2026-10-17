"""Claude Code hook handlers (`codelabgen hook <event>`, input JSON on stdin).

pre-tool-use   blocks Write/Edit on files only the CLI may change (exit 2 + reason)
subagent-stop  logs the finished subagent in the course's event log, if a course
               can be found from the hook's working directory or $CODELABGEN_COURSE
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from codelabgen.course import META_DIR, Course, CourseNotFound

PROTECTED = {
    "state.json": "codelabgen state … (set, fail, block, phase, task …)",
    "events.jsonl": "codelabgen state log",
    "sources.jsonl": "codelabgen sources add / apply / keep-proposed",
}


def read_input() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def pre_tool_use(data: dict) -> int:
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path:
        return 0
    file = Path(path)
    if file.parent.name == META_DIR and file.name in PROTECTED:
        print(
            f"{file.name} is managed by the codelabgen CLI and must not be edited directly. "
            f"Use: {PROTECTED[file.name]}.",
            file=sys.stderr,
        )
        return 2
    return 0


def subagent_stop(data: dict) -> int:
    from codelabgen.state import StateStore

    try:
        course = Course.find(None) if not data.get("cwd") else find_from(Path(data["cwd"]))
    except CourseNotFound:
        return 0
    fields = {k: data[k] for k in ("agent_type", "agent_id", "session_id") if data.get(k)}
    try:
        StateStore(course).log("subagent-stop", **fields)
    except OSError:
        pass
    return 0


def find_from(cwd: Path) -> Course:
    try:
        return Course.find(None)  # $CODELABGEN_COURSE first
    except CourseNotFound:
        pass
    for candidate in (cwd, *cwd.parents):
        if (candidate / META_DIR / "config.yaml").is_file():
            return Course(candidate)
    raise CourseNotFound(str(cwd))


HANDLERS = {"pre-tool-use": pre_tool_use, "subagent-stop": subagent_stop}
