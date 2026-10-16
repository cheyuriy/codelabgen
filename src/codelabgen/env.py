"""Layered environment: course `.env`, then the lesson's `.env` (PLAN.md §3.1)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import dotenv_values

from codelabgen.course import Course
from codelabgen.curriculum import Lesson
from codelabgen.models import Curriculum, EnvVar, LessonSpec


@dataclass
class EnvReport:
    lesson: str
    required: list[EnvVar]
    missing: list[str]  # absent or empty


def spec_path(course: Course, lesson_id: str) -> Path:
    return course.meta / "lessons" / lesson_id / "spec.yaml"


def load_spec(course: Course, lesson_id: str) -> LessonSpec | None:
    path = spec_path(course, lesson_id)
    if not path.is_file():
        return None
    return LessonSpec.model_validate(yaml.safe_load(path.read_text()))


def required_vars(curriculum: Curriculum, lesson_id: str, spec: LessonSpec | None) -> list[EnvVar]:
    found = {var.name: var for var in curriculum.env if not var.lessons or lesson_id in var.lessons}
    for var in spec.env if spec else []:
        found[var.name] = var
    return list(found.values())


def lesson_env(course: Course, lesson: Lesson) -> dict[str, str]:
    """Values from the course `.env`, overridden by the lesson's `.env`."""
    values: dict[str, str] = {}
    for path in (course.root / ".env", course.root / lesson.rel_dir / ".env"):
        if path.is_file():
            values.update({k: v for k, v in dotenv_values(path).items() if v is not None})
    return values


def process_env(course: Course, lesson: Lesson) -> dict[str, str]:
    """Environment for lesson commands: ours, minus the plugin's venv, plus the lesson env."""
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "CODELABGEN_COURSE")}
    env.update(lesson_env(course, lesson))
    return env


def check(course: Course, curriculum: Curriculum, lesson: Lesson) -> EnvReport:
    spec = load_spec(course, lesson.id)
    required = required_vars(curriculum, lesson.id, spec)
    values = lesson_env(course, lesson)
    missing = [var.name for var in required if not values.get(var.name)]
    return EnvReport(lesson.id, required, missing)


def render_example(variables: list[EnvVar], header: str) -> str:
    """The text of a `.env.example` file: one commented entry per variable."""
    lines = [f"# {header}", "# Copy to .env and fill in the values. .env is ignored by git.", ""]
    for var in variables:
        lines.append(f"# {var.description}")
        if var.where_to_get:
            lines.append(f"# Where to get it: {var.where_to_get}")
        if var.lessons:
            lines.append(f"# Used in lessons: {', '.join(var.lessons)}")
        if var.secret:
            lines.append("# Secret: never commit the real value.")
        lines.append(f"{var.name}={var.default or ''}")
        lines.append("")
    return "\n".join(lines)
