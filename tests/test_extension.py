"""Extending a finished course: delta, apply, renumbering and stale lessons."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from codelabgen import extension as ext
from codelabgen import resume
from codelabgen.init import init_course
from codelabgen.models import Phase, Stage
from codelabgen.scaffold import scaffold_course
from codelabgen.state import StateStore

FIXTURE = Path(__file__).parent / "fixtures" / "langgraph-curriculum.yaml"


def git(course, *args):
    subprocess.run(
        ["git", "-C", str(course.root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def course(tmp_path):
    """A finished three-lesson course: code, docs with cross-links, specs, all committed."""
    course = init_course(tmp_path / "course", topic="LangGraph", language="ru")
    shutil.copy(FIXTURE, course.meta / "curriculum.yaml")
    store = StateStore(course)
    for phase in list(Phase)[1:8]:  # up to scaffold
        current = store.load().phase
        store.advance_phase(phase, approved=current in (Phase.GATE_SOURCES, Phase.GATE_PLAN))
    scaffold_course(course)
    store.advance_phase(Phase.LESSONS)
    root = course.root / "1-basics"
    (root / "1.2-routing/src/l1_2_routing/graph.py").write_text(
        "from l1_2_routing.state import TicketState\n"
    )
    (root / "1.2-routing/docs/notes.md").write_text(
        "# Notes\n\nSee [1.1](../../1.1-hello-graph/README.md).\n"
    )
    (root / "1.3-persistence/docs/readalong.md").write_text(
        "Continues [routing](../../1.2-routing/README.md).\n"
        "<!-- snippet: src/l1_3_persistence/graph.py -->\n<!-- /snippet -->\n"
    )
    for lesson_id in ("1.1", "1.2", "1.3"):
        spec = course.meta / "lessons" / lesson_id / "spec.yaml"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(
            yaml.safe_dump(
                {
                    "id": lesson_id,
                    "title": "t",
                    "scenario": "s",
                    "files": [],
                    "run_cmd": "python -m x",
                    "delta_from": "1.2" if lesson_id == "1.3" else None,
                }
            )
        )
        for stage in list(Stage)[1:8]:
            store.set_stage(lesson_id, stage)
    git(course, "add", "-A")
    git(course, "commit", "-q", "-m", "course")
    return course


def propose(course, mutate):
    data = yaml.safe_load((course.meta / "curriculum.yaml").read_text())
    mutate(data["modules"][0]["children"], data)
    path = ext.proposed_path(course, ext.current(course).id)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return path


def to_gate(course):
    for stage in ("research", "digests", "delta", "gate"):
        ext.set_stage(course, stage)


def new_lesson(lesson_id, slug, **extra):
    return {"id": lesson_id, "title": f"Урок {slug}", "slug": slug, "summary": "s"} | extra


# --- starting ---------------------------------------------------------------------------------


def test_start_needs_finished_clean_course(course):
    (course.root / "stray.txt").write_text("x")
    with pytest.raises(ext.ExtensionError, match="uncommitted"):
        ext.start(course, "add streaming")
    (course.root / "stray.txt").unlink()
    extension = ext.start(course, "add streaming")
    assert extension.id == 1 and (ext.ext_dir(course, 1) / "request.md").is_file()
    with pytest.raises(ext.ExtensionError, match="still in progress"):
        ext.start(course, "again")
    actions = resume.next_actions(course)
    assert actions["extension"]["stage"] == "gaps"
    assert actions["actions"][0]["agent"] == "gap-analyst"


def test_stages_move_one_at_a_time(course):
    ext.start(course, "x")
    with pytest.raises(ext.ExtensionError, match="can only move to research"):
        ext.set_stage(course, "delta")
    to_gate(course)
    with pytest.raises(ext.ExtensionError, match="extend apply"):
        ext.set_stage(course, "lessons")


# --- appending (no renumbering) ---------------------------------------------------------------


def test_append_lesson(course):
    ext.start(course, "add a lesson on streaming")
    to_gate(course)
    propose(course, lambda lessons, _: lessons.append(new_lesson("1.4", "streaming")))
    delta = ext.compute_delta(course, ext.proposed_path(course, 1))
    assert [lesson.id for lesson in delta.added] == ["1.4"] and not delta.moved

    result = ext.apply(course)
    assert result["added"] == ["1.4"] and result["moved"] == {}
    state = StateStore(course).load()
    assert state.phase is Phase.LESSONS and state.extension.stage == "lessons"
    assert state.lessons["1.4"].stage is Stage.PENDING
    assert state.lessons["1.3"].stage is Stage.DONE
    assert (course.root / "1-basics/1.4-streaming/src/l1_4_streaming/__init__.py").exists()
    assert '"1.4-streaming"' in (course.root / "1-basics/pyproject.toml").read_text()


# --- inserting (renumbering) ------------------------------------------------------------------


def test_insert_needs_permission_then_moves_everything(course):
    ext.start(course, "add a lesson between 1.1 and 1.2")
    to_gate(course)

    def insert(lessons, data):
        lessons.insert(1, new_lesson("1.2", "reducers"))
        lessons[2]["id"], lessons[3]["id"] = "1.3", "1.4"
        lessons[2]["prerequisites"] = ["1.1"]
        lessons[3]["prerequisites"] = ["1.3"]
        lessons[3]["example"]["from"] = "1.3"

    propose(course, insert)
    with pytest.raises(ext.ExtensionError, match=r"renumbers lessons: 1.2→1.3, 1.3→1.4"):
        ext.apply(course)

    result = ext.apply(course, allow_renumber=True)
    assert result["moved"] == {"1.2": "1.3", "1.3": "1.4"} and result["added"] == ["1.2"]
    assert result["rewrite"] == []  # only ids changed, so the example counts as the same

    module = course.root / "1-basics"
    routing = module / "1.3-routing"
    assert (routing / "src/l1_3_routing/graph.py").read_text() == (
        "from l1_3_routing.state import TicketState\n"
    )
    assert 'name = "l1-3-routing"' in (routing / "pyproject.toml").read_text()
    persistence = module / "1.4-persistence"
    readalong = (persistence / "docs/readalong.md").read_text()
    assert "../../1.3-routing/README.md" in readalong
    assert "src/l1_4_persistence/graph.py" in readalong
    assert (module / "1.2-reducers/src/l1_2_reducers/__init__.py").exists()  # the new lesson

    spec = yaml.safe_load((course.meta / "lessons/1.4/spec.yaml").read_text())
    assert (spec["id"], spec["delta_from"]) == ("1.4", "1.3")
    state = StateStore(course).load()
    assert list(state.lessons) == ["1.1", "1.2", "1.3", "1.4"]
    assert state.lessons["1.2"].stage is Stage.PENDING
    assert state.lessons["1.3"].stage is Stage.DONE and state.lessons["1.4"].stage is Stage.DONE


# --- rewriting and stale lessons --------------------------------------------------------------


def test_rewrite_marks_followers_stale(course):
    ext.start(course, "deepen routing")
    to_gate(course)

    def deepen(lessons, _):
        lessons[1]["objectives"].append("Сравнить path_map и Literal")
        lessons[0]["title"] = "Первый граф"

    propose(course, deepen)
    delta = ext.compute_delta(course, ext.proposed_path(course, 1))
    assert [new.id for _, new, _ in delta.changed] == ["1.2"]
    assert [new.id for _, new in delta.retitled] == ["1.1"]
    text = ext.render_delta(course, delta, 1).read_text()
    assert "## Lessons to rewrite" in text and "## Lessons to re-check" in text

    result = ext.apply(course)
    assert result["rewrite"] == ["1.2"] and result["stale"] == ["1.3"]
    lessons = StateStore(course).load().lessons
    assert lessons["1.2"].stage is Stage.PENDING and lessons["1.3"].stage is Stage.STALE
    assert lessons["1.1"].stage is Stage.DONE
    work = resume.next_actions(course)["lessons"]
    assert [item["lesson"] for item in work] == ["1.2"]  # 1.3 waits for 1.2 (same module)


def test_removal_is_refused(course):
    ext.start(course, "drop persistence")
    to_gate(course)
    propose(course, lambda lessons, _: lessons.pop())
    with pytest.raises(ext.ExtensionError, match="removes lessons: 1.3"):
        ext.apply(course)


def test_finish_after_assembly(course):
    ext.start(course, "add streaming")
    to_gate(course)
    propose(course, lambda lessons, _: lessons.append(new_lesson("1.4", "streaming")))
    ext.apply(course)
    with pytest.raises(Exception, match="assemble the course first"):
        ext.finish(course)
    store = StateStore(course)
    for stage in list(Stage)[1:8]:
        store.set_stage("1.4", stage)
    store.advance_phase(Phase.ASSEMBLY)
    store.advance_phase(Phase.DONE)
    assert resume.next_actions(course)["actions"][0]["run"] == "codelabgen extend finish"
    assert ext.finish(course).stage == "done"
    assert StateStore(course).load().extension is None
