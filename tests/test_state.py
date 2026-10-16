import json

import pytest
from typer.testing import CliRunner

from codelabgen.cli import app
from codelabgen.course import Course, CourseNotFound
from codelabgen.init import InitError, init_course
from codelabgen.models import Phase, Stage
from codelabgen.state import StateError, StateStore


@pytest.fixture
def store(tmp_path):
    course = init_course(tmp_path / "course", topic="LangGraph", language="ru")
    return StateStore(course)


def walk_to_lessons(store: StateStore) -> None:
    for phase in Phase:
        if phase is Phase.INIT:
            continue
        current = store.load().phase
        store.advance_phase(phase, approved=current in (Phase.GATE_SOURCES, Phase.GATE_PLAN))
        if phase is Phase.LESSONS:
            return


# --- init ---------------------------------------------------------------------------


def test_init_creates_meta(store):
    course = store.course
    assert course.load_config().topic == "LangGraph"
    assert store.load().phase is Phase.INIT
    assert json.loads(course.events_path.read_text().splitlines()[0])["kind"] == "init"


def test_init_refuses_existing_course(store):
    with pytest.raises(InitError, match="already"):
        init_course(store.course.root, topic="x")


def test_init_refuses_non_empty_dir(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    with pytest.raises(InitError, match="not empty"):
        init_course(tmp_path, topic="x")
    init_course(tmp_path, topic="x", force=True)


def test_course_find_walks_up(store, monkeypatch):
    nested = store.course.root / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.delenv("CODELABGEN_COURSE", raising=False)
    assert Course.find().root == store.course.root


def test_course_find_fails_outside(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CODELABGEN_COURSE", raising=False)
    with pytest.raises(CourseNotFound):
        Course.find()


# --- phases ---------------------------------------------------------------------------


def test_phases_advance_one_at_a_time(store):
    store.advance_phase(Phase.RECON)
    with pytest.raises(StateError, match="cannot move"):
        store.advance_phase(Phase.TOPICS)


def test_gate_requires_approval(store):
    for phase in (Phase.RECON, Phase.SOURCES, Phase.GATE_SOURCES):
        store.advance_phase(phase)
    with pytest.raises(StateError, match="review gate"):
        store.advance_phase(Phase.TOPICS)
    state = store.advance_phase(Phase.TOPICS, approved=True)
    assert state.approved_gates == [Phase.GATE_SOURCES]


def test_assembly_needs_all_lessons_done(store):
    walk_to_lessons(store)
    store.register(["1.1"])
    with pytest.raises(StateError, match="not done"):
        store.advance_phase(Phase.ASSEMBLY)


# --- lessons --------------------------------------------------------------------------


def test_register_sorts_numerically_and_validates(store):
    store.register(["1.10", "1.2", "2.1.1"])
    assert list(store.load().lessons) == ["1.2", "1.10", "2.1.1"]
    with pytest.raises(ValueError):
        store.register(["1.2.3.4"])


def test_forward_one_stage_only(store):
    store.register(["1.1"])
    store.set_stage("1.1", Stage.SPEC)
    with pytest.raises(StateError, match="cannot skip"):
        store.set_stage("1.1", Stage.READALONG)


def test_rework_counts_review_rounds_and_enforces_budget(store):
    store.register(["1.1"])
    for stage in (Stage.SPEC, Stage.CODE, Stage.VERIFIED, Stage.READALONG, Stage.NOTES):
        store.set_stage("1.1", stage)
    budget = store.course.load_config().budgets.review_rounds
    for _ in range(budget):
        store.set_stage("1.1", Stage.READALONG, note="reviewer: revise")
        store.set_stage("1.1", Stage.NOTES)
    assert store.load().lessons["1.1"].review_rounds == budget
    with pytest.raises(StateError, match="review budget"):
        store.set_stage("1.1", Stage.READALONG)


def test_failures_block_after_budget(store):
    store.register(["1.1"])
    store.set_stage("1.1", Stage.SPEC)
    store.set_stage("1.1", Stage.CODE)
    budget = store.course.load_config().budgets.fix_attempts
    for _ in range(budget - 1):
        assert store.record_failure("1.1").stage is Stage.CODE
    assert store.record_failure("1.1").stage is Stage.BLOCKED
    store.unblock("1.1")
    lesson = store.load().lessons["1.1"]
    assert (lesson.stage, lesson.fix_attempts) == (Stage.CODE, 0)


def test_failure_only_at_code(store):
    store.register(["1.1"])
    with pytest.raises(StateError, match="failures count"):
        store.record_failure("1.1")


def test_stale_only_from_done_and_must_be_redone(store):
    store.register(["1.1"])
    with pytest.raises(StateError, match="only done"):
        store.mark_stale("1.1", "upstream changed")
    for stage in Stage:
        if stage in (Stage.PENDING, Stage.BLOCKED, Stage.STALE):
            continue
        store.set_stage("1.1", stage)
    store.mark_stale("1.1", "1.0 rewritten")
    with pytest.raises(StateError, match="redone"):
        store.set_stage("1.1", Stage.DONE)
    assert store.set_stage("1.1", Stage.CODE).lessons["1.1"].stage is Stage.CODE


def test_unknown_lesson(store):
    with pytest.raises(StateError, match="unknown lesson"):
        store.set_stage("9.9", Stage.SPEC)


# --- scheduling -------------------------------------------------------------------------


def test_next_outside_lessons_phase(store):
    work = store.next_work()
    assert work["phase"] == Phase.INIT and work["lessons"] == []


def test_next_runs_modules_in_parallel_and_lessons_in_order(store):
    walk_to_lessons(store)
    store.register(["1.1", "1.2", "2.1", "3.1"])
    work = store.next_work()
    assert [item["lesson"] for item in work["lessons"]] == ["1.1", "2.1"]  # parallel_modules=2
    assert work["lessons"][0]["action"] == "example-designer"


def test_next_skips_blocked_modules(store):
    walk_to_lessons(store)
    store.register(["1.1", "1.2", "2.1"])
    store.block("1.1", reason="needs a decision")
    work = store.next_work()
    assert [item["lesson"] for item in work["lessons"]] == ["2.1"]
    assert work["blocked"][0]["lesson"] == "1.1"


# --- CLI ------------------------------------------------------------------------------------


def test_cli_roundtrip(tmp_path, monkeypatch):
    runner = CliRunner()
    target = tmp_path / "course"
    result = runner.invoke(app, ["init", str(target), "--topic", "LangGraph", "--lang", "ru"])
    assert result.exit_code == 0, result.output
    monkeypatch.setenv("CODELABGEN_COURSE", str(target))
    assert runner.invoke(app, ["state", "phase", "recon"]).exit_code == 0
    result = runner.invoke(app, ["state", "show", "--json"])
    assert json.loads(result.output)["phase"] == "recon"
    result = runner.invoke(app, ["state", "next"])
    assert json.loads(result.output)["phase"] == "recon"
