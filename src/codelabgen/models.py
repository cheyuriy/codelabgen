"""Pydantic models for every data file codelabgen reads or writes.

These are the data contracts from PLAN.md §5. JSON Schemas exported from them
(`codelabgen schema export`) are what the agents follow.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LESSON_ID_RE = re.compile(r"^[1-9]\d*(\.[1-9]\d*){0,2}$")


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def lesson_sort_key(lesson_id: str) -> tuple[int, ...]:
    return tuple(int(part) for part in lesson_id.split("."))


def validate_lesson_id(value: str) -> str:
    if not LESSON_ID_RE.match(value):
        raise ValueError(f"invalid lesson id {value!r}: expected 1 to 3 levels like '1.2.3'")
    return value


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# --- config.yaml ---------------------------------------------------------------


class Runtime(Model):
    kind: str | None = Field(None, description="Ecosystem, e.g. 'python-uv', 'node', 'go'")
    per: Literal["module", "lesson"] = "module"
    services: list[str] = Field(default_factory=list, description="Docker Compose services")
    port_offset: int | None = Field(
        None, description="Added to every service's host port so courses never share a service"
    )


class External(Model):
    """An external service the course needs, with the user's answers from gate 2."""

    provider: str
    models: list[str] = Field(default_factory=list)
    env_vars: list[str] = Field(default_factory=list)


class Budgets(Model):
    fix_attempts: int = Field(5, ge=1, description="Verify-fix attempts before a lesson is blocked")
    review_rounds: int = Field(2, ge=0)
    parallel_modules: int = Field(2, ge=1)
    parallel_agents: int = Field(4, ge=1, description="Most agents running at once")
    sources_per_type: int = Field(8, ge=1, description="Most sources a hunter proposes per type")


class Config(Model):
    topic: str
    version: str | None = Field(None, description="Pinned version of the technology")
    language: str = Field("en", description="Course language (ISO 639-1)")
    target: str = Field(description="Absolute path of the course directory")
    user_sources: list[str] = Field(default_factory=list)
    runtime: Runtime = Field(default_factory=Runtime)
    external: list[External] = Field(default_factory=list)
    budgets: Budgets = Field(default_factory=Budgets)


# --- state.json ----------------------------------------------------------------


class Phase(StrEnum):
    INIT = "init"
    RECON = "recon"
    SOURCES = "sources"
    GATE_SOURCES = "gate_sources"
    TOPICS = "topics"
    CURRICULUM = "curriculum"
    GATE_PLAN = "gate_plan"
    SCAFFOLD = "scaffold"
    LESSONS = "lessons"
    ASSEMBLY = "assembly"
    DONE = "done"


PHASE_ORDER: list[Phase] = list(Phase)
GATES = {Phase.GATE_SOURCES, Phase.GATE_PLAN}


class Stage(StrEnum):
    """The last completed stage of a lesson (PLAN.md §2)."""

    PENDING = "pending"
    SPEC = "spec"
    CODE = "code"
    VERIFIED = "verified"
    READALONG = "readalong"
    NOTES = "notes"
    REVIEWED = "reviewed"
    DONE = "done"
    BLOCKED = "blocked"
    STALE = "stale"


STAGE_ORDER: list[Stage] = [
    Stage.PENDING,
    Stage.SPEC,
    Stage.CODE,
    Stage.VERIFIED,
    Stage.READALONG,
    Stage.NOTES,
    Stage.REVIEWED,
    Stage.DONE,
]


class LessonState(Model):
    stage: Stage = Stage.PENDING
    fix_attempts: int = 0
    review_rounds: int = 0
    blocked_from: Stage | None = Field(None, description="Stage to return to when unblocked")
    note: str | None = None
    updated: datetime = Field(default_factory=now)


class TaskState(Model):
    """One unit of agent work (a hunter run, an extraction batch, a lesson stage).

    A task still `running` when a session resumes was interrupted: its worker may
    have left partial artifacts behind.
    """

    status: Literal["running", "done", "failed"] = "running"
    phase: Phase
    lesson: str | None = None
    attempts: int = 1
    note: str | None = None
    started: datetime = Field(default_factory=now)
    finished: datetime | None = None


ExtensionStage = Literal["gaps", "research", "digests", "delta", "gate", "lessons", "done"]
EXTENSION_STAGES: list[str] = ["gaps", "research", "digests", "delta", "gate", "lessons", "done"]


class ExtensionState(Model):
    """One extension of a finished course: deepen a topic or add a new one."""

    id: int
    request: str
    stage: ExtensionStage = "gaps"
    allow_renumber: bool = False
    started: datetime = Field(default_factory=now)
    finished: datetime | None = None


class State(Model):
    schema_version: int = 1
    phase: Phase = Phase.INIT
    approved_gates: list[Phase] = Field(default_factory=list)
    lessons: dict[str, LessonState] = Field(default_factory=dict)
    tasks: dict[str, TaskState] = Field(default_factory=dict)
    extensions: list[ExtensionState] = Field(default_factory=list)
    updated: datetime = Field(default_factory=now)

    @property
    def extension(self) -> ExtensionState | None:
        """The extension in progress, if any."""
        if self.extensions and self.extensions[-1].stage != "done":
            return self.extensions[-1]
        return None

    @field_validator("lessons")
    @classmethod
    def _check_ids(cls, value: dict[str, LessonState]) -> dict[str, LessonState]:
        for lesson_id in value:
            validate_lesson_id(lesson_id)
        return value


class Event(Model):
    ts: datetime = Field(default_factory=now)
    kind: str
    lesson: str | None = None
    data: dict = Field(default_factory=dict)


# --- research ------------------------------------------------------------------

SourceType = Literal[
    "official-docs",
    "official-blog",
    "release-notes",
    "package-internals",
    "article",
    "github-repo",
    "qa",
    "paper-spec",
    "talk-workshop",
    "university",
    "book-course",
]
SourceRole = Literal["structure", "code-truth", "concepts", "pitfalls"]


class Source(Model):
    """One row of sources.jsonl."""

    id: str = Field("", description="Assigned by `codelabgen sources add` when empty")
    url: str
    type: SourceType
    roles: list[SourceRole] = Field(min_length=1)
    title: str
    language: str | None = Field(None, description="Language of the source (ISO 639-1)")
    version: str | None = Field(None, description="Technology version the source targets")
    date: str | None = Field(None, description="Publication or last-update date, YYYY-MM-DD")
    score: float = Field(ge=0, le=1, description="See the source-evaluation skill")
    reason: str = Field(description="Why this source is useful, one sentence")
    status: Literal["proposed", "kept", "dropped", "user"] = "proposed"


class Topic(Model):
    """One row of topics/<source>.jsonl."""

    name: str
    summary: str
    prerequisites: list[str] = Field(default_factory=list)
    difficulty: int = Field(ge=1, le=5)
    apis: list[str] = Field(default_factory=list)
    source_id: str
    evidence_url: str


# --- curriculum.yaml -------------------------------------------------------------


class EnvVar(Model):
    name: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    description: str
    where_to_get: str | None = None
    scope: Literal["course", "lesson"] = "course"
    secret: bool = False
    default: str | None = Field(
        None, description="Value written to .env.example; never for secrets"
    )
    lessons: list[str] = Field(
        default_factory=list, description="Lessons that need it; empty = every lesson"
    )

    @model_validator(mode="after")
    def _no_secret_default(self) -> EnvVar:
        if self.secret and self.default:
            raise ValueError(f"{self.name}: secrets must not have a default value")
        return self


class ExampleRef(Model):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    mode: Literal["new", "extend"]
    from_lesson: str | None = Field(None, alias="from")


class CurriculumNode(Model):
    id: str
    title: str
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    summary: str
    objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    example: ExampleRef | None = None
    services: list[str] = Field(
        default_factory=list, description="Compose services the lesson uses"
    )
    sources: list[str] = Field(default_factory=list)
    children: list[CurriculumNode] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        return validate_lesson_id(value)


class Curriculum(Model):
    title: str
    description: str
    modules: list[CurriculumNode]
    env: list[EnvVar] = Field(default_factory=list)


# --- lessons/<id>/spec.yaml -------------------------------------------------------


class Recording(Model):
    name: str
    cmd: str
    input_script: str | None = None
    max_seconds: int = Field(60, ge=1, le=600)


class LessonSpec(Model):
    id: str
    title: str
    scenario: str = Field(description="What the example does, in a few sentences")
    files: list[str] = Field(description="Files the lesson creates, relative to the lesson dir")
    delta_from: str | None = Field(None, description="Lesson whose code this one extends")
    delta: list[str] = Field(default_factory=list, description="Changes relative to delta_from")
    run_cmd: str = Field(description="Live run, executed in the lesson dir via `uv run`")
    run_timeout_s: int = Field(300, ge=1, le=3600)
    services: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    experiments: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    recordings: list[Recording] = Field(default_factory=list)
    env: list[EnvVar] = Field(default_factory=list)


# --- runs/<id>/<ts>/result.json ----------------------------------------------------


class StepResult(Model):
    name: Literal[
        "env",
        "services",
        "sync",
        "lint",
        "format",
        "offline-tests",
        "live-run",
        "snippets",
        "record",
        "diagrams",
    ]
    exit_code: int
    duration_s: float
    log: str = Field(description="Path to the log file, relative to the run directory")


class RunResult(Model):
    lesson: str
    started: datetime
    run_dir: str
    steps: list[StepResult]
    passed: bool
    failed_step: str | None = None


# --- glossary.yaml ---------------------------------------------------------------


class GlossaryEntry(Model):
    term: str
    aliases: list[str] = Field(default_factory=list)
    definition: str
    first_lesson: str | None = None


SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "config": Config,
    "state": State,
    "event": Event,
    "source": Source,
    "topic": Topic,
    "curriculum": Curriculum,
    "lesson-spec": LessonSpec,
    "run-result": RunResult,
    "glossary-entry": GlossaryEntry,
}
