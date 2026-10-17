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


def load(course: Course, path: Path | None = None) -> Curriculum:
    """The course curriculum, or a proposed one at `path`, fully validated."""
    path = path or course.meta / "curriculum.yaml"
    if not path.is_file():
        raise CurriculumError([f"{path} does not exist"])
    curriculum = Curriculum.model_validate(yaml.safe_load(path.read_text()))
    problems = validate(curriculum) + validate_references(course, curriculum)
    if problems:
        raise CurriculumError(problems)
    return curriculum


def validate_references(course: Course, curriculum: Curriculum) -> list[str]:
    """Cited sources must be ones the course uses; services must be known."""
    from codelabgen import services
    from codelabgen import sources as srcmod

    problems = []
    if srcmod.registry(course).is_file():
        usable = {s.id for s in srcmod.used(course)}
        for node, _ in walk(curriculum):
            for source_id in node.sources:
                if source_id not in usable:
                    problems.append(f"{node.id}: source {source_id} is not a kept source")
    try:
        known = services.available(course.meta)
    except services.UnknownService as exc:
        return [*problems, str(exc)]
    for node, _ in walk(curriculum):
        for name in node.services:
            if name not in known:
                problems.append(
                    f"{node.id}: unknown service {name!r} (known: {', '.join(known)}; "
                    "define others in .codelabgen/services.yaml)"
                )
    return problems


def number(course: Course, path: Path | None = None) -> dict[str, str]:
    """Give every node the id of its position; rewrite references to the old ids.

    Works on the raw YAML, so nodes may lack ids or carry stale ones (after the
    architect reorders lessons). Returns old id -> new id for the changed ones.
    """
    path = path or course.meta / "curriculum.yaml"
    data = yaml.safe_load(path.read_text())
    mapping: dict[str, str] = {}

    def visit(nodes: list[dict], prefix: str) -> None:
        for position, node in enumerate(nodes, start=1):
            new_id = f"{prefix}.{position}" if prefix else str(position)
            old_id = str(node.get("id", "")) or None
            if old_id and old_id != new_id:
                mapping[old_id] = new_id
            node["id"] = new_id
            visit(node.get("children") or [], new_id)

    visit(data.get("modules") or [], "")

    def remap(value: str) -> str:
        return mapping.get(str(value), str(value))

    def fix(nodes: list[dict]) -> None:
        for node in nodes:
            if node.get("prerequisites"):
                node["prerequisites"] = [remap(p) for p in node["prerequisites"]]
            example = node.get("example") or {}
            if example.get("from"):
                example["from"] = remap(example["from"])
            fix(node.get("children") or [])

    fix(data.get("modules") or [])
    for var in data.get("env") or []:
        if var.get("lessons"):
            var["lessons"] = [remap(lesson) for lesson in var["lessons"]]
    order = [
        "id",
        "title",
        "slug",
        "summary",
        "objectives",
        "prerequisites",
        "example",
        "services",
        "sources",
        "children",
    ]

    def ordered(node: dict) -> dict:
        result = {k: node[k] for k in order if k in node}
        result |= {k: v for k, v in node.items() if k not in result}
        if result.get("children"):
            result["children"] = [ordered(child) for child in result["children"]]
        return result

    data["modules"] = [ordered(module) for module in data.get("modules") or []]
    from codelabgen.course import atomic_write

    atomic_write(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100))
    return mapping


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


def render_plan(course: Course) -> Path:
    """`.codelabgen/plan.md`: the curriculum as the user reviews it at gate 2."""
    from codelabgen import sources as srcmod
    from codelabgen.course import atomic_write
    from codelabgen.i18n import labels

    curriculum = load(course)
    config = course.load_config()
    text = labels(config.language)
    all_lessons = lessons(curriculum)
    lines = [
        f"# {text['plan']}: {curriculum.title}",
        "",
        " ".join(curriculum.description.split()),
        "",
        f"**{text['technology']}:** {config.topic} {config.version or ''} · "
        f"**{text['course_language']}:** {config.language} · "
        f"{len(curriculum.modules)} {text['modules_word']}, "
        f"{len(all_lessons)} {text['lessons_word']}",
        "",
    ]
    titles = {node.id: node.title for node, _ in walk(curriculum)}
    source_titles = {s.id: s.title for s in srcmod.load(course)}

    def visit(node: CurriculumNode, depth: int) -> None:
        if depth == 0:
            lines.extend([f"## {node.id} {node.title}", "", " ".join(node.summary.split()), ""])
        elif node.children:
            lines.extend([f"### {node.id} {node.title}", "", " ".join(node.summary.split()), ""])
        else:
            lines.append(f"- **{node.id} {node.title}** — {' '.join(node.summary.split())}")
            details = []
            if node.objectives:
                details.append(f"{text['objectives']}: " + "; ".join(node.objectives))
            if node.example:
                if node.example.mode == "extend" and node.example.from_lesson:
                    source = node.example.from_lesson
                    details.append(
                        f"{text['example']}: `{node.example.name}`, "
                        f"{text['example_extends']} {source} {titles.get(source, '')}"
                    )
                else:
                    details.append(
                        f"{text['example']}: `{node.example.name}` ({text['example_new']})"
                    )
            if node.prerequisites:
                details.append(f"{text['prerequisites_word']}: {', '.join(node.prerequisites)}")
            if node.services:
                details.append(f"{text['services']}: {', '.join(node.services)}")
            if node.sources:
                named = [source_titles.get(s, s) for s in node.sources]
                details.append(f"{text['sources']}: " + "; ".join(named))
            lines.extend(f"  - {d}" for d in details)
        for child in node.children:
            visit(child, depth + 1)
        if depth == 0 or node.children:
            lines.append("")

    for module in curriculum.modules:
        visit(module, 0)

    runtime = config.runtime
    used_services = sorted({s for lesson in all_lessons for s in lesson.node.services})
    lines += [
        f"## {text['runtime']}",
        "",
        f"- {runtime.kind or 'python-uv'}, "
        f"{text['per_module'] if runtime.per == 'module' else text['per_lesson']}",
        f"- {text['services']}: {', '.join(used_services) or text['none']}",
        "",
    ]

    lines += [f"## {text['external']}", ""]
    for external in config.external:
        models = f" ({', '.join(external.models)})" if external.models else ""
        lines.append(f"- {external.provider}{models}: {', '.join(external.env_vars)}")
    if curriculum.env:
        lines += [
            "",
            f"| {text['env_var']} | {text['meaning']} | {text['secret']} | {text['lessons']} |",
            "|---|---|---|---|",
        ]
        for var in curriculum.env:
            where = f" — {var.where_to_get}" if var.where_to_get else ""
            lines.append(
                f"| `{var.name}` | {var.description}{where} | "
                f"{'✓' if var.secret else ''} | "
                f"{', '.join(var.lessons) or text['all_lessons']} |"
            )
    elif not config.external:
        lines.append(text["none"])
    path = course.meta / "plan.md"
    atomic_write(path, "\n".join(lines).rstrip() + "\n")
    return path
