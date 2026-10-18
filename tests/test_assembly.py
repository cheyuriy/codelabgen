"""toc, glossary, checks and the Markdown helpers (no network, no external tools)."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from codelabgen import checks, glossary, toc
from codelabgen.init import init_course
from codelabgen.markdown import github_slug, heading_slugs, prose_lines
from codelabgen.scaffold import scaffold_course

FIXTURE = Path(__file__).parent / "fixtures" / "langgraph-curriculum.yaml"


@pytest.fixture
def course(tmp_path):
    course = init_course(tmp_path / "course", topic="LangGraph", language="ru")
    shutil.copy(FIXTURE, course.meta / "curriculum.yaml")
    scaffold_course(course)
    return course


def lesson_dir(course, name="1.1-hello-graph"):
    return course.root / "1-basics" / name


# --- markdown helpers -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "slug"),
    [
        ("Граф состояний", "граф-состояний"),
        ("Что изменилось с урока 1.1", "что-изменилось-с-урока-11"),
        ("The `route()` function!", "the-route-function"),
        ("Read-along", "read-along"),
        ("path_map", "path_map"),
    ],
)
def test_github_slug(heading, slug):
    assert github_slug(heading) == slug


def test_heading_slugs_dedupe_and_skip_code():
    text = '# A\n## A\n```\n# not a heading\n```\n<a id="custom"></a>\n'
    assert heading_slugs(text) == {"a", "a-1", "custom"}


def test_prose_lines_skip_nested_fences():
    text = "x\n````md\n```\ninside\n```\n````\ny\n"
    assert [line for _, line in prose_lines(text)] == ["x", "y"]


# --- glossary ---------------------------------------------------------------------------


def test_glossary_add_update_build_and_link(course):
    glossary.add(course, "Граф состояний", "Граф узлов.", aliases=["граф"], lesson="1.1")
    entry, created = glossary.add(course, "граф состояний", "Граф узлов над общим состоянием.")
    assert not created and entry.definition.endswith("состоянием.")
    assert [e.term for e in glossary.load(course)] == ["Граф состояний"]

    page, abbr = glossary.build(course)
    text = page.read_text()
    assert "## Граф состояний" in text and "1-basics/1.1-hello-graph/README.md" in text
    assert "*[граф]: Граф узлов над общим состоянием." in abbr.read_text()

    notes = lesson_dir(course) / "docs" / "notes.md"
    assert glossary.link(course, "Граф состояний", notes) == "../../../GLOSSARY.md#граф-состояний"
    with pytest.raises(KeyError):
        glossary.link(course, "nope", notes)


def test_glossary_heading_keeps_dunder_terms_out_of_emphasis(course):
    glossary.add(course, "__interrupt__", "The pause key.")
    glossary.add(course, "path_map", "Routing map.")
    text = glossary.build(course)[0].read_text()
    assert "## `__interrupt__`" in text and "## path_map" in text
    notes = lesson_dir(course) / "docs" / "notes.md"
    assert glossary.link(course, "__interrupt__", notes).endswith("#__interrupt__")


# --- toc --------------------------------------------------------------------------------


def test_toc_generates_pages_nav_and_run_sh(course):
    (lesson_dir(course) / "docs" / "notes.md").write_text("# Notes\n")
    written = {p.relative_to(course.root).as_posix() for p in toc.generate(course)}
    assert {
        "README.md",
        "mkdocs.yml",
        "run.sh",
        "1-basics/README.md",
        "1-basics/1.3-persistence/README.md",
        "assets/glossary-abbr.md",
    } <= written

    readme = (course.root / "README.md").read_text()
    assert "## Как начать" in readme and "[1.2 Условные рёбра и маршрутизация]" in readme
    lesson3 = (lesson_dir(course, "1.3-persistence") / "README.md").read_text()
    assert "> [!NOTE]" in lesson3 and "../1.2-routing/README.md" in lesson3
    assert "docker compose up -d --wait postgres" in lesson3

    config = (course.root / "mkdocs.yml").read_text()
    assert "language: ru" in config and "pymdownx.arithmatex" in config
    nav = config.split("\nnav:\n", 1)[1]
    assert "1-basics/1.1-hello-graph/docs/notes.md" in nav
    assert "readalong.md" not in nav  # only pages that exist

    assert toc.generate(course) == []  # stable output

    run_sh = course.root / "run.sh"
    listed = subprocess.run([str(run_sh), "list"], capture_output=True, text=True, check=True)
    assert "1.3      Сохранение состояния: checkpointer на Postgres" in listed.stdout
    unknown = subprocess.run([str(run_sh), "9.9"], capture_output=True, text=True)
    assert unknown.returncode == 2


def test_mkdocs_yml_parses(course):
    toc.generate(course)

    class Loader(yaml.SafeLoader):
        pass

    Loader.add_multi_constructor("tag:yaml.org,2002:python/", lambda *args: None)
    config = yaml.load((course.root / "mkdocs.yml").read_text(), Loader=Loader)
    assert config["docs_dir"] == "." and config["use_directory_urls"] is False
    assert config["nav"][0] == {"Главная": "README.md"}


# --- checks -----------------------------------------------------------------------------


def write_doc(course, text, name="notes.md"):
    path = lesson_dir(course) / "docs" / name
    path.write_text(text)
    return path


def test_check_links(course):
    toc.generate(course)
    write_doc(
        course,
        "# Заметки\n\n## Раздел\n\n[ok](#раздел) [ok](../README.md) "
        "[bad](missing.md) [bad anchor](#нет) [web](https://example.com)\n"
        "```\n[ignored](nope.md)\n```\n",
    )
    problems = checks.check_links(course)
    assert len(problems) == 2
    assert "broken link missing.md" in problems[0] and "no heading #нет" in problems[1]


def test_check_render_and_math(course):
    write_doc(
        course,
        '!!! note\n=== "Tab"\n--8<-- "x"\n\\(x\\)\n$ x$\ntext $$x$$\n$a$ and $b$\n'
        "```\n!!! fine in code\n```\n",
    )
    render = "\n".join(checks.check_render(course))
    assert "admonition" in render and "content tabs" in render and "--8<--" in render
    math = "\n".join(checks.check_math(course))
    assert "\\( \\)" in math and "space just inside" in math and "lines of its own" in math
    assert "notes.md:7" not in math  # two inline formulas on a line are fine


def test_check_mermaid(course):
    write_doc(course, "```mermaid\nflowchart LR\n  A --> B\n```\n\n```mermaid\nA --> B\n```\n")
    problems = checks.check_mermaid(course)
    assert len(problems) == 1 and "found 'A'" in problems[0]


def test_check_structure(course):
    problems = checks.check_structure(course)
    assert len(problems) == 3 and "missing lesson code, tests" in problems[0]


# --- record helpers -------------------------------------------------------------------------


def test_content_size_fits_output():
    from codelabgen.record import content_size

    cast = (
        '{"version": 3}\n[0.1, "o", "$ run\\r\\n"]\n[0.2, "o", "\\u001b[32mok\\u001b[0m\\r\\n"]\n'
    )
    assert content_size(cast) == (40, 5)  # minimum height
    long_line = '[0.1, "o", "' + "x" * 300 + '"]'
    many = "\n".join('[0.1, "o", "line\\r\\n"]' for _ in range(100))
    assert content_size('{"version": 3}\n' + long_line + "\n" + many) == (100, 30)


def test_check_links_line_anchors(course):
    toc.generate(course)
    code = lesson_dir(course) / "src" / "l1_1_hello_graph" / "graph.py"
    code.write_text("a = 1\nb = 2\nc = 3\n")
    write_doc(
        course,
        "# Разбор\n\n[a](../src/l1_1_hello_graph/graph.py#L1) "
        "[range](../src/l1_1_hello_graph/graph.py#L2-L3) "
        "[past](../src/l1_1_hello_graph/graph.py#L9) "
        "[bad range](../src/l1_1_hello_graph/graph.py#L2-L7)\n",
        name="readalong.md",
    )
    problems = checks.check_links(course)
    assert len(problems) == 2 and all(
        "points past the end of graph.py (3 lines)" in p for p in problems
    )
