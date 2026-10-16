"""`codelabgen record <id>`: terminal recordings of a lesson's scenarios.

Each recording in the lesson spec runs headless under asciinema in the lesson
environment, then `agg` turns the `.cast` into a GIF. Markdown links the GIF
(GitHub shows it); the site swaps it for an interactive player. A recording
that contains the value of a secret variable is deleted and the step fails.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from codelabgen import curriculum as cur
from codelabgen import env as envmod
from codelabgen.course import Course

MAX_GIF_BYTES = 8 * 1024 * 1024


@dataclass
class RecordReport:
    recorded: list[Path] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    skipped: str | None = None


def secret_values(course: Course, curriculum, lesson) -> list[str]:
    spec = envmod.load_spec(course, lesson.id)
    secret_names = {v.name for v in envmod.required_vars(curriculum, lesson.id, spec) if v.secret}
    values = envmod.lesson_env(course, lesson)
    return [values[name] for name in secret_names if len(values.get(name, "")) >= 6]


def content_size(cast_text: str, max_cols: int = 100, max_rows: int = 30) -> tuple[int, int]:
    """Terminal size that fits the recorded output, so short runs make small GIFs."""
    output = ""
    for line in cast_text.splitlines()[1:]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, list) and len(event) == 3 and event[1] == "o":
            output += event[2]
    plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07", "", output).replace("\r", "")
    lines = plain.split("\n")
    cols = max((len(line) for line in lines), default=0) + 2
    rows = len(lines) + 1
    return max(40, min(cols, max_cols)), max(5, min(rows, max_rows))


def record(course: Course, lesson_id: str) -> RecordReport:
    curriculum = cur.load(course)
    lesson = cur.find_lesson(curriculum, lesson_id)
    spec = envmod.load_spec(course, lesson_id)
    report = RecordReport()
    if spec is None or not spec.recordings:
        report.skipped = "the spec lists no recordings"
        return report
    missing = [tool for tool in ("asciinema", "agg") if shutil.which(tool) is None]
    if missing:
        report.skipped = f"not installed: {', '.join(missing)} (see codelabgen doctor)"
        return report

    lesson_dir = course.root / lesson.rel_dir
    out_dir = lesson_dir / "docs" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    env = envmod.process_env(course, lesson)
    env.setdefault("TERM", "xterm-256color")
    secrets = secret_values(course, curriculum, lesson)

    for item in spec.recordings:
        cast, gif = out_dir / f"{item.name}.cast", out_dir / f"{item.name}.gif"
        # What the viewer sees typed, then the real command run inside the lesson's project.
        shown = f"uv run {item.cmd}"
        real = shlex.join(
            ["uv", "run", "--frozen", "--package", lesson.project, *shlex.split(item.cmd)]
        )
        if item.input_script:
            real = f"printf %s {shlex.quote(item.input_script)} | {real}"
        script = f"printf '$ %s\\n' {shlex.quote(shown)}; {real}"
        argv = [
            "asciinema",
            "rec",
            "--headless",
            "--return",
            "--overwrite",
            "--quiet",
            "--idle-time-limit",
            "1",
            "--window-size",
            "100x30",
            "--command",
            f"bash -c {shlex.quote(script)}",
            str(cast),
        ]
        try:
            proc = subprocess.run(
                argv,
                cwd=lesson_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=item.max_seconds + 30,
            )
        except subprocess.TimeoutExpired:
            cast.unlink(missing_ok=True)
            report.problems.append(f"{item.name}: longer than {item.max_seconds}s")
            continue
        if proc.returncode != 0 or not cast.exists():
            report.problems.append(f"{item.name}: asciinema failed: {proc.stderr.strip()[-300:]}")
            continue
        text = cast.read_text(errors="replace")
        if any(secret in text for secret in secrets):
            cast.unlink()
            report.problems.append(f"{item.name}: the recording shows a secret value; deleted")
            continue
        cols, rows = content_size(text)
        proc = subprocess.run(
            [
                "agg",
                "--font-size",
                "14",
                "--last-frame-duration",
                "3",
                "--cols",
                str(cols),
                "--rows",
                str(rows),
                str(cast),
                str(gif),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            report.problems.append(f"{item.name}: agg failed: {proc.stderr.strip()[-300:]}")
            continue
        if gif.stat().st_size > MAX_GIF_BYTES:
            report.problems.append(
                f"{item.name}: GIF is {gif.stat().st_size // 1024} KiB, over the "
                f"{MAX_GIF_BYTES // 1024 // 1024} MiB cap; shorten the scenario"
            )
            continue
        report.recorded += [cast, gif]
    return report
