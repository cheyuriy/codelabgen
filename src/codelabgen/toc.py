"""`codelabgen toc`: READMEs, mkdocs.yml (with nav), run.sh and site assets.

Everything written here is generated from the curriculum and the lesson specs
and is overwritten on every run. Lesson code and docs are never touched.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

from codelabgen import curriculum as cur
from codelabgen import env as envmod
from codelabgen import glossary, runtimes, sources
from codelabgen.course import Course, atomic_write
from codelabgen.curriculum import Lesson
from codelabgen.i18n import labels
from codelabgen.markdown import relative_link
from codelabgen.models import Curriculum, CurriculumNode
from codelabgen.scaffold import _jinja, lesson_services

TEMPLATES = files("codelabgen") / "templates"

# The site toolchain, pinned in one place (run with uvx; nothing is installed in the course).
SITE_MKDOCS = "mkdocs==1.6.1"
SITE_PLUGINS = [
    "mkdocs-material==9.7.7",
    "mkdocs-same-dir==0.1.5",
    "mkdocs-callouts==1.17.1",
    "pymdown-extensions==12.3",
]


def render(name: str, **context) -> str:
    return _jinja.from_string((TEMPLATES / name).read_text()).render(**context)


def run_command(course: Course, lesson: Lesson) -> str:
    spec = envmod.load_spec(course, lesson.id)
    return spec.run_cmd if spec else runtimes.for_course(course).default_run_cmd(lesson)


def run_entry(course: Course, lesson: Lesson, services: list[str]) -> dict:
    """One lesson's line in run.sh."""
    shell = shell_commands(course, lesson)
    sync_dir = lesson.module_rel_dir if shell.sync_cwd == "module" else lesson.rel_dir
    return {
        "id": lesson.id,
        "title": lesson.node.title,
        "dir": lesson.rel_dir.as_posix(),
        "services": " ".join(services),
        "sync_dir": sync_dir.as_posix(),
        "sync": shell.sync,
        "run": shell.run,
        "test": shell.test,
    }


def shell_commands(course: Course, lesson: Lesson):
    return runtimes.for_course(course).shell(lesson, run_command(course, lesson))


def generate(course: Course) -> list[Path]:
    curriculum = cur.load(course)
    config = course.load_config()
    text = labels(config.language)
    lessons = cur.lessons(curriculum)
    services = lesson_services(curriculum, course)
    written: list[Path] = []

    def write(path: Path, content: str) -> None:
        if not path.exists() or path.read_text() != content:
            atomic_write(path, content)
            written.append(path)

    # site assets and the glossary (always present: the site appends the abbreviations file)
    for asset in ("assets/js/mathjax.js", "assets/js/asciinema.js", "assets/hooks/asciinema.py"):
        write(course.root / asset, (TEMPLATES / asset).read_text())
    if not (course.root / glossary.ABBR_FILE).exists() or glossary.load(course):
        written += glossary.build(course)

    write(course.root / "README.md", course_readme(course, curriculum, lessons, services, text))
    for node, ancestors in cur.walk(curriculum):
        if node.children:
            folder = course.root.joinpath(*(cur.node_dir_name(n) for n in (*ancestors, node)))
            write(folder / "README.md", group_readme(course, folder, node, text))
    for index, lesson in enumerate(lessons):
        previous = lessons[index - 1] if index > 0 else None
        following = lessons[index + 1] if index + 1 < len(lessons) else None
        content = lesson_readme(
            course, curriculum, lesson, services[lesson.id], previous, following, text
        )
        write(course.root / lesson.rel_dir / "README.md", content)

    nav = yaml.safe_dump(
        build_nav(course, curriculum, text), allow_unicode=True, sort_keys=False, width=1000
    )
    write(
        course.root / "mkdocs.yml",
        render(
            "mkdocs.yml.j2",
            title=curriculum.title,
            # the site meta description: the opening paragraph, without the README's lists
            description=" ".join(curriculum.description.strip().split("\n\n")[0].split()),
            language=config.language,
            labels=text,
            nav="\n".join("  " + line for line in nav.splitlines()),
        ),
    )

    run_sh = course.root / "run.sh"
    write(
        run_sh,
        render(
            "run.sh.j2",
            lessons=[run_entry(course, lesson, services[lesson.id]) for lesson in lessons],
            site_mkdocs=SITE_MKDOCS,
            site_plugins=SITE_PLUGINS,
        ),
    )
    run_sh.chmod(0o755)
    return written


def course_readme(course, curriculum: Curriculum, lessons, services, text) -> str:
    uses_docker = any(services.values())
    lines = [
        f"# {curriculum.title}",
        "",
        curriculum.description.strip(),
        "",
        f"## {text['getting_started']}",
        "",
    ]
    requirement = text["requirements"] + (text["requirements_docker"] if uses_docker else "")
    lines += [
        f"1. {requirement}.",
        f"2. {text['env_step']}",
        f"3. {text['run_step']}",
        "",
        "   ```bash",
        f"   ./run.sh {lessons[0].id}" if lessons else "   ./run.sh list",
        "   ```",
        "",
        f"4. {text['site_step']}",
        "",
        "   ```bash",
        "   ./run.sh site serve",
        "   ```",
        "",
        f"5. {text['branch_step']}",
        "",
        "   ```bash",
        f"   git switch -c {text['branch_name']}",
        "   ```",
        "",
        f"## {text['contents']}",
        "",
    ]

    def visit(node: CurriculumNode, ancestors: tuple, depth: int) -> None:
        folder = Path(*(cur.node_dir_name(n) for n in (*ancestors, node)))
        target = (folder / "README.md").as_posix()
        label = f"[{node.id} {node.title}]({target})"
        summary = " ".join(node.summary.split())
        if depth == 0:
            lines.extend([f"### {label}", "", summary, ""])
        else:
            lines.append(f"{'  ' * (depth - 1)}- {label} — {summary}")
        for child in node.children:
            visit(child, (*ancestors, node), depth + 1)
        if depth == 0:
            lines.append("")

    for module in curriculum.modules:
        visit(module, (), 0)
    if glossary.load(course):
        lines += [f"[{text['glossary']}]({glossary.GLOSSARY_PAGE})", ""]
    lines += sources_section(course, text)
    return "\n".join(lines).rstrip() + "\n"


def sources_section(course: Course, text) -> list[str]:
    """The sources the course is built from, by type: titles and links only (no review scores
    or notes, which stay in .codelabgen)."""
    used = sources.used(course)
    if not used:
        return []
    lines = [f"## {text['sources']}", "", text["sources_intro"], ""]
    for type_ in sources.TYPE_ORDER:
        group = [s for s in used if s.type == type_]
        if group:
            lines += [f"### {text[f'type_{type_}']}", ""]
            lines += [f"- [{s.title}]({s.url})" for s in group]
            lines.append("")
    return lines


def group_readme(course: Course, folder: Path, node: CurriculumNode, text) -> str:
    lines = [f"# {node.id} {node.title}", "", " ".join(node.summary.split()), ""]
    if node.objectives:
        lines += [f"## {text['what_you_learn']}", ""] + [f"- {o}" for o in node.objectives] + [""]
    lines += [f"## {text['lessons']}", ""]
    for child in node.children:
        link = f"{cur.node_dir_name(child)}/README.md"
        lines.append(f"- [{child.id} {child.title}]({link}) — {' '.join(child.summary.split())}")
    lines += [
        "",
        f"[{text['home']}]({relative_link(folder / 'README.md', course.root / 'README.md')})",
    ]
    return "\n".join(lines) + "\n"


def lesson_readme(course, curriculum, lesson: Lesson, services, previous, following, text) -> str:
    here = course.root / lesson.rel_dir / "README.md"
    node = lesson.node
    lines = [f"# {node.id} {node.title}", "", " ".join(node.summary.split()), ""]
    example = node.example
    if example and example.mode == "extend" and example.from_lesson:
        source = cur.find_lesson(curriculum, example.from_lesson)
        link = relative_link(here, course.root / source.rel_dir / "README.md")
        lines += [
            "> [!NOTE]",
            f"> {text['extends']} [{source.id} {source.node.title}]({link}).",
            "",
        ]
    if node.objectives:
        lines += [f"## {text['what_you_learn']}", ""] + [f"- {o}" for o in node.objectives] + [""]

    lines += [f"## {text['materials']}", ""]
    docs = course.root / lesson.rel_dir / "docs"
    if (docs / "notes.md").exists():
        lines.append(f"- [{text['notes']}](docs/notes.md) — {text['notes_hint']}")
    if (docs / "readalong.md").exists():
        lines.append(f"- [{text['readalong']}](docs/readalong.md) — {text['readalong_hint']}")
    lesson_dir = course.root / lesson.rel_dir
    code_files = runtimes.real_code_files(runtimes.for_course(course), lesson_dir, lesson)
    if code_files:
        links = ", ".join(
            f"[{p.name}]({p.relative_to(lesson_dir).as_posix()})" for p in code_files[:12]
        )
        lines.append(f"- {text['code']}: {links}")
    lines.append("")

    shell = shell_commands(course, lesson)
    lines += [
        f"## {text['how_to_run']}",
        "",
        text["run_hint"],
        "",
        "```bash",
        f"./run.sh {lesson.id}",
        "```",
        "",
        text["manual_hint"],
        "",
        "```bash",
    ]
    if services:
        lines.append(f"docker compose up -d --wait {' '.join(services)}")
    if shell.sync_cwd == "module":
        lines += [
            f"cd {lesson.module_rel_dir.as_posix()} && {shell.sync}",
            f"cd {lesson.rel_dir.relative_to(lesson.module_rel_dir).as_posix()}",
        ]
    else:
        lines += [f"cd {lesson.rel_dir.as_posix()} && {shell.sync}"]
    lines += [
        shell.run,
        "```",
        "",
        text["tests_hint"],
        "",
        "```bash",
        f"./run.sh test {lesson.id}",
        "```",
        "",
    ]

    navigation = []
    if previous:
        link = relative_link(here, course.root / previous.rel_dir / "README.md")
        navigation.append(f"← {text['previous']}: [{previous.id} {previous.node.title}]({link})")
    if following:
        link = relative_link(here, course.root / following.rel_dir / "README.md")
        navigation.append(f"{text['next']}: [{following.id} {following.node.title}]({link}) →")
    if navigation:
        lines += [" · ".join(navigation), ""]
    return "\n".join(lines).rstrip() + "\n"


def build_nav(course: Course, curriculum: Curriculum, text) -> list:
    def entry(node: CurriculumNode, ancestors: tuple) -> dict:
        folder = Path(*(cur.node_dir_name(n) for n in (*ancestors, node)))
        items: list = [(folder / "README.md").as_posix()]
        if node.children:
            items += [entry(child, (*ancestors, node)) for child in node.children]
        else:
            for name, label in (("notes.md", text["notes"]), ("readalong.md", text["readalong"])):
                if (course.root / folder / "docs" / name).exists():
                    items.append({label: (folder / "docs" / name).as_posix()})
        return {f"{node.id} {node.title}": items}

    nav: list = [{text["home"]: "README.md"}]
    nav += [entry(module, ()) for module in curriculum.modules]
    if glossary.load(course):
        nav.append({text["glossary"]: glossary.GLOSSARY_PAGE})
    return nav
