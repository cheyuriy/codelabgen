"""The `codelabgen` command line. Agents call this instead of editing state by hand."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from codelabgen import curriculum as cur
from codelabgen import env as envmod
from codelabgen import snippets
from codelabgen.course import Course, CourseNotFound
from codelabgen.curriculum import CurriculumError
from codelabgen.doctor import check_tools
from codelabgen.init import InitError, init_course, plugin_root
from codelabgen.models import SCHEMA_MODELS, Phase, Stage
from codelabgen.scaffold import ScaffoldError, scaffold_course, scaffold_lesson
from codelabgen.state import NEXT_ACTION, PHASE_ACTION, StateError, StateStore
from codelabgen.verify import summary, verify

app = typer.Typer(
    no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False, help=__doc__
)
state_app = typer.Typer(no_args_is_help=True, help="Read and change the course state.")
schema_app = typer.Typer(no_args_is_help=True, help="JSON Schemas of the data files.")
app.add_typer(state_app, name="state")
app.add_typer(schema_app, name="schema")
curriculum_app = typer.Typer(no_args_is_help=True, help="Validate and inspect the curriculum.")
scaffold_app = typer.Typer(no_args_is_help=True, help="Create course and lesson directories.")
snippets_app = typer.Typer(no_args_is_help=True, help="Copy code regions into lesson Markdown.")
check_app = typer.Typer(no_args_is_help=True, help="Consistency checks.")
env_app = typer.Typer(no_args_is_help=True, help="Course and lesson environment variables.")
app.add_typer(curriculum_app, name="curriculum")
app.add_typer(scaffold_app, name="scaffold")
app.add_typer(snippets_app, name="snippets")
app.add_typer(check_app, name="check")
app.add_typer(env_app, name="env")

CourseOpt = Annotated[
    Path | None,
    typer.Option("--course", "-C", help="Course directory (default: $CODELABGEN_COURSE or cwd)"),
]


def fail(message: str, code: int = 2) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code)


def emit(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def store_for(course: Path | None) -> StateStore:
    return StateStore(Course.find(course))


# --- init / doctor -------------------------------------------------------------------


@app.command()
def init(
    target: Annotated[Path, typer.Argument(help="Course directory to create (outside the plugin)")],
    topic: Annotated[str, typer.Option(help="Technology the course is about")],
    lang: Annotated[str, typer.Option(help="Course language, ISO 639-1")] = "en",
    version: Annotated[str | None, typer.Option(help="Pinned technology version")] = None,
    source: Annotated[list[str] | None, typer.Option(help="User-provided source URL")] = None,
    force: Annotated[bool, typer.Option(help="Allow a non-empty target directory")] = False,
) -> None:
    """Create a course directory with config, state and event log."""
    course = init_course(target, topic, lang, version, source, force)
    typer.echo(f"initialized course '{topic}' in {course.root}")


@app.command()
def doctor(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Check external tools and report which features a missing tool disables."""
    results = check_tools()
    if as_json:
        emit(
            [
                {
                    "tool": r.tool.command,
                    "found": bool(r.path),
                    "usable": r.usable,
                    "required": r.tool.required,
                    "version": r.version,
                    "problem": r.problem,
                    "feature": r.tool.feature,
                }
                for r in results
            ]
        )
    else:
        for r in results:
            if r.usable:
                mark, detail = "ok", r.version
            elif r.path:
                mark, detail = "not usable", f"{r.problem} — disables: {r.tool.feature}"
            else:
                mark = "MISSING (required)" if r.tool.required else "missing"
                detail = f"disables: {r.tool.feature}"
            typer.echo(f"{r.tool.command:<10} {mark:<18} {detail}")
    if any(r.tool.required and not r.usable for r in results):
        raise typer.Exit(1)


# --- state ------------------------------------------------------------------------


@state_app.command("show")
def state_show(course: CourseOpt = None, as_json: Annotated[bool, typer.Option("--json")] = False):
    """Show the phase and every lesson's stage."""
    store = store_for(course)
    state = store.load()
    if as_json:
        emit(state.model_dump(mode="json"))
        return
    config = store.course.load_config()
    typer.echo(f"course:  {config.topic} ({config.language}) at {store.course.root}")
    typer.echo(f"phase:   {state.phase} — {PHASE_ACTION.get(state.phase, '')}")
    if not state.lessons:
        typer.echo("lessons: none registered yet")
        return
    counts: dict[str, int] = {}
    for lesson in state.lessons.values():
        counts[lesson.stage] = counts.get(lesson.stage, 0) + 1
    typer.echo("lessons: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    for lesson_id, lesson in state.lessons.items():
        extra = []
        if lesson.fix_attempts:
            extra.append(f"fixes {lesson.fix_attempts}")
        if lesson.review_rounds:
            extra.append(f"reviews {lesson.review_rounds}")
        if lesson.note:
            extra.append(lesson.note)
        typer.echo(f"  {lesson_id:<8} {lesson.stage:<10} {' · '.join(extra)}")


@state_app.command("next")
def state_next(course: CourseOpt = None):
    """Print (JSON) the next work items for the orchestrator."""
    emit(store_for(course).next_work())


@state_app.command("phase")
def state_phase(
    phase: Phase,
    course: CourseOpt = None,
    approved: Annotated[bool, typer.Option(help="The user approved the current gate")] = False,
):
    """Advance the course to the next phase."""
    state = store_for(course).advance_phase(phase, approved)
    typer.echo(f"phase: {state.phase}")


@state_app.command("register")
def state_register(
    ids: Annotated[list[str], typer.Argument(help="Lesson ids")], course: CourseOpt = None
):
    """Register lessons (new ones start at 'pending')."""
    state = store_for(course).register(ids)
    typer.echo(f"{len(state.lessons)} lessons registered")


@state_app.command("set")
def state_set(
    lesson: str,
    stage: Stage,
    course: CourseOpt = None,
    note: Annotated[str | None, typer.Option(help="Short reason, kept in state and log")] = None,
):
    """Move a lesson one stage forward, or back to an earlier stage for rework."""
    state = store_for(course).set_stage(lesson, stage, note)
    typer.echo(f"{lesson}: {state.lessons[lesson].stage}")


@state_app.command("fail")
def state_fail(
    lesson: str, course: CourseOpt = None, note: Annotated[str | None, typer.Option()] = None
):
    """Record a failed verify; blocks the lesson when the fix budget is used up."""
    result = store_for(course).record_failure(lesson, note)
    emit({"lesson": lesson, "stage": result.stage, "fix_attempts": result.fix_attempts})


@state_app.command("block")
def state_block(lesson: str, reason: Annotated[str, typer.Option()], course: CourseOpt = None):
    """Block a lesson until the user decides."""
    store_for(course).block(lesson, reason)
    typer.echo(f"{lesson}: blocked")


@state_app.command("unblock")
def state_unblock(lesson: str, course: CourseOpt = None):
    """Return a blocked lesson to the stage it was blocked at."""
    state = store_for(course).unblock(lesson)
    typer.echo(f"{lesson}: {state.lessons[lesson].stage}")


@state_app.command("stale")
def state_stale(lesson: str, reason: Annotated[str, typer.Option()], course: CourseOpt = None):
    """Mark a done lesson as stale because something upstream changed."""
    store_for(course).mark_stale(lesson, reason)
    typer.echo(f"{lesson}: stale")


@state_app.command("log")
def state_log(
    kind: str,
    course: CourseOpt = None,
    lesson: Annotated[str | None, typer.Option()] = None,
    data: Annotated[list[str] | None, typer.Option(help="key=value, repeatable")] = None,
):
    """Append an event to events.jsonl (for agents and hooks)."""
    pairs = dict(item.split("=", 1) for item in (data or []) if "=" in item)
    store_for(course).log(kind, lesson, **pairs)


@state_app.command("stages")
def state_stages():
    """Print the lesson stages and who moves a lesson out of each."""
    emit({stage: {"next": nxt, "by": by} for stage, (nxt, by) in NEXT_ACTION.items()})


# --- curriculum ---------------------------------------------------------------------


@curriculum_app.command("validate")
def curriculum_validate(course: CourseOpt = None):
    """Check curriculum.yaml: schema, numbering, depth, prerequisites, example storyline."""
    curriculum = cur.load(Course.find(course))
    count = len(cur.lessons(curriculum))
    typer.echo(f"ok: {len(curriculum.modules)} modules, {count} lessons")


@curriculum_app.command("lessons")
def curriculum_lessons(course: CourseOpt = None):
    """Print (JSON) every lesson with its directory, package and example."""
    curriculum = cur.load(Course.find(course))
    emit(
        [
            {
                "id": lesson.id,
                "title": lesson.node.title,
                "dir": lesson.rel_dir.as_posix(),
                "package": lesson.package,
                "project": lesson.project,
                "example": lesson.node.example.model_dump(by_alias=True)
                if lesson.node.example
                else None,
                "services": lesson.node.services,
            }
            for lesson in cur.lessons(curriculum)
        ]
    )


# --- scaffold -----------------------------------------------------------------------


def print_scaffold(report) -> None:
    for path in report.created:
        typer.echo(f"created  {path}")
    for path in report.written:
        typer.echo(f"updated  {path}")
    for lesson, source in report.copied_from.items():
        typer.echo(f"copied   code of {source} into {lesson}")
    if not (report.created or report.written or report.copied_from):
        typer.echo("nothing to do")


@scaffold_app.command("course")
def scaffold_course_cmd(course: CourseOpt = None):
    """Generate course files, module workspaces and lesson directories; register lessons."""
    print_scaffold(scaffold_course(Course.find(course)))


@scaffold_app.command("lesson")
def scaffold_lesson_cmd(lesson: str, course: CourseOpt = None):
    """Complete one lesson directory; an extending lesson gets the earlier lesson's code."""
    print_scaffold(scaffold_lesson(Course.find(course), lesson))


# --- verify -------------------------------------------------------------------------


@app.command("verify")
def verify_cmd(
    lesson: str,
    course: CourseOpt = None,
    live: Annotated[bool, typer.Option(help="Run the spec's run_cmd after the tests")] = True,
    update_state: Annotated[
        bool, typer.Option(help="On pass set 'verified'; on failure count a fix attempt")
    ] = False,
):
    """Install, lint, test and run a lesson; print a JSON summary. Exit 1 when it fails."""
    found = Course.find(course)
    result = verify(found, lesson, live=live)
    data = summary(found, result)
    if update_state:
        store = StateStore(found)
        if result.passed:
            store.set_stage(lesson, Stage.VERIFIED, note=None)
            data["stage"] = Stage.VERIFIED
        else:
            state = store.record_failure(lesson, note=f"verify failed at {result.failed_step}")
            data["stage"], data["fix_attempts"] = state.stage, state.fix_attempts
    emit(data)
    if not result.passed:
        raise typer.Exit(1)


# --- snippets / check -------------------------------------------------------------


def lesson_dirs(found: Course, lesson: str | None) -> list[tuple[str, Path]]:
    curriculum = cur.load(found)
    chosen = [cur.find_lesson(curriculum, lesson)] if lesson else cur.lessons(curriculum)
    return [(item.id, found.root / item.rel_dir) for item in chosen]


@snippets_app.command("sync")
def snippets_sync(lesson: Annotated[str | None, typer.Argument()] = None, course: CourseOpt = None):
    """Refresh code snippets in the docs of one lesson (or all)."""
    found = Course.find(course)
    problems = []
    for _, path in lesson_dirs(found, lesson):
        changed, found_problems = snippets.sync(path)
        problems += found_problems
        for item in changed:
            typer.echo(f"updated {item.relative_to(found.root)}")
    for problem in problems:
        typer.echo(f"problem: {problem}", err=True)
    if problems:
        raise typer.Exit(1)


@check_app.command("snippets")
def check_snippets(
    lesson: Annotated[str | None, typer.Argument()] = None, course: CourseOpt = None
):
    """Fail if a snippet points at a missing region or its copy is out of date."""
    found = Course.find(course)
    issues = []
    for _, path in lesson_dirs(found, lesson):
        stale, problems = snippets.sync(path, write=False)
        issues += [
            f"{p.relative_to(found.root)}: out of date, run codelabgen snippets sync" for p in stale
        ]
        issues += [str(p) for p in problems]
    for issue in issues:
        typer.echo(issue)
    if issues:
        raise typer.Exit(1)
    typer.echo("ok")


# --- env --------------------------------------------------------------------------


@env_app.command("check")
def env_check(lesson: Annotated[str | None, typer.Argument()] = None, course: CourseOpt = None):
    """Report required variables that are missing or empty, per lesson."""
    found = Course.find(course)
    curriculum = cur.load(found)
    chosen = [cur.find_lesson(curriculum, lesson)] if lesson else cur.lessons(curriculum)
    missing = False
    for item in chosen:
        report = envmod.check(found, curriculum, item)
        if report.missing:
            missing = True
            typer.echo(f"{item.id}: missing {', '.join(report.missing)}")
    if missing:
        raise typer.Exit(1)
    typer.echo("ok")


@env_app.command("list")
def env_list(course: CourseOpt = None):
    """Print (JSON) every lesson's required variables."""
    found = Course.find(course)
    curriculum = cur.load(found)
    emit(
        {
            item.id: [
                {"name": v.name, "scope": v.scope, "secret": v.secret}
                for v in envmod.required_vars(curriculum, item.id, envmod.load_spec(found, item.id))
            ]
            for item in cur.lessons(curriculum)
        }
    )


# --- schema -----------------------------------------------------------------------


@schema_app.command("export")
def schema_export(
    out: Annotated[
        Path | None, typer.Argument(help="Output dir (default: <plugin>/schemas)")
    ] = None,
):
    """Write a JSON Schema for every data file."""
    if out is None:
        root = plugin_root()
        if root is None:
            fail("not running from the plugin checkout; pass an output directory")
        out = root / "schemas"
    out.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMA_MODELS.items():
        schema = model.model_json_schema(by_alias=True)
        (out / f"{name}.schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    typer.echo(f"wrote {len(SCHEMA_MODELS)} schemas to {out}")


@schema_app.command("show")
def schema_show(name: str):
    """Print the JSON Schema of one data file."""
    model = SCHEMA_MODELS.get(name)
    if model is None:
        fail(f"unknown schema {name!r}; known: {', '.join(SCHEMA_MODELS)}")
    emit(model.model_json_schema(by_alias=True))


def main() -> None:
    """Entry point: expected errors become a one-line message and exit code 2."""
    try:
        app()
    except (StateError, InitError, CourseNotFound, CurriculumError, ScaffoldError) as exc:
        typer.echo(f"error: {exc}", err=True)
        sys.exit(2)
    except ValidationError as exc:
        typer.echo(f"error: invalid data: {exc}", err=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
