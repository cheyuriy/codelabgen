"""`codelabgen scaffold`: course, module and lesson directories from the curriculum.

Generated files (compose, ruff config, module pyprojects, .env.example) are
rewritten on every run. Files the agents own (lesson code, docs, a lesson's
pyproject once created) are only created when missing.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from codelabgen import curriculum as cur
from codelabgen import env as envmod
from codelabgen import runtimes, services
from codelabgen.course import Course, atomic_write
from codelabgen.curriculum import Lesson
from codelabgen.i18n import labels
from codelabgen.models import Curriculum, CurriculumNode
from codelabgen.state import StateStore

TEMPLATES = files("codelabgen") / "templates"
_jinja = Environment(undefined=StrictUndefined, keep_trailing_newline=True)
_jinja.filters["shq"] = shlex.quote


class ScaffoldError(Exception):
    pass


@dataclass
class ScaffoldReport:
    written: list[str] = field(default_factory=list)  # regenerated files
    created: list[str] = field(default_factory=list)  # files created because missing
    copied_from: dict[str, str] = field(default_factory=dict)  # lesson -> source lesson

    def add(self, course: Course, path: Path, created: bool) -> None:
        (self.created if created else self.written).append(str(path.relative_to(course.root)))


def render(name: str, **context) -> str:
    return _jinja.from_string((TEMPLATES / name).read_text()).render(**context)


def course_slug(name: str) -> str:
    """A Docker Compose project name: lowercase letters, digits and dashes."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "course"


def lesson_services(curriculum: Curriculum, course: Course) -> dict[str, list[str]]:
    """Services per lesson: from the curriculum node plus the lesson spec, if any."""
    result = {}
    for lesson in cur.lessons(curriculum):
        spec = envmod.load_spec(course, lesson.id)
        result[lesson.id] = list(
            dict.fromkeys(lesson.node.services + (spec.services if spec else []))
        )
    return result


def scaffold_course(course: Course) -> ScaffoldReport:
    curriculum = cur.load(course)
    config = course.load_config()
    report = ScaffoldReport()
    root = course.root

    used = sorted({s for names in lesson_services(curriculum, course).values() for s in names})
    try:
        catalog = services.resolve(used, course.meta)
    except services.UnknownService as exc:
        raise ScaffoldError(str(exc)) from exc
    if config.runtime.port_offset is None:
        # New courses get their own host ports. A course whose .env already exists keeps
        # the standard ports its .env was written for.
        exists = (root / ".env").exists()
        config.runtime.port_offset = 0 if exists else services.choose_offset(root)
    catalog = [services.with_offset(s, config.runtime.port_offset) for s in catalog]
    if config.runtime.services != used or config != course.load_config():
        config.runtime.services = used
        course.save_config(config)

    runtime = runtimes.for_course(course)
    gitignore = (TEMPLATES / "gitignore").read_text() + "".join(
        f"{line}\n" for line in runtime.gitignore
    )
    write(course, report, root / ".gitignore", gitignore)
    for name, text in runtime.course_files().items():
        write(course, report, root / name, text)
    compose = root / "docker-compose.yml"
    if catalog:
        write(course, report, compose, services.compose_yaml(catalog, course_slug(root.name)))
    elif compose.exists():
        compose.unlink()

    course_vars = [v for v in curriculum.env if v.scope == "course"]
    course_vars += [
        v for s in catalog for v in s.env if v.name not in {c.name for c in course_vars}
    ]
    example = envmod.render_example(course_vars, f"Environment for the course '{config.topic}'")
    write(course, report, root / ".env.example", example)
    if not (root / ".env").exists():
        own_values = example.replace(
            "# Copy to .env and fill in the values. .env is ignored by git.",
            "# Your values. This file is ignored by git; .env.example lists every variable.",
        )
        create(course, report, root / ".env", own_values)

    for module in curriculum.modules:
        module_lessons = [lesson for lesson in cur.lessons(curriculum) if lesson.module is module]
        scaffold_module(course, report, module, module_lessons)
        for lesson in module_lessons:
            scaffold_lesson_dir(course, curriculum, report, lesson, copy_code=False)

    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
        report.created.append(".git")

    StateStore(course).register([lesson.id for lesson in cur.lessons(curriculum)])
    return report


def scaffold_module(
    course: Course, report: ScaffoldReport, module: CurriculumNode, lessons: list[Lesson]
) -> None:
    module_dir = course.root / cur.node_dir_name(module)
    members = [lesson.rel_dir.relative_to(lesson.module_rel_dir).as_posix() for lesson in lessons]
    for name, text in runtimes.for_course(course).module_files(module, members).items():
        write(course, report, module_dir / name, text)


def scaffold_lesson(course: Course, lesson_id: str) -> ScaffoldReport:
    """Create or complete one lesson directory (idempotent)."""
    curriculum = cur.load(course)
    report = ScaffoldReport()
    lesson = cur.find_lesson(curriculum, lesson_id)
    scaffold_lesson_dir(course, curriculum, report, lesson, copy_code=True)
    return report


def scaffold_lesson_dir(
    course: Course,
    curriculum: Curriculum,
    report: ScaffoldReport,
    lesson: Lesson,
    copy_code: bool,
) -> None:
    """Create what is missing. With copy_code, an extending lesson that still has only
    the placeholder code gets the code of the lesson it extends."""
    runtime = runtimes.for_course(course)
    lesson_dir = course.root / lesson.rel_dir
    (lesson_dir / "docs").mkdir(parents=True, exist_ok=True)

    example = lesson.node.example
    extends = example.from_lesson if example and example.mode == "extend" else None
    if copy_code and extends and runtimes.is_stub(runtime, lesson_dir, lesson):
        source = cur.find_lesson(curriculum, extends)
        source_dir = course.root / source.rel_dir
        if runtimes.is_stub(runtime, source_dir, source):
            raise ScaffoldError(
                f"lesson {lesson.id} extends {source.id}, but {source.id} has no code yet"
            )
        for rel in runtime.stub_files(lesson):
            stub = lesson_dir / rel
            stub.unlink(missing_ok=True)
            for parent in stub.parents:  # folders the placeholder leaves empty
                if parent == lesson_dir or not parent.is_dir() or any(parent.iterdir()):
                    break
                parent.rmdir()
        copy_lesson_code(course, runtime, source, lesson)
        report.copied_from[lesson.id] = source.id

    for rel, text in runtime.lesson_files(lesson).items():
        path = lesson_dir / rel
        if not path.exists():
            create(course, report, path, text)
    (lesson_dir / "tests").mkdir(exist_ok=True)
    readme = lesson_dir / "README.md"
    if not readme.exists():
        text = labels(course.load_config().language)
        create(course, report, readme, render("lesson_readme.md.j2", lesson=lesson, labels=text))

    spec = envmod.load_spec(course, lesson.id)
    lesson_vars = [
        v for v in envmod.required_vars(curriculum, lesson.id, spec) if v.scope == "lesson"
    ]
    env_example = lesson_dir / ".env.example"
    if lesson_vars:
        header = f"Lesson {lesson.id} variables; they override the course .env"
        write(course, report, env_example, envmod.render_example(lesson_vars, header))
    elif env_example.exists():
        env_example.unlink()


def rename_tokens(source: Lesson, target: Lesson) -> dict[str, str]:
    return {
        source.package: target.package,
        source.project: target.project,
        f"Lesson {source.id}: {source.node.title}": f"Lesson {target.id}: {target.node.title}",
    }


TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".go",
    ".mod",
    ".sum",
    ".rs",
    ".sql",
    ".sh",
    ".cfg",
    ".ini",
}


def copy_lesson_code(course: Course, runtime, source: Lesson, target: Lesson) -> None:
    """Start a lesson from an earlier lesson's code, renaming its package everywhere."""
    src_dir, dst_dir = course.root / source.rel_dir, course.root / target.rel_dir
    for item in src_dir.iterdir():
        if item.name in runtimes.NOT_CODE:
            continue
        destination = dst_dir / item.name
        if item.is_dir():
            shutil.copytree(
                item,
                destination,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(*runtimes.CACHE_DIRS),
            )
        else:
            shutil.copy2(item, destination)
    for old, new in runtime.path_renames(source, target):
        if (dst_dir / old).exists() and not (dst_dir / new).exists():
            (dst_dir / old).rename(dst_dir / new)
    replacements = rename_tokens(source, target)
    for path in dst_dir.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES and "docs" not in path.parts:
            text = path.read_text()
            new_text = text
            for old, new in replacements.items():
                new_text = new_text.replace(old, new)
            if new_text != text:
                path.write_text(new_text)


def write(course: Course, report: ScaffoldReport, path: Path, text: str) -> None:
    existed = path.exists()
    if existed and path.read_text() == text:
        return
    atomic_write(path, text)
    report.add(course, path, created=not existed)


def create(course: Course, report: ScaffoldReport, path: Path, text: str) -> None:
    atomic_write(path, text)
    report.add(course, path, created=True)
