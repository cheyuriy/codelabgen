"""`codelabgen report`: a summary of how the course was generated, from state and events."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from codelabgen import sources as srcmod
from codelabgen import topics as topicsmod
from codelabgen.course import Course, atomic_write
from codelabgen.state import StateStore


def events(course: Course) -> list[dict]:
    path = course.events_path
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def duration(start: str | None, end: str | None) -> str:
    if not start or not end:
        return "—"
    seconds = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {seconds:02d}s"


def build(course: Course) -> Path:
    state = StateStore(course).load()
    config = course.load_config()
    log = events(course)

    phase_start: dict[str, str] = {}
    for event in log:
        if event["kind"] == "init":
            phase_start["init"] = event["ts"]
        if event["kind"] == "phase":
            phase_start.setdefault(event["data"]["to"], event["ts"])
    lines = [
        f"# Generation report: {config.topic} {config.version or ''}",
        "",
        f"Course: `{course.root}` · language `{config.language}` · phase **{state.phase}**",
        "",
    ]

    lines += ["## Phases", "", "| Phase | Started | Took |", "|---|---|---|"]
    ordered = sorted(phase_start.items(), key=lambda kv: kv[1])
    for index, (phase, started) in enumerate(ordered):
        end = ordered[index + 1][1] if index + 1 < len(ordered) else None
        lines.append(f"| {phase} | {started[:16].replace('T', ' ')} | {duration(started, end)} |")
    lines.append("")

    items = srcmod.load(course)
    if items:
        statuses = Counter(s.status for s in items)
        types = Counter(s.type for s in srcmod.used(course))
        lines += [
            "## Sources",
            "",
            f"{len(items)} found: " + ", ".join(f"{v} {k}" for k, v in statuses.items()),
            "",
            "Used, by type: " + ", ".join(f"{k} {v}" for k, v in types.most_common()),
            "",
        ]
    found_topics = topicsmod.load(course)
    if found_topics:
        lines += [
            f"{len(found_topics)} topic records, "
            f"{len({topicsmod.key(t.name) for t in found_topics})} distinct topics.",
            "",
        ]

    if state.lessons:
        first_seen: dict[str, str] = {}
        done_at: dict[str, str] = {}
        verify_runs = Counter()
        for event in log:
            lesson = event.get("lesson")
            if not lesson:
                continue
            first_seen.setdefault(lesson, event["ts"])
            if event["kind"] == "advance" and event["data"].get("to") == "done":
                done_at[lesson] = event["ts"]
        runs_dir = course.meta / "runs"
        for lesson in state.lessons:
            folder = runs_dir / lesson
            verify_runs[lesson] = len(list(folder.iterdir())) if folder.is_dir() else 0
        lines += [
            "## Lessons",
            "",
            "| Lesson | Stage | Verify runs | Fix attempts | Review rounds | Took |",
            "|---|---|---|---|---|---|",
        ]
        for lesson_id, lesson in state.lessons.items():
            lines.append(
                f"| {lesson_id} | {lesson.stage} | {verify_runs[lesson_id]} | "
                f"{lesson.fix_attempts} | {lesson.review_rounds} | "
                f"{duration(first_seen.get(lesson_id), done_at.get(lesson_id))} |"
            )
        blocked = {k: v for k, v in state.lessons.items() if v.stage == "blocked"}
        if blocked:
            lines += ["", "Blocked: " + "; ".join(f"{k} ({v.note})" for k, v in blocked.items())]
        lines.append("")

    failed = {k: t for k, t in state.tasks.items() if t.status != "done"}
    if failed:
        lines += ["## Unfinished tasks", ""]
        lines += [
            f"- `{k}`: {t.status}, attempt {t.attempts}" + (f", {t.note}" if t.note else "")
            for k, t in failed.items()
        ]
        lines.append("")
    path = course.meta / "report.md"
    atomic_write(path, "\n".join(lines))
    return path
