"""The course state machine: phases, lesson stages and the event log.

All changes go through `StateStore.transaction()`, which holds a file lock,
validates the result and writes it atomically. Agents never edit state.json.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from filelock import FileLock

from codelabgen.course import Course, atomic_write, dump_json
from codelabgen.models import (
    GATES,
    PHASE_ORDER,
    STAGE_ORDER,
    Event,
    LessonState,
    Phase,
    Stage,
    State,
    lesson_sort_key,
    now,
    validate_lesson_id,
)


class StateError(Exception):
    pass


# Which agent (or script) advances a lesson out of each stage. The orchestrator uses this.
NEXT_ACTION: dict[Stage, tuple[Stage, str]] = {
    Stage.PENDING: (Stage.SPEC, "example-designer"),
    Stage.SPEC: (Stage.CODE, "code-author"),
    Stage.CODE: (Stage.VERIFIED, "codelabgen verify (code-fixer on failure)"),
    Stage.VERIFIED: (Stage.READALONG, "readalong-writer"),
    Stage.READALONG: (Stage.NOTES, "notes-writer"),
    Stage.NOTES: (Stage.REVIEWED, "lesson-reviewer"),
    Stage.REVIEWED: (Stage.DONE, "orchestrator (final checks)"),
}

# The work done during each phase; the orchestrator advances when it is finished.
PHASE_ACTION: dict[Phase, str] = {
    Phase.INIT: "course created: advance to recon",
    Phase.RECON: "tech-scout: write research/overview.md",
    Phase.SOURCES: "source-hunter per source type: fill sources.jsonl, render sources.md",
    Phase.GATE_SOURCES: "wait for the user to approve the sources (/codelabgen:sources)",
    Phase.TOPICS: "topic-extractor: topics/*.jsonl and source digests",
    Phase.CURRICULUM: "curriculum-architect + runtime-planner: curriculum.yaml, plan.md",
    Phase.GATE_PLAN: "wait for the user to approve plan and external services (/codelabgen:plan)",
    Phase.SCAFFOLD: "codelabgen scaffold course",
    Phase.LESSONS: "codelabgen state next",
    Phase.ASSEMBLY: "codelabgen toc, site build, commit",
    Phase.DONE: "nothing to do",
}


class StateStore:
    def __init__(self, course: Course):
        self.course = course
        self._lock = FileLock(str(course.lock_path), timeout=30)

    def load(self) -> State:
        return State.model_validate_json(self.course.state_path.read_text())

    def save(self, state: State) -> None:
        state.updated = now()
        atomic_write(self.course.state_path, dump_json(state))

    def log(self, kind: str, lesson: str | None = None, **data: Any) -> None:
        event = Event(kind=kind, lesson=lesson, data=data)
        with self.course.events_path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json(exclude_none=True) + "\n")

    @contextmanager
    def transaction(self) -> Iterator[State]:
        with self._lock:
            state = self.load()
            yield state
            State.model_validate(state.model_dump())  # re-validate before writing
            self.save(state)

    # --- phases -------------------------------------------------------------

    def advance_phase(self, target: Phase, approved: bool = False) -> State:
        with self.transaction() as state:
            current = PHASE_ORDER.index(state.phase)
            wanted = PHASE_ORDER.index(target)
            if wanted != current + 1:
                expected = PHASE_ORDER[current + 1] if current + 1 < len(PHASE_ORDER) else "none"
                raise StateError(
                    f"cannot move from phase {state.phase} to {target}; next phase is {expected}"
                )
            if state.phase in GATES:
                if not approved:
                    raise StateError(
                        f"phase {state.phase} is a review gate; "
                        "pass --approved once the user approved"
                    )
                state.approved_gates.append(state.phase)
            if target is Phase.ASSEMBLY:
                unfinished = [i for i, s in state.lessons.items() if s.stage is not Stage.DONE]
                if unfinished:
                    raise StateError(f"lessons not done: {', '.join(unfinished)}")
            previous = state.phase
            state.phase = target
        self.log("phase", frm=previous, to=target)
        return state

    # --- lessons ------------------------------------------------------------

    def register(self, lesson_ids: list[str]) -> State:
        for lesson_id in lesson_ids:
            validate_lesson_id(lesson_id)
        with self.transaction() as state:
            added = [i for i in lesson_ids if i not in state.lessons]
            for lesson_id in added:
                state.lessons[lesson_id] = LessonState()
            state.lessons = dict(
                sorted(state.lessons.items(), key=lambda kv: lesson_sort_key(kv[0]))
            )
        if added:
            self.log("register", ids=added)
        return state

    def set_stage(self, lesson_id: str, target: Stage, note: str | None = None) -> State:
        """Move a lesson one stage forward, or back to any earlier stage (rework)."""
        if target in (Stage.BLOCKED, Stage.STALE):
            raise StateError(f"use the dedicated command for {target}")
        review_budget = self.course.load_config().budgets.review_rounds
        with self.transaction() as state:
            lesson = self._get(state, lesson_id)
            source = lesson.blocked_from if lesson.stage is Stage.BLOCKED else lesson.stage
            if lesson.stage is Stage.STALE:
                source = Stage.DONE
                if target is Stage.DONE:
                    raise StateError("a stale lesson must be redone from an earlier stage")
            pos_from, pos_to = STAGE_ORDER.index(source), STAGE_ORDER.index(target)
            if pos_to == pos_from + 1:
                kind = "advance"
                if target is Stage.VERIFIED:
                    lesson.fix_attempts = 0
            elif pos_to <= pos_from:
                kind = "rework"
                if lesson.stage is not Stage.STALE and source in (Stage.NOTES, Stage.REVIEWED):
                    if lesson.review_rounds >= review_budget:
                        raise StateError(
                            f"lesson {lesson_id}: review budget ({review_budget}) used up; "
                            "accept the lesson as is or block it for the user"
                        )
                    lesson.review_rounds += 1
            else:
                raise StateError(
                    f"lesson {lesson_id}: cannot skip from {source} to {target}; "
                    f"next stage is {STAGE_ORDER[pos_from + 1]}"
                )
            lesson.stage, lesson.blocked_from, lesson.note = target, None, note
            lesson.updated = now()
        self.log(kind, lesson_id, frm=source, to=target, note=note)
        return state

    def record_failure(self, lesson_id: str, note: str | None = None) -> LessonState:
        """Count a failed verify; block the lesson when the fix budget is used up."""
        budget = self.course.load_config().budgets.fix_attempts
        with self.transaction() as state:
            lesson = self._get(state, lesson_id)
            if lesson.stage is not Stage.CODE:
                raise StateError(
                    f"lesson {lesson_id} is at {lesson.stage}, failures count at 'code'"
                )
            lesson.fix_attempts += 1
            lesson.note, lesson.updated = note, now()
            if lesson.fix_attempts >= budget:
                lesson.blocked_from, lesson.stage = lesson.stage, Stage.BLOCKED
        self.log("verify-failed", lesson_id, attempt=lesson.fix_attempts, budget=budget, note=note)
        if lesson.stage is Stage.BLOCKED:
            self.log("blocked", lesson_id, reason="fix budget used up")
        return lesson

    def block(self, lesson_id: str, reason: str) -> State:
        with self.transaction() as state:
            lesson = self._get(state, lesson_id)
            if lesson.stage is Stage.BLOCKED:
                raise StateError(f"lesson {lesson_id} is already blocked")
            lesson.blocked_from, lesson.stage = lesson.stage, Stage.BLOCKED
            lesson.note, lesson.updated = reason, now()
        self.log("blocked", lesson_id, reason=reason)
        return state

    def unblock(self, lesson_id: str) -> State:
        with self.transaction() as state:
            lesson = self._get(state, lesson_id)
            if lesson.stage is not Stage.BLOCKED:
                raise StateError(f"lesson {lesson_id} is not blocked")
            lesson.stage, lesson.blocked_from = lesson.blocked_from or Stage.PENDING, None
            lesson.fix_attempts, lesson.note, lesson.updated = 0, None, now()
        self.log("unblocked", lesson_id, to=lesson.stage)
        return state

    def mark_stale(self, lesson_id: str, reason: str) -> State:
        with self.transaction() as state:
            lesson = self._get(state, lesson_id)
            if lesson.stage is not Stage.DONE:
                raise StateError(
                    f"only done lessons can become stale ({lesson_id} is {lesson.stage})"
                )
            lesson.stage, lesson.note, lesson.updated = Stage.STALE, reason, now()
        self.log("stale", lesson_id, reason=reason)
        return state

    # --- scheduling -----------------------------------------------------------

    def next_work(self) -> dict[str, Any]:
        """What the orchestrator should do next.

        Lessons of one module run in order (examples build on each other), so each
        module offers at most its first unfinished lesson. Up to `parallel_modules`
        modules are offered at once.
        """
        state = self.load()
        if state.phase is not Phase.LESSONS:
            return {"phase": state.phase, "action": PHASE_ACTION[state.phase], "lessons": []}

        parallel = self.course.load_config().budgets.parallel_modules
        modules: dict[str, list[str]] = {}
        for lesson_id in state.lessons:
            modules.setdefault(lesson_id.split(".")[0], []).append(lesson_id)

        items, blocked = [], []
        for ids in modules.values():
            first = next((i for i in ids if state.lessons[i].stage is not Stage.DONE), None)
            if first is None:
                continue
            lesson = state.lessons[first]
            if lesson.stage is Stage.BLOCKED:
                blocked.append({"lesson": first, "note": lesson.note})
                continue
            if lesson.stage is Stage.STALE:
                items.append(
                    {
                        "lesson": first,
                        "stage": "stale",
                        "next_stage": Stage.CODE,
                        "action": "codelabgen verify, then rework as the review decides",
                    }
                )
            else:
                next_stage, action = NEXT_ACTION[lesson.stage]
                items.append(
                    {
                        "lesson": first,
                        "stage": lesson.stage,
                        "next_stage": next_stage,
                        "action": action,
                    }
                )
            if len(items) >= parallel:
                break

        if not items and not blocked:
            action = "all lessons done: advance to assembly"
        elif not items:
            action = "only blocked lessons left: ask the user"
        else:
            action = "run the listed lessons"
        return {"phase": state.phase, "action": action, "lessons": items, "blocked": blocked}

    @staticmethod
    def _get(state: State, lesson_id: str) -> LessonState:
        try:
            return state.lessons[lesson_id]
        except KeyError:
            raise StateError(f"unknown lesson {lesson_id}; register it first") from None
