"""Resuming: tasks, interrupted workers and `state next` in every phase."""

import shutil
from pathlib import Path

import pytest

from codelabgen import report, resume
from codelabgen import sources as src
from codelabgen.init import init_course
from codelabgen.models import Phase, Stage
from codelabgen.scaffold import scaffold_course
from codelabgen.state import StateError, StateStore, lesson_task_key

FIXTURE = Path(__file__).parent / "fixtures" / "langgraph-curriculum.yaml"


@pytest.fixture
def course(tmp_path):
    return init_course(
        tmp_path / "course", topic="LangGraph", language="ru", sources=["https://my.blog/post"]
    )


def go_to(course, phase: Phase):
    store = StateStore(course)
    for step in list(Phase)[1:]:
        current = store.load().phase
        if current is phase:
            return store
        store.advance_phase(step, approved=current in (Phase.GATE_SOURCES, Phase.GATE_PLAN))
    return store


def actions(course):
    return resume.next_actions(course)["actions"]


def kinds(course):
    return [
        (a["do"], a.get("agent") or a.get("to") or a.get("run") or a.get("about"))
        for a in actions(course)
    ]


# --- tasks ------------------------------------------------------------------------------------


def test_task_lifecycle_and_interruption(course):
    store = StateStore(course)
    assert store.start_task("recon:tech-scout").attempts == 1
    # The session dies here. A new session starts the same task again:
    again = StateStore(course).start_task("recon:tech-scout")
    assert again.attempts == 2 and "interrupted" in again.note
    store.finish_task("recon:tech-scout")
    with pytest.raises(StateError, match="already done"):
        store.start_task("recon:tech-scout")
    store.reset_task("recon:tech-scout")
    assert store.start_task("recon:tech-scout").attempts == 1

    store.start_task("sources:qa")
    store.finish_task("sources:qa", ok=False, note="search failed")
    assert store.start_task("sources:qa").attempts == 2  # a retry after a failure


# --- next actions, phase by phase -------------------------------------------------------------


def test_research_phases(course):
    assert kinds(course) == [("advance", Phase.RECON)]
    store = go_to(course, Phase.RECON)
    assert kinds(course) == [("run-agent", "tech-scout")]

    (course.meta / "research").mkdir()
    (course.meta / "research" / "overview.md").write_text("# LangGraph\n")
    assert actions(course)[0]["do"] == "ask-user"  # no version yet
    config = course.load_config()
    config.version = "1.2.15"
    course.save_config(config)
    assert kinds(course) == [("advance", Phase.SOURCES)]

    store.advance_phase(Phase.SOURCES)
    first = actions(course)
    assert first[0]["do"] == "command" and "my.blog" in first[0]["why"]  # user source first
    hunters = [a for a in first if a["do"] == "run-agent"]
    assert len(hunters) == 10 and hunters[1]["args"]["skill"] == "source-official-blog"

    src.add(
        course,
        [
            {
                "url": "https://my.blog/post",
                "type": "article",
                "roles": ["concepts"],
                "title": "t",
                "score": 1,
                "reason": "r",
                "status": "user",
            }
        ],
    )
    store.start_task("sources:official-docs")  # interrupted hunter
    for type_, _ in resume.HUNTERS[1:]:
        store.start_task(f"sources:{type_}")
        store.finish_task(f"sources:{type_}")
    result = resume.next_actions(course)
    assert [a["task"] for a in result["actions"]] == ["sources:official-docs"]
    assert result["actions"][0]["interrupted"] is True
    assert result["interrupted"][0]["task"] == "sources:official-docs"

    store.start_task("sources:official-docs")
    store.finish_task("sources:official-docs")
    assert kinds(course) == [("run-agent", "source-hunter")]  # deprecations.md is missing
    (course.meta / "research" / "deprecations.md").write_text("# none\n")
    assert kinds(course) == [
        ("command", "codelabgen sources render"),
        ("advance", Phase.GATE_SOURCES),
    ]


def test_topics_and_curriculum_phases(course):
    store = go_to(course, Phase.TOPICS)
    rows = [
        {
            "url": f"https://docs.x/{i}",
            "type": "official-docs",
            "roles": ["concepts"],
            "title": "t",
            "score": 0.9,
            "reason": "r",
            "status": "kept",
        }
        for i in range(7)
    ]
    src.add(course, rows)
    extractors = actions(course)
    assert [len(a["args"]["sources"]) for a in extractors] == [5, 2]

    for s in src.used(course):
        body = "\n\n".join(f"## {name}\n\nx" for name in src.DIGEST_SECTIONS)
        path = src.digest_path(course, s.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nid: {s.id}\n---\n{body}\n")
    assert kinds(course)[-1] == ("advance", Phase.CURRICULUM)

    store.advance_phase(Phase.CURRICULUM)
    first = actions(course)[0]
    assert (
        first["agent"] == "curriculum-architect"
        and "does not exist" in first["args"]["problems"][0]
    )
    (course.meta / "curriculum.yaml").write_text("title: broken\n")
    assert actions(course)[0]["agent"] == "curriculum-architect"  # invalid, so redo
    shutil.copy(FIXTURE, course.meta / "curriculum.yaml")
    assert kinds(course) == [("run-agent", "runtime-planner")]
    (course.meta / "research").mkdir(exist_ok=True)
    (course.meta / "research" / "runtime.md").write_text("# Runtime\n")
    config = course.load_config()
    config.runtime.kind = "python-uv"
    course.save_config(config)
    assert kinds(course)[-1] == ("advance", Phase.GATE_PLAN)


def test_scaffold_lessons_and_interrupted_lesson(course):
    shutil.copy(FIXTURE, course.meta / "curriculum.yaml")
    store = go_to(course, Phase.SCAFFOLD)
    assert kinds(course) == [
        ("command", "codelabgen scaffold course"),
        ("command", "codelabgen toc"),
    ]
    scaffold_course(course)
    assert kinds(course) == [("advance", Phase.LESSONS)]  # postgres URL has a default

    store.advance_phase(Phase.LESSONS)
    lesson = resume.next_actions(course)["lessons"][0]
    assert (lesson["lesson"], lesson["task"], lesson["interrupted"]) == (
        "1.1",
        "lesson:1.1:spec",
        False,
    )

    # The example-designer is killed midway through lesson 1.1.
    store.start_task(lesson_task_key("1.1", Stage.SPEC), lesson="1.1")
    resumed = resume.next_actions(course)
    assert resumed["lessons"][0]["interrupted"] is True
    assert resumed["interrupted"] == [
        {"task": "lesson:1.1:spec", "phase": Phase.LESSONS, "lesson": "1.1", "attempts": 1}
    ]

    # The resumed session redoes the stage and records it.
    assert store.start_task("lesson:1.1:spec", lesson="1.1").attempts == 2
    store.set_stage("1.1", Stage.SPEC)
    store.finish_task("lesson:1.1:spec")
    after = resume.next_actions(course)
    assert after["interrupted"] == [] and after["lessons"][0]["next_stage"] == Stage.CODE


def test_report(course):
    shutil.copy(FIXTURE, course.meta / "curriculum.yaml")
    store = go_to(course, Phase.SCAFFOLD)
    scaffold_course(course)
    store.advance_phase(Phase.LESSONS)
    store.start_task("lesson:1.1:spec", lesson="1.1")
    text = report.build(course).read_text()
    assert "# Generation report: LangGraph" in text
    assert "| 1.1 | pending | 0 | 0 | 0 | — |" in text
    assert "`lesson:1.1:spec`: running" in text


def test_quick_course_settings(tmp_path):
    course = init_course(
        tmp_path / "quick",
        topic="humanize",
        source_types=["official-docs", "qa"],
        wishes="At most 3 lessons",
        sources_per_type=2,
    )
    config = course.load_config()
    assert config.source_types == ["official-docs", "qa"] and config.budgets.sources_per_type == 2
    store = go_to(course, Phase.SOURCES)
    hunters = [a["args"]["type"] for a in actions(course) if a["do"] == "run-agent"]
    assert hunters == ["official-docs", "qa"]
    for type_ in hunters:
        store.start_task(f"sources:{type_}")
        store.finish_task(f"sources:{type_}")
    assert kinds(course)[0] == ("command", "codelabgen sources render")  # no deprecations needed
    with pytest.raises(Exception, match="unknown source types: blogs"):
        init_course(tmp_path / "bad", topic="x", source_types=["blogs"])
