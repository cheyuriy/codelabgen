"""Extending a finished course: deepen a topic or add new ones.

An extension lives in `.codelabgen/extensions/<n>/`:

  request.md       what the user asked for
  gaps.md          gap analysis (gap-analyst)
  hunt.yaml        which source types to search, with a focus each (gap-analyst)
  curriculum.yaml  the proposed full curriculum (curriculum-architect, extend mode)
  delta.md         the proposed change, as the user reviews it (`extend diff`)

Stages: gaps → research → digests → delta → gate → lessons → done. `extend apply`
merges the proposed curriculum into the course: new lessons are registered,
changed lessons go back to `pending`, lessons whose example builds on a changed
one become `stale`, and — only with --allow-renumber — lessons whose id changes
are moved, with their package, specs, runs and links rewritten.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from codelabgen import curriculum as cur
from codelabgen import runtimes
from codelabgen.course import Course, atomic_write
from codelabgen.curriculum import Lesson
from codelabgen.models import (
    EXTENSION_STAGES,
    ExtensionState,
    LessonState,
    Phase,
    Stage,
    lesson_sort_key,
    now,
)
from codelabgen.scaffold import TEXT_SUFFIXES
from codelabgen.state import StateError, StateStore


class ExtensionError(Exception):
    pass


def ext_dir(course: Course, number: int) -> Path:
    return course.meta / "extensions" / str(number)


def proposed_path(course: Course, number: int) -> Path:
    return ext_dir(course, number) / "curriculum.yaml"


def current(course: Course) -> ExtensionState:
    extension = StateStore(course).load().extension
    if extension is None:
        raise ExtensionError("no extension in progress; start one with `codelabgen extend start`")
    return extension


# --- lifecycle --------------------------------------------------------------------------------


def git_dirty(course: Course) -> list[str]:
    if not (course.root / ".git").exists():
        return []
    proc = subprocess.run(
        ["git", "-C", str(course.root), "status", "--porcelain"], capture_output=True, text=True
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def start(course: Course, request: str) -> ExtensionState:
    store = StateStore(course)
    state = store.load()
    if state.extension:
        raise ExtensionError(
            f"extension {state.extension.id} is still in progress (stage {state.extension.stage})"
        )
    if state.phase not in (Phase.LESSONS, Phase.ASSEMBLY, Phase.DONE) or any(
        lesson.stage is not Stage.DONE for lesson in state.lessons.values()
    ):
        raise ExtensionError("only a finished course can be extended: all lessons done")
    dirty = git_dirty(course)
    if dirty:
        raise ExtensionError(
            "the course has uncommitted changes; commit or stash them first:\n"
            + "\n".join(dirty[:10])
        )
    with store.transaction() as state:
        extension = ExtensionState(id=len(state.extensions) + 1, request=request)
        state.extensions.append(extension)
    folder = ext_dir(course, extension.id)
    folder.mkdir(parents=True, exist_ok=True)
    atomic_write(folder / "request.md", f"# Extension {extension.id}\n\n{request.strip()}\n")
    store.log("extension-start", number=extension.id, request=request)
    return extension


def set_stage(course: Course, stage: str, approved: bool = False) -> ExtensionState:
    store = StateStore(course)
    with store.transaction() as state:
        extension = state.extension
        if extension is None:
            raise ExtensionError("no extension in progress")
        here, there = EXTENSION_STAGES.index(extension.stage), EXTENSION_STAGES.index(stage)
        if there != here + 1:
            raise ExtensionError(
                f"extension stage {extension.stage} can only move to {EXTENSION_STAGES[here + 1]}"
            )
        if extension.stage == "gate":
            raise ExtensionError("leave the review gate with `codelabgen extend apply`")
        extension.stage = stage
        if stage == "done":
            extension.finished = now()
    store.log("extension-stage", number=extension.id, stage=stage, approved=approved)
    return extension


# --- the proposed change ----------------------------------------------------------------------


def identity(lesson: Lesson) -> tuple[str, ...]:
    """A lesson is the same lesson when its slug path is the same, whatever its id."""
    return tuple(node.slug for node in (*lesson.ancestors, lesson.node))


CONTENT_FIELDS = ("summary", "objectives", "example", "services")


@dataclass
class Delta:
    added: list[Lesson] = field(default_factory=list)
    removed: list[Lesson] = field(default_factory=list)
    changed: list[tuple[Lesson, Lesson, list[str]]] = field(default_factory=list)
    retitled: list[tuple[Lesson, Lesson]] = field(default_factory=list)
    moved: list[tuple[Lesson, Lesson]] = field(default_factory=list)  # old, new (dir differs)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.retitled or self.moved)


def compute_delta(course: Course, proposed: Path) -> Delta:
    old = {identity(lesson): lesson for lesson in cur.lessons(cur.load(course))}
    new = {identity(lesson): lesson for lesson in cur.lessons(cur.load(course, proposed))}
    delta = Delta()
    for key, lesson in new.items():
        before = old.get(key)
        if before is None:
            delta.added.append(lesson)
            continue
        if before.rel_dir != lesson.rel_dir:
            delta.moved.append((before, lesson))
        fields = [
            name
            for name in CONTENT_FIELDS
            if getattr(before.node, name) != getattr(lesson.node, name)
            and not (name == "example" and same_example(before, lesson, old, new))
        ]
        if fields:
            delta.changed.append((before, lesson, fields))
        elif before.node.title != lesson.node.title:
            delta.retitled.append((before, lesson))
    delta.removed = [lesson for key, lesson in old.items() if key not in new]
    return delta


def same_example(before: Lesson, after: Lesson, old: dict, new: dict) -> bool:
    """Examples are equal if only the id of the lesson they extend changed (a renumber)."""
    a, b = before.node.example, after.node.example
    if a is None or b is None or (a.name, a.mode) != (b.name, b.mode):
        return False
    if a.from_lesson == b.from_lesson:
        return True
    old_by_id = {lesson.id: key for key, lesson in old.items()}
    new_by_id = {lesson.id: key for key, lesson in new.items()}
    return old_by_id.get(a.from_lesson) == new_by_id.get(b.from_lesson)


def render_delta(course: Course, delta: Delta, number: int) -> Path:
    lines = [f"# Extension {number}: proposed change", ""]
    request = (ext_dir(course, number) / "request.md").read_text().split("\n", 2)[-1].strip()
    lines += [f"> {request}", ""]

    def row(lesson: Lesson) -> str:
        return f"**{lesson.id} {lesson.node.title}** — {' '.join(lesson.node.summary.split())}"

    if delta.added:
        lines += ["## New lessons", ""] + [f"- {row(lesson)}" for lesson in delta.added] + [""]
    if delta.changed:
        lines += ["## Lessons to rewrite", ""]
        lines += [
            f"- {row(new)} (changes: {', '.join(fields)})" for _, new, fields in delta.changed
        ]
        lines.append("")
    if delta.retitled:
        lines += ["## Renamed", ""]
        lines += [f"- {old.id}: {old.node.title} → {new.node.title}" for old, new in delta.retitled]
        lines.append("")
    if delta.moved:
        lines += ["## Renumbered (directories move; needs approval)", ""]
        lines += [f"- {old.id} → {new.id} {new.node.title}" for old, new in delta.moved]
        lines.append("")
    if delta.removed:
        lines += ["## Removed (not supported by extensions)", ""]
        lines += [f"- {row(lesson)}" for lesson in delta.removed] + [""]
    stale = stale_lessons(course, delta)
    if stale:
        lines += ["## Lessons to re-check (their example builds on a rewritten lesson)", ""]
        lines += [f"- {lesson_id}" for lesson_id in stale] + [""]
    if delta.empty:
        lines.append("No change to the curriculum.")
    path = ext_dir(course, number) / "delta.md"
    atomic_write(path, "\n".join(lines).rstrip() + "\n")
    return path


def stale_lessons(course: Course, delta: Delta) -> list[str]:
    """New ids of unchanged lessons whose example (transitively) extends a changed one."""
    proposed = cur.load(course, proposed_path(course, current(course).id))
    by_id = {lesson.id: lesson for lesson in cur.lessons(proposed)}
    changed = {new.id for _, new, _ in delta.changed}
    stale: list[str] = []
    for lesson in cur.lessons(proposed):
        if lesson.id in changed or lesson in delta.added:
            continue
        seen, node = set(), lesson.node
        while node.example and node.example.mode == "extend" and node.example.from_lesson:
            source = node.example.from_lesson
            if source in seen or source not in by_id:
                break
            if source in changed or source in stale:
                stale.append(lesson.id)
                break
            seen.add(source)
            node = by_id[source].node
    return sorted(stale, key=lesson_sort_key)


# --- applying ---------------------------------------------------------------------------------


def apply(course: Course, allow_renumber: bool = False) -> dict:
    extension = current(course)
    if extension.stage != "gate":
        raise ExtensionError(
            f"extension {extension.id} is at stage {extension.stage}; "
            "apply happens at the review gate"
        )
    proposed = proposed_path(course, extension.id)
    delta = compute_delta(course, proposed)
    if delta.removed:
        raise ExtensionError(
            "the proposal removes lessons: "
            + ", ".join(lesson.id for lesson in delta.removed)
            + ". Extensions only add and rewrite lessons."
        )
    if delta.moved and not allow_renumber:
        raise ExtensionError(
            "the proposal renumbers lessons: "
            + ", ".join(f"{o.id}→{n.id}" for o, n in delta.moved)
            + ". Ask the user, then pass --allow-renumber."
        )
    stale = stale_lessons(course, delta)

    if delta.moved:
        move_lessons(course, delta.moved)
    shutil.copy(proposed, course.meta / "curriculum.yaml")

    from codelabgen.scaffold import scaffold_course  # registers the new lessons, too

    store = StateStore(course)
    for _, new, _ in delta.changed:
        lesson = store.load().lessons[new.id]
        if lesson.stage is not Stage.PENDING:
            store.set_stage(new.id, Stage.PENDING, note=f"rewritten by extension {extension.id}")
    report = scaffold_course(course)
    for lesson_id in stale:
        if store.load().lessons[lesson_id].stage is Stage.DONE:
            store.mark_stale(lesson_id, f"builds on a lesson rewritten by extension {extension.id}")

    with store.transaction() as state:
        state.phase = Phase.LESSONS
        state.extension.stage = "lessons"
        state.extension.allow_renumber = allow_renumber
    store.log(
        "extension-apply",
        number=extension.id,
        added=[lesson.id for lesson in delta.added],
        changed=[new.id for _, new, _ in delta.changed],
        moved={o.id: n.id for o, n in delta.moved},
        stale=stale,
    )
    return {
        "added": [lesson.id for lesson in delta.added],
        "rewrite": [new.id for _, new, _ in delta.changed],
        "retitled": [new.id for _, new in delta.retitled],
        "moved": {o.id: n.id for o, n in delta.moved},
        "stale": stale,
        "created": report.created,
    }


def move_lessons(course: Course, moves: list[tuple[Lesson, Lesson]]) -> None:
    """Move lesson directories and everything keyed by lesson id (two-phase, no clashes)."""
    root, meta = course.root, course.meta
    staging = meta / "extension-moves"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)

    # 1. Lift every moving lesson (and its id-keyed metadata) out of the way.
    for index, (old, _) in enumerate(moves):
        for source, name in (
            (root / old.rel_dir, "dir"),
            (meta / "lessons" / old.id, "spec"),
            (meta / "runs" / old.id, "runs"),
        ):
            if source.exists():
                shutil.move(str(source), str(staging / f"{index}-{name}"))
    # 2. Put them down at their new places, renaming the package inside.
    for index, (old, new) in enumerate(moves):
        for name, target in (
            ("dir", root / new.rel_dir),
            ("spec", meta / "lessons" / new.id),
            ("runs", meta / "runs" / new.id),
        ):
            source = staging / f"{index}-{name}"
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
        for old_rel, new_rel in runtimes.for_course(course).path_renames(old, new):
            if (root / new.rel_dir / old_rel).exists():
                (root / new.rel_dir / old_rel).rename(root / new.rel_dir / new_rel)
    shutil.rmtree(staging)

    # 3. Rewrite references: packages, projects, ids in specs, directory names in links.
    tokens = {}
    for index, (old, new) in enumerate(moves):
        tokens[old.package] = (f"\0pkg{index}\0", new.package)
        tokens[old.project] = (f"\0prj{index}\0", new.project)
        tokens[old.dir_name] = (f"\0dir{index}\0", new.dir_name)
    for old, new in moves:
        for old_node, new_node in zip(old.ancestors, new.ancestors, strict=False):
            if old_node.id != new_node.id:
                old_name, new_name = cur.node_dir_name(old_node), cur.node_dir_name(new_node)
                tokens.setdefault(old_name, (f"\0grp{old_name}\0", new_name))
    texts = [
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix in TEXT_SUFFIXES
        and not {".git", ".venv", "cache", "repos", "site", "__pycache__"} & set(p.parts)
    ]
    pattern = re.compile("|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True)))
    for path in texts:
        text = path.read_text(errors="replace")
        if not pattern.search(text):
            continue
        text = pattern.sub(lambda m: tokens[m.group(0)][0], text)
        for placeholder, value in tokens.values():
            text = text.replace(placeholder, value)
        path.write_text(text)

    id_map = {old.id: new.id for old, new in moves}
    for spec in (meta / "lessons").glob("*/spec.yaml"):
        data = yaml.safe_load(spec.read_text()) or {}
        changed = False
        for key in ("id", "delta_from"):
            if data.get(key) in id_map:
                data[key], changed = id_map[data[key]], True
        if changed:
            atomic_write(spec, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))

    store = StateStore(course)
    with store.transaction() as state:
        lessons: dict[str, LessonState] = {}
        for lesson_id, lesson in state.lessons.items():
            lessons[id_map.get(lesson_id, lesson_id)] = lesson
        state.lessons = dict(sorted(lessons.items(), key=lambda kv: lesson_sort_key(kv[0])))
        state.tasks = {k: t for k, t in state.tasks.items() if not k.startswith("lesson:")}

    from codelabgen import glossary

    entries = glossary.load(course)
    for entry in entries:
        if entry.first_lesson in id_map:
            entry.first_lesson = id_map[entry.first_lesson]
    if entries:
        glossary.save(course, entries)

    # Module or section directories left empty by the moves.
    for old, _ in moves:
        for parent in (root / old.rel_dir).parents:
            if parent == root:
                break
            if parent.exists() and not any(
                p
                for p in parent.iterdir()
                if p.name not in ("pyproject.toml", "uv.lock", "README.md", ".venv")
            ):
                shutil.rmtree(parent)
    store.log("lessons-moved", moves=id_map)


def finish(course: Course) -> ExtensionState:
    extension = current(course)
    state = StateStore(course).load()
    if extension.stage != "lessons":
        raise ExtensionError(f"extension {extension.id} is at stage {extension.stage}")
    if state.phase is not Phase.DONE:
        raise StateError("assemble the course first (phase must be done)")
    return set_stage(course, "done")
