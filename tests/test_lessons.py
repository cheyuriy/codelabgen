"""Curriculum, scaffold, env and snippets (no network)."""

import shutil
from pathlib import Path

import pytest
import yaml

from codelabgen import curriculum as cur
from codelabgen import env as envmod
from codelabgen import snippets
from codelabgen.curriculum import CurriculumError
from codelabgen.init import init_course
from codelabgen.models import Curriculum
from codelabgen.scaffold import ScaffoldError, scaffold_course, scaffold_lesson
from codelabgen.state import StateStore

FIXTURE = Path(__file__).parent / "fixtures" / "langgraph-curriculum.yaml"


@pytest.fixture
def course(tmp_path):
    course = init_course(tmp_path / "course", topic="LangGraph", language="ru")
    shutil.copy(FIXTURE, course.meta / "curriculum.yaml")
    return course


def fixture_data() -> dict:
    return yaml.safe_load(FIXTURE.read_text())


# --- curriculum -----------------------------------------------------------------------


def test_fixture_is_valid(course):
    curriculum = cur.load(course)
    lessons = cur.lessons(curriculum)
    assert [lesson.id for lesson in lessons] == ["1.1", "1.2", "1.3"]
    third = lessons[2]
    assert third.rel_dir == Path("1-basics/1.3-persistence")
    assert (third.package, third.project) == ("l1_3_persistence", "l1-3-persistence")
    assert third.node.example.from_lesson == "1.2"


def test_validation_catches_structure_errors():
    data = fixture_data()
    lessons = data["modules"][0]["children"]
    lessons[1]["id"] = "1.5"
    lessons[0]["prerequisites"] = ["1.3"]
    lessons[2]["example"]["from"] = "1.3"
    data["modules"].append({"id": "2", "title": "Empty", "slug": "empty", "summary": "x"})
    problems = cur.validate(Curriculum.model_validate(data))
    text = "\n".join(problems)
    assert "expected id 1.2" in text
    assert "1.1: prerequisite 1.3 does not come earlier" in text
    assert "extends 1.3, which does not come earlier" in text
    assert "module 2 has no lessons" in text


def test_depth_limit_is_schema_level():
    data = fixture_data()
    lesson = data["modules"][0]["children"][0]
    lesson["children"] = [
        {
            "id": "1.1.1",
            "title": "t",
            "slug": "a",
            "summary": "s",
            "children": [{"id": "1.1.1.1", "title": "t", "slug": "b", "summary": "s"}],
        }
    ]
    with pytest.raises(ValueError, match="1 to 3 levels"):
        Curriculum.model_validate(data)


def test_load_reports_problems(course):
    data = fixture_data()
    data["modules"][0]["children"][0]["id"] = "1.9"
    (course.meta / "curriculum.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(CurriculumError, match="expected id 1.1"):
        cur.load(course)


# --- scaffold ---------------------------------------------------------------------------


def test_scaffold_course(course):
    report = scaffold_course(course)
    root = course.root
    for path in [
        ".gitignore",
        "ruff.toml",
        "docker-compose.yml",
        ".env.example",
        ".env",
        "1-basics/pyproject.toml",
        "1-basics/1.1-hello-graph/pyproject.toml",
        "1-basics/1.1-hello-graph/src/l1_1_hello_graph/__init__.py",
        "1-basics/1.3-persistence/README.md",
    ]:
        assert (root / path).exists(), path
    assert (root / ".git").is_dir()
    assert '"1.1-hello-graph"' in (root / "1-basics/pyproject.toml").read_text()
    assert "POSTGRES_URL=postgresql://" in (root / ".env.example").read_text()
    assert "postgres:" in (root / "docker-compose.yml").read_text()
    assert course.load_config().runtime.services == ["postgres"]
    assert list(StateStore(course).load().lessons) == ["1.1", "1.2", "1.3"]
    assert report.copied_from == {}  # copying waits for `scaffold lesson`

    again = scaffold_course(course)
    assert again.created == [] and again.written == []


def test_scaffold_lesson_copies_extended_code(course):
    scaffold_course(course)
    root = course.root
    with pytest.raises(ScaffoldError, match="has no code yet"):
        # 1.2's package is still the stub, but the stub exists, so mimic an empty source
        shutil.rmtree(root / "1-basics/1.2-routing/src/l1_2_routing")
        scaffold_lesson(course, "1.3")
    assert (root / "1-basics/1.3-persistence/src/l1_3_persistence/__init__.py").exists()
    src = root / "1-basics/1.2-routing/src/l1_2_routing"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('"""Lesson 1.2: Условные рёбра и маршрутизация."""\n')
    (src / "graph.py").write_text("from l1_2_routing.state import State\n")
    (root / "1-basics/1.2-routing/tests/test_graph.py").write_text("import l1_2_routing\n")

    report = scaffold_lesson(course, "1.3")
    assert report.copied_from == {"1.3": "1.2"}
    target = root / "1-basics/1.3-persistence"
    assert (target / "src/l1_3_persistence/graph.py").read_text() == (
        "from l1_3_persistence.state import State\n"
    )
    assert "Lesson 1.3: Сохранение" in (target / "src/l1_3_persistence/__init__.py").read_text()
    assert (target / "tests/test_graph.py").read_text() == "import l1_3_persistence\n"
    assert 'name = "l1-3-persistence"' in (target / "pyproject.toml").read_text()

    # once the lesson has its own code, scaffolding again must not overwrite it
    (target / "src/l1_3_persistence/graph.py").write_text("# edited\n")
    assert scaffold_lesson(course, "1.3").copied_from == {}
    assert (target / "src/l1_3_persistence/graph.py").read_text() == "# edited\n"


def test_unknown_service(course):
    data = fixture_data()
    data["modules"][0]["children"][0]["services"] = ["mongo"]
    (course.meta / "curriculum.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(CurriculumError, match="unknown service 'mongo'"):
        scaffold_course(course)


# --- env --------------------------------------------------------------------------------


def test_env_layering_and_check(course):
    data = fixture_data()
    data["env"] = [
        {"name": "API_KEY", "description": "key", "secret": True},
        {
            "name": "MODEL",
            "description": "model",
            "scope": "lesson",
            "lessons": ["1.2"],
            "default": "small",
        },
    ]
    (course.meta / "curriculum.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    scaffold_course(course)
    curriculum = cur.load(course)
    lesson = cur.find_lesson(curriculum, "1.2")
    assert envmod.check(course, curriculum, lesson).missing == ["API_KEY", "MODEL"]
    assert "MODEL=small" in (course.root / lesson.rel_dir / ".env.example").read_text()

    (course.root / ".env").write_text("API_KEY=course\nMODEL=course-model\n")
    (course.root / lesson.rel_dir / ".env").write_text("MODEL=lesson-model\n")
    assert envmod.check(course, curriculum, lesson).missing == []
    values = envmod.lesson_env(course, lesson)
    assert values["MODEL"] == "lesson-model" and values["API_KEY"] == "course"
    assert "VIRTUAL_ENV" not in envmod.process_env(course, lesson)


def test_secret_default_rejected():
    with pytest.raises(ValueError, match="secrets must not have a default"):
        envmod.EnvVar(name="X", description="x", secret=True, default="oops")


# --- snippets ------------------------------------------------------------------------------


CODE = '''\
"""Module."""

# region state
class State:
    # region fields
    total: int
    # endregion
    name: str
# endregion


def run():
    # region body
    return 1
    # endregion
'''


@pytest.fixture
def lesson_dir(tmp_path):
    root = tmp_path / "1.1-x"
    (root / "src/pkg").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "src/pkg/graph.py").write_text(CODE)
    return root


def test_parse_regions_nested_and_dedented():
    regions = snippets.parse_regions(CODE)
    assert regions["state"] == "class State:\n    total: int\n    name: str"
    assert regions["fields"] == "total: int"
    assert regions["body"] == "return 1"


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("# region a\n# region a\n# endregion\n# endregion\n", "defined twice"),
        ("# region a\n", "not closed"),
        ("# endregion\n", "without a region"),
    ],
)
def test_region_errors(code, message):
    with pytest.raises(snippets.RegionError, match=message):
        snippets.parse_regions(code)


def test_sync_fills_and_check_detects_drift(lesson_dir):
    doc = lesson_dir / "docs/readalong.md"
    doc.write_text(
        "Intro\n\n<!-- snippet: src/pkg/graph.py#state -->\n<!-- /snippet -->\n\n"
        "<!-- snippet: src/pkg/graph.py -->\n<!-- /snippet -->\n"
    )
    changed, problems = snippets.sync(lesson_dir)
    assert problems == [] and changed == [doc]
    text = doc.read_text()
    assert "```python\nclass State:\n    total: int\n    name: str\n```" in text
    assert "# region" not in text  # markers never leak into docs
    assert snippets.sync(lesson_dir, write=False) == ([], [])

    (lesson_dir / "src/pkg/graph.py").write_text(CODE.replace("name: str", "label: str"))
    stale, _ = snippets.sync(lesson_dir, write=False)
    assert stale == [doc]


def test_sync_reports_bad_references(lesson_dir):
    (lesson_dir / "docs/notes.md").write_text(
        "<!-- snippet: src/pkg/graph.py#nope -->\n<!-- /snippet -->\n"
        "<!-- snippet: src/pkg/missing.py -->\n<!-- /snippet -->\n"
        "<!-- snippet: src/pkg/graph.py#body -->\n"
    )
    _, problems = snippets.sync(lesson_dir)
    text = "\n".join(str(p) for p in problems)
    assert "no region 'nope' (regions: body, fields, state)" in text
    assert "missing.py not found" in text
    assert "without <!-- /snippet -->" in text


def test_port_conflict_diagnosis(monkeypatch):
    from codelabgen import verify

    log = (
        "Error response from daemon: failed to set up container networking: driver failed "
        "programming external connectivity on endpoint x: Bind for 0.0.0.0:5432 failed: "
        "port is already allocated"
    )

    class Done:
        stdout = "other-postgres-1\tother-course\n"

    monkeypatch.setattr(verify.subprocess, "run", lambda *a, **k: Done())
    note = verify.explain_port_conflict(log)
    assert "port 5432 is used by container other-postgres-1" in note
    assert "docker compose -p other-course stop" in note
    assert verify.explain_port_conflict("some other error") == ""


def test_port_offset_moves_ports_and_urls():
    from codelabgen import services as svc

    moved = svc.with_offset(svc.CATALOG["postgres"], 120)
    assert moved.definition["ports"] == ["5552:5432"]
    assert moved.env[0].default == "postgresql://codelab:codelab@localhost:5552/codelab"
    assert svc.CATALOG["postgres"].definition["ports"] == ["5432:5432"]  # catalog untouched
    assert svc.published_ports(moved) == [(5552, 5432)]
    offset = svc.choose_offset(Path("/some/course"))
    assert offset % 10 == 0 and 10 <= offset <= 9000


def test_new_course_gets_own_ports_existing_env_keeps_standard(course, tmp_path):
    scaffold_course(course)
    offset = course.load_config().runtime.port_offset
    assert offset and f"- {5432 + offset}:5432" in (course.root / "docker-compose.yml").read_text()
    assert f"localhost:{5432 + offset}/" in (course.root / ".env").read_text()

    old = init_course(tmp_path / "old", topic="LangGraph")
    shutil.copy(FIXTURE, old.meta / "curriculum.yaml")
    (old.root / ".env").write_text(
        "POSTGRES_URL=postgresql://codelab:codelab@localhost:5432/codelab\n"
    )
    scaffold_course(old)
    assert old.load_config().runtime.port_offset == 0
    assert "- 5432:5432" in (old.root / "docker-compose.yml").read_text()
