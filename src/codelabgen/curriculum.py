"""Loading, validating and walking `.codelabgen/curriculum.yaml`.

The tree has up to three levels. Top-level nodes are modules (one directory and
one uv workspace each). Leaves are lessons. A level-2 node with children is a
section: a plain directory that groups lessons.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from codelabgen.course import Course
from codelabgen.models import Curriculum, CurriculumNode, lesson_sort_key


class CurriculumError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("curriculum is invalid:\n" + "\n".join(f"  - {p}" for p in problems))


@dataclass(frozen=True)
class Lesson:
    """A leaf of the curriculum, with where it lives on disk."""

    node: CurriculumNode
    module: CurriculumNode
    ancestors: tuple[CurriculumNode, ...] = field(default=())  # module first

    @property
    def id(self) -> str:
        return self.node.id

    @property
    def dir_name(self) -> str:
        return node_dir_name(self.node)

    @property
    def rel_dir(self) -> Path:
        """Lesson directory relative to the course root."""
        return Path(*(node_dir_name(n) for n in self.ancestors), self.dir_name)

    @property
    def module_rel_dir(self) -> Path:
        return Path(node_dir_name(self.module))

    @property
    def package(self) -> str:
        """Importable Python package name, e.g. `l1_2_state`."""
        return "l" + self.id.replace(".", "_") + "_" + self.node.slug.replace("-", "_")

    @property
    def project(self) -> str:
        """uv project (distribution) name, e.g. `l1-2-state`."""
        return self.package.replace("_", "-")


def node_dir_name(node: CurriculumNode) -> str:
    return f"{node.id}-{node.slug}"


def load(course: Course) -> Curriculum:
    path = course.meta / "curriculum.yaml"
    if not path.is_file():
        raise CurriculumError([f"{path} does not exist"])
    curriculum = Curriculum.model_validate(yaml.safe_load(path.read_text()))
    problems = validate(curriculum)
    if problems:
        raise CurriculumError(problems)
    return curriculum


def walk(curriculum: Curriculum) -> Iterator[tuple[CurriculumNode, tuple[CurriculumNode, ...]]]:
    """All nodes in reading order, with their ancestors (outermost first)."""

    def visit(node, ancestors):
        yield node, ancestors
        for child in node.children:
            yield from visit(child, (*ancestors, node))

    for module in curriculum.modules:
        yield from visit(module, ())


def lessons(curriculum: Curriculum) -> list[Lesson]:
    return [
        Lesson(node=node, module=ancestors[0], ancestors=ancestors)
        for node, ancestors in walk(curriculum)
        if not node.children and ancestors
    ]


def find_lesson(curriculum: Curriculum, lesson_id: str) -> Lesson:
    for lesson in lessons(curriculum):
        if lesson.id == lesson_id:
            return lesson
    raise CurriculumError([f"no lesson {lesson_id} in the curriculum"])


def validate(curriculum: Curriculum) -> list[str]:
    """Structural checks the schema cannot express. Returns a list of problems."""
    problems: list[str] = []

    def check_children(parent_id: str | None, nodes: list[CurriculumNode]) -> None:
        slugs = set()
        for position, node in enumerate(nodes, start=1):
            expected = f"{parent_id}.{position}" if parent_id else str(position)
            if node.id != expected:
                problems.append(f"{node.id} '{node.title}': expected id {expected} by position")
            if node.slug in slugs:
                problems.append(f"{node.id}: slug '{node.slug}' repeats among its siblings")
            slugs.add(node.slug)
            check_children(node.id, node.children)

    check_children(None, curriculum.modules)
    if not curriculum.modules:
        problems.append("the curriculum has no modules")
    for module in curriculum.modules:
        if not module.children:
            problems.append(f"module {module.id} has no lessons")

    order = {node.id: index for index, (node, _) in enumerate(walk(curriculum))}
    leaf_ids = {lesson.id for lesson in lessons(curriculum)}
    for node, _ in walk(curriculum):
        for prerequisite in node.prerequisites:
            if prerequisite not in order:
                problems.append(f"{node.id}: unknown prerequisite {prerequisite}")
            elif order[prerequisite] >= order[node.id]:
                problems.append(f"{node.id}: prerequisite {prerequisite} does not come earlier")
        if node.children and (node.example or node.services):
            problems.append(f"{node.id}: example and services belong on lessons (leaves) only")
        example = node.example
        if example is None:
            continue
        if example.mode == "new" and example.from_lesson:
            problems.append(f"{node.id}: a new example cannot have 'from'")
        if example.mode == "extend":
            source = example.from_lesson
            if not source:
                problems.append(f"{node.id}: an extended example needs 'from'")
            elif source not in leaf_ids:
                problems.append(f"{node.id}: example extends {source}, which is not a lesson")
            elif lesson_sort_key(source) >= lesson_sort_key(node.id):
                problems.append(f"{node.id}: example extends {source}, which does not come earlier")

    names = [var.name for var in curriculum.env]
    for name in {n for n in names if names.count(n) > 1}:
        problems.append(f"env variable {name} is defined more than once")
    for var in curriculum.env:
        for lesson_id in var.lessons:
            if lesson_id not in leaf_ids:
                problems.append(f"env {var.name}: unknown lesson {lesson_id}")
    return problems
