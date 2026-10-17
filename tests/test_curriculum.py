"""Topics, digests, curriculum numbering, plan rendering and custom services."""

import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from codelabgen import curriculum as cur
from codelabgen import services, topics
from codelabgen import sources as src
from codelabgen.cli import app
from codelabgen.init import init_course

FIXTURE = Path(__file__).parent / "fixtures" / "langgraph-curriculum.yaml"


@pytest.fixture
def course(tmp_path):
    return init_course(tmp_path / "course", topic="LangGraph", language="ru", version="1.2.15")


def add_source(course, url, type_="official-docs", status="kept", roles=("concepts",)):
    report = src.add(
        course,
        [
            {
                "url": url,
                "type": type_,
                "roles": list(roles),
                "title": url,
                "score": 0.9,
                "reason": "r",
                "status": status,
            }
        ],
    )
    return (report.added or report.merged)[0]


def write_digest(course, source_id, sections=src.DIGEST_SECTIONS):
    body = "\n\n".join(f"## {name}\n\ntext about {name}" for name in sections)
    path = src.digest_path(course, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nid: {source_id}\n---\n{body}\n")


# --- topics -----------------------------------------------------------------------------------


def test_topics_add_replace_and_merge(course):
    a = add_source(course, "https://docs.x/a")
    b = add_source(course, "https://blog.x/b", "official-blog", roles=("structure",))
    row = {
        "name": "StateGraph",
        "summary": "s",
        "difficulty": 1,
        "apis": ["StateGraph"],
        "evidence_url": "https://docs.x/a#g",
    }
    assert topics.add(course, a, [row, row | {"name": "Reducers", "difficulty": 2}]) == 2
    assert topics.add(course, a, [row]) == 1  # replaces, never duplicates
    topics.add(
        course,
        b,
        [
            row | {"name": "state graph", "difficulty": 3},
            row | {"name": "Checkpointer", "difficulty": 3},
        ],
    )
    items, path = topics.merge(course)
    by_name = {t.name: t for t in items}
    assert set(by_name) == {"StateGraph", "Checkpointer"}  # "state graph" merged
    assert len(by_name["StateGraph"].sources) == 2 and by_name["StateGraph"].difficulty == 2.0
    assert "| StateGraph | 2.0 | 2 | 1 |" in path.read_text()


def test_topics_reject_unknown_source(course):
    with pytest.raises(topics.TopicsError, match="unknown source"):
        topics.add(course, "nope", [])


# --- digests ----------------------------------------------------------------------------------


def test_pending_digests_batches_and_index(course):
    ids = [add_source(course, f"https://docs.x/{i}") for i in range(3)]
    dropped = add_source(course, "https://bad.x", "article", status="dropped")
    user = add_source(course, "https://talk.x", "talk-workshop", status="user")
    write_digest(course, ids[0])
    write_digest(course, ids[1], sections=("Summary",))

    pending = {s.id for s in src.pending_digests(course)}
    assert pending == {ids[1], ids[2], user}  # dropped sources need no digest
    assert "no '## Topics covered' section" in src.digest_problems(
        course, src.load(course)[1]
    ) or src.digest_problems(course, next(s for s in src.load(course) if s.id == ids[1]))
    assert src.batches(course, size=1) == [[ids[1]], [ids[2]], [user]]
    assert dropped not in sum(src.batches(course, size=10, only_pending=False), [])

    index = src.build_index(course).read_text()
    assert "## concepts" in index and f"]({ids[0]}.md)" in index and "(no digest yet)" in index


# --- curriculum -------------------------------------------------------------------------------


def test_number_assigns_ids_and_rewrites_references(course):
    data = yaml.safe_load(FIXTURE.read_text())
    lessons = data["modules"][0]["children"]
    lessons.insert(0, lessons.pop(2))  # move 1.3 to the front: ids are now stale
    lessons.insert(0, lessons.pop(1))  # order: 1.1, 1.3, 1.2
    del lessons[2]["id"]  # and one node has no id at all
    lessons[1]["prerequisites"] = ["1.1"]
    lessons[1]["example"] = {"name": "ticket-router", "mode": "new"}
    lessons[2]["example"] = {"name": "ticket-router", "mode": "extend", "from": "1.3"}
    data["env"] = [{"name": "X", "description": "x", "lessons": ["1.3"]}]
    (course.meta / "curriculum.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))

    assert cur.number(course) == {"1.3": "1.2"}
    curriculum = cur.load(course)
    ids = [lesson.id for lesson in cur.lessons(curriculum)]
    assert ids == ["1.1", "1.2", "1.3"]
    third = cur.lessons(curriculum)[2]
    assert third.node.slug == "routing" and third.node.example.from_lesson == "1.2"
    assert curriculum.env[0].lessons == ["1.2"]


def test_references_to_sources_and_services(course):
    kept = add_source(course, "https://docs.x/a")
    dropped = add_source(course, "https://bad.x", status="dropped")
    data = yaml.safe_load(FIXTURE.read_text())
    lessons = data["modules"][0]["children"]
    lessons[0]["sources"] = [kept, dropped]
    lessons[1]["services"] = ["qdrant"]
    (course.meta / "curriculum.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(cur.CurriculumError) as error:
        cur.load(course)
    text = str(error.value)
    assert f"source {dropped} is not a kept source" in text and kept not in text
    assert "unknown service 'qdrant'" in text

    services.custom_path(course.meta).write_text(
        yaml.safe_dump(
            {
                "qdrant": {
                    "definition": {"image": "qdrant/qdrant:v1.15", "ports": ["6333:6333"]},
                    "env": [
                        {
                            "name": "QDRANT_URL",
                            "description": "Qdrant",
                            "default": "http://localhost:6333",
                        }
                    ],
                },
            }
        )
    )
    lessons[0]["sources"] = [kept]
    (course.meta / "curriculum.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    cur.load(course)  # now valid
    assert services.resolve(["qdrant"], course.meta)[0].env[0].name == "QDRANT_URL"


def test_render_plan(course):
    source_id = add_source(course, "https://docs.x/a")
    data = yaml.safe_load(FIXTURE.read_text())
    data["modules"][0]["children"][0]["sources"] = [source_id]
    data["env"] = [
        {
            "name": "OPENAI_API_KEY",
            "description": "Ключ OpenAI",
            "secret": True,
            "where_to_get": "platform.openai.com",
        }
    ]
    (course.meta / "curriculum.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    text = cur.render_plan(course).read_text()
    assert text.startswith("# План курса: LangGraph на практике")
    assert "1 модулей, 3 уроков" in text
    assert "Пример: `ticket-router`, продолжает 1.2 Условные рёбра и маршрутизация" in text
    assert "Сервисы: postgres" in text and "Источники: https://docs.x/a" in text
    assert "| `OPENAI_API_KEY` | Ключ OpenAI — platform.openai.com | ✓ | все |" in text


# --- CLI --------------------------------------------------------------------------------------


def test_cli_config_runtime_and_external(course, monkeypatch):
    monkeypatch.setenv("CODELABGEN_COURSE", str(course.root))
    runner = CliRunner()
    assert runner.invoke(app, ["config", "set", "runtime.per", "lesson"]).exit_code == 0
    assert runner.invoke(app, ["config", "set", "runtime.per", "bogus"]).exit_code != 0
    result = runner.invoke(
        app,
        ["config", "external", "add", "openai", "--model", "gpt-5-mini", "--env", "OPENAI_API_KEY"],
    )
    assert result.exit_code == 0, result.output
    config = course.load_config()
    assert config.runtime.per == "lesson"
    assert config.external[0].models == ["gpt-5-mini"]


def test_cli_number_refuses_after_scaffold(course, monkeypatch):
    from codelabgen.scaffold import scaffold_course

    shutil.copy(FIXTURE, course.meta / "curriculum.yaml")
    scaffold_course(course)
    monkeypatch.setenv("CODELABGEN_COURSE", str(course.root))
    result = CliRunner().invoke(app, ["curriculum", "number"])
    assert result.exit_code != 0
