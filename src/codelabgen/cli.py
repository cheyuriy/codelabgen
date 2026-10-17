"""The `codelabgen` command line. Agents call this instead of editing state by hand."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from codelabgen import checks, diagrams, glossary, report, research, resume, snippets, toc
from codelabgen import curriculum as cur
from codelabgen import env as envmod
from codelabgen import fetch as fetchmod
from codelabgen import github as gh
from codelabgen import record as recordings
from codelabgen import site as sitemod
from codelabgen import sources as srcmod
from codelabgen import topics as topicsmod
from codelabgen.course import Course, CourseNotFound, atomic_write
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
glossary_app = typer.Typer(no_args_is_help=True, help="The course glossary.")
diagrams_app = typer.Typer(no_args_is_help=True, help="D2 and Graphviz diagrams.")
site_app = typer.Typer(no_args_is_help=True, help="The course website (MkDocs).")
app.add_typer(glossary_app, name="glossary")
app.add_typer(diagrams_app, name="diagrams")
app.add_typer(site_app, name="site")
sources_app = typer.Typer(no_args_is_help=True, help="The source registry and review sheet.")
github_app = typer.Typer(
    no_args_is_help=True, help="GitHub research (gh, GITHUB_TOKEN or anonymous)."
)
repo_app = typer.Typer(no_args_is_help=True, help="Clones of the technology's repositories.")
config_app = typer.Typer(no_args_is_help=True, help="Course settings.")
topics_app = typer.Typer(no_args_is_help=True, help="Topics extracted from the sources.")
external_app = typer.Typer(no_args_is_help=True, help="External services the user chose.")
app.add_typer(topics_app, name="topics")
config_app.add_typer(external_app, name="external")
app.add_typer(sources_app, name="sources")
app.add_typer(github_app, name="github")
app.add_typer(repo_app, name="repo")
app.add_typer(config_app, name="config")
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
    if not as_json:
        typer.echo(f"{'github':<10} {gh.access().mode:<18} {gh.access().detail}")
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
    """Print (JSON) what is left to do in the current phase, including interrupted tasks."""
    emit(resume.next_actions(Course.find(course)))


task_app = typer.Typer(no_args_is_help=True, help="Units of agent work, for resuming.")
state_app.add_typer(task_app, name="task")


@task_app.command("start")
def task_start(
    key: str,
    course: CourseOpt = None,
    lesson: Annotated[str | None, typer.Option()] = None,
    note: Annotated[str | None, typer.Option()] = None,
):
    """Record that a worker starts (say, lesson:1.2:code). Prints the attempt number."""
    task = store_for(course).start_task(key, lesson, note)
    emit(
        {
            "task": key,
            "attempt": task.attempts,
            "interrupted_before": task.attempts > 1 and "interrupted" in (task.note or ""),
        }
    )


@task_app.command("done")
def task_done(
    key: str, course: CourseOpt = None, note: Annotated[str | None, typer.Option()] = None
):
    """Record that a worker finished successfully."""
    store_for(course).finish_task(key, ok=True, note=note)
    typer.echo(f"{key}: done")


@task_app.command("fail")
def task_fail(
    key: str, course: CourseOpt = None, note: Annotated[str | None, typer.Option()] = None
):
    """Record that a worker failed."""
    store_for(course).finish_task(key, ok=False, note=note)
    typer.echo(f"{key}: failed")


@task_app.command("reset")
def task_reset(key: str, course: CourseOpt = None):
    """Forget a task, so it runs again (for example to redo a source hunter)."""
    store_for(course).reset_task(key)
    typer.echo(f"{key}: reset")


@task_app.command("list")
def task_list(
    course: CourseOpt = None,
    open_only: Annotated[bool, typer.Option("--open", help="Only running or failed")] = False,
):
    """Print (JSON) the tasks, optionally only unfinished ones."""
    tasks = store_for(course).load().tasks
    emit(
        {
            k: t.model_dump(mode="json", exclude_none=True)
            for k, t in tasks.items()
            if not open_only or t.status != "done"
        }
    )


@app.command("report")
def report_cmd(course: CourseOpt = None):
    """Write .codelabgen/report.md: phases, sources, lessons, unfinished tasks."""
    found = Course.find(course)
    path = report.build(found)
    typer.echo(path.read_text())


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


@curriculum_app.command("number")
def curriculum_number(course: CourseOpt = None):
    """Assign ids by position and rewrite references (before scaffolding only)."""
    found = Course.find(course)
    if StateStore(found).load().lessons:
        fail("lessons are registered already; renumbering now would break their directories")
    mapping = cur.number(found)
    for old, new in mapping.items():
        typer.echo(f"{old} -> {new}")
    cur.load(found)
    typer.echo("ok")


@curriculum_app.command("render")
def curriculum_render(course: CourseOpt = None):
    """Write .codelabgen/plan.md for the user's review."""
    found = Course.find(course)
    typer.echo(cur.render_plan(found).relative_to(found.root))


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


def run_checks(found: Course, names: list[str]) -> None:
    issues = []
    for name in names:
        issues += [f"[{name}] {issue}" for issue in checks.CHECKS[name](found)]
    for issue in issues:
        typer.echo(issue)
    if issues:
        typer.echo(f"{len(issues)} problem(s)", err=True)
        raise typer.Exit(1)
    typer.echo("ok")


@check_app.command("snippets")
def check_snippets(
    lesson: Annotated[str | None, typer.Argument()] = None, course: CourseOpt = None
):
    """Fail if a snippet points at a missing region or its copy is out of date."""
    found = Course.find(course)
    if lesson is None:
        run_checks(found, ["snippets"])
        return
    stale, problems = snippets.sync(
        found.root / cur.find_lesson(cur.load(found), lesson).rel_dir, write=False
    )
    issues = [
        f"{p.relative_to(found.root)}: out of date, run codelabgen snippets sync" for p in stale
    ]
    issues += [str(p) for p in problems]
    for issue in issues:
        typer.echo(issue)
    if issues:
        raise typer.Exit(1)
    typer.echo("ok")


def _add_check(name: str) -> None:
    def command(course: CourseOpt = None):
        run_checks(Course.find(course), [name])

    command.__doc__ = checks.CHECKS[name].__doc__ or f"Run the {name} check."
    check_app.command(name)(command)


for _name in ("structure", "links", "render", "math", "mermaid"):
    _add_check(_name)


@check_app.command("all")
def check_all(course: CourseOpt = None):
    """Run every check: structure, snippets, links, render, math, mermaid."""
    run_checks(Course.find(course), list(checks.CHECKS))


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


# --- toc / site / glossary / diagrams / record / commit ---------------------------


@app.command("toc")
def toc_cmd(course: CourseOpt = None):
    """Generate READMEs, mkdocs.yml (nav), run.sh, site assets and the glossary page."""
    found = Course.find(course)
    written = toc.generate(found)
    for path in written:
        typer.echo(f"wrote {path.relative_to(found.root)}")
    if not written:
        typer.echo("nothing changed")


@site_app.command("build")
def site_build(course: CourseOpt = None):
    """Build the site into site/ (strict: warnings fail the build)."""
    found = Course.find(course)
    proc = sitemod.run(found, "build", [])
    output = (proc.stdout or "") + (proc.stderr or "")
    lines = [
        ln for ln in output.splitlines() if "WARNING" in ln or "ERROR" in ln or "Aborted" in ln
    ]
    typer.echo("\n".join(lines) if lines else output.strip().splitlines()[-1] if output else "")
    if proc.returncode != 0:
        raise typer.Exit(1)
    typer.echo(f"site built in {found.root / 'site'}")


@site_app.command("serve")
def site_serve(
    course: CourseOpt = None,
    addr: Annotated[str, typer.Option(help="host:port")] = "127.0.0.1:8000",
):
    """Serve the site with live reload."""
    proc = sitemod.run(Course.find(course), "serve", ["--dev-addr", addr])
    raise typer.Exit(proc.returncode)


@glossary_app.command("add")
def glossary_add(
    term: str,
    definition: Annotated[str, typer.Option(help="One or two sentences, course language")],
    course: CourseOpt = None,
    alias: Annotated[list[str] | None, typer.Option(help="Other forms, repeatable")] = None,
    lesson: Annotated[str | None, typer.Option(help="Lesson that introduces the term")] = None,
):
    """Add a term (or update its definition) and rebuild GLOSSARY.md."""
    found = Course.find(course)
    entry, created = glossary.add(found, term, definition, alias, lesson)
    glossary.build(found)
    typer.echo(f"{'added' if created else 'updated'} {entry.term} (#{glossary.anchor(entry.term)})")


@glossary_app.command("build")
def glossary_build(course: CourseOpt = None):
    """Rebuild GLOSSARY.md and the site's tooltip file."""
    found = Course.find(course)
    for path in glossary.build(found):
        typer.echo(f"wrote {path.relative_to(found.root)}")


@glossary_app.command("link")
def glossary_link(
    term: str,
    from_file: Annotated[Path, typer.Option("--from", help="The Markdown file the link goes in")],
    course: CourseOpt = None,
):
    """Print the relative link target for a term, e.g. ../../GLOSSARY.md#граф-состояний."""
    found = Course.find(course)
    try:
        typer.echo(glossary.link(found, term, from_file))
    except KeyError as exc:
        fail(str(exc.args[0]))


@glossary_app.command("list")
def glossary_list(course: CourseOpt = None):
    """Print (JSON) all glossary entries."""
    emit([e.model_dump(exclude_none=True) for e in glossary.load(Course.find(course))])


@diagrams_app.command("render")
def diagrams_render(
    lesson: Annotated[str | None, typer.Argument()] = None,
    course: CourseOpt = None,
    force: Annotated[bool, typer.Option(help="Re-render even if the SVG is newer")] = False,
):
    """Render D2 / Graphviz sources in docs/diagrams/ to SVG."""
    found = Course.find(course)
    problems = []
    for _, path in lesson_dirs(found, lesson):
        report = diagrams.render(path, force=force)
        problems += report.problems
        for svg in report.rendered:
            typer.echo(f"rendered {svg.relative_to(found.root)}")
    for problem in problems:
        typer.echo(f"problem: {problem}", err=True)
    if problems:
        raise typer.Exit(1)


@app.command("record")
def record_cmd(lesson: str, course: CourseOpt = None):
    """Record the lesson's terminal scenarios (asciinema) and convert them to GIF (agg)."""
    found = Course.find(course)
    report = recordings.record(found, lesson)
    if report.skipped:
        typer.echo(f"skipped: {report.skipped}")
    for path in report.recorded:
        typer.echo(f"recorded {path.relative_to(found.root)}")
    for problem in report.problems:
        typer.echo(f"problem: {problem}", err=True)
    if report.problems:
        raise typer.Exit(1)


@app.command("commit")
def commit_cmd(
    message: Annotated[str, typer.Option("--message", "-m")],
    course: CourseOpt = None,
):
    """Commit everything in the course repository (after a build or an extension)."""
    found = Course.find(course)
    git = ["git", "-C", str(found.root)]
    subprocess.run([*git, "add", "-A"], check=True)
    staged = subprocess.run([*git, "diff", "--cached", "--quiet"])
    if staged.returncode == 0:
        typer.echo("nothing to commit")
        return
    subprocess.run([*git, "commit", "-q", "-m", message], check=True)
    head = subprocess.run([*git, "log", "-1", "--oneline"], capture_output=True, text=True)
    typer.echo(head.stdout.strip())


# --- research: fetch / github / repo / pkg-info / transcript ------------------------------


@app.command("fetch")
def fetch_cmd(
    urls: Annotated[list[str], typer.Argument(help="One or more URLs")],
    course: CourseOpt = None,
    refresh: Annotated[bool, typer.Option(help="Fetch again even if cached")] = False,
):
    """Download pages (HTML, Markdown, PDF) into .codelabgen/cache as Markdown; print JSON."""
    found = Course.find(course)
    results = []
    for url in urls:
        try:
            page = fetchmod.fetch(found, url, refresh=refresh)
            results.append(
                {
                    "url": url,
                    "final_url": page.final_url,
                    "title": page.title,
                    "path": str(page.path.relative_to(found.root)),
                    "chars": page.chars,
                    "cached": page.cached,
                }
            )
        except fetchmod.FetchError as exc:
            results.append({"url": url, "error": str(exc)})
    emit(results)
    if all("error" in r for r in results):
        raise typer.Exit(1)


@app.command("llms-txt")
def llms_txt_cmd(site: str, course: CourseOpt = None):
    """Fetch llms.txt / llms-full.txt of a docs site when they exist; print JSON."""
    found = Course.find(course)
    pages = fetchmod.llms_txt(found, site)
    emit(
        [
            {"url": p.url, "path": str(p.path.relative_to(found.root)), "chars": p.chars}
            for p in pages
        ]
    )


@app.command("transcript")
def transcript_cmd(
    url: str,
    course: CourseOpt = None,
    langs: Annotated[str, typer.Option(help="Subtitle languages for yt-dlp")] = "en.*,ru.*",
):
    """Save a talk's subtitles as text in the cache (yt-dlp; via uvx when not installed)."""
    found = Course.find(course)
    path = research.transcript(found, url, langs)
    typer.echo(str(path.relative_to(found.root)))


@app.command("pkg-info")
def pkg_info_cmd(
    ecosystem: Annotated[str, typer.Argument(help="pypi, npm, crates or go")],
    name: str,
):
    """Latest version, release date and links from the package registry (JSON)."""
    emit(research.pkg_info(ecosystem, name))


@repo_app.command("clone")
def repo_clone(
    url: Annotated[str, typer.Argument(help="GitHub URL or owner/name")],
    course: CourseOpt = None,
    ref: Annotated[
        str | None, typer.Option(help="Tag or branch; default: the pinned version")
    ] = None,
    package: Annotated[
        str | None, typer.Option(help="Package name for monorepo tags like pkg==1.2.3")
    ] = None,
):
    """Shallow-clone a repo into .codelabgen/repos at the pinned version's tag (JSON)."""
    emit(research.clone(Course.find(course), url, ref, package))


@github_app.command("meta")
def github_meta(repos: list[str]):
    """Stars, last push, license, topics of repositories (JSON)."""
    emit([gh.repo_meta(research.repo_slug(r)) for r in repos])


@github_app.command("repos")
def github_repos(
    query: str,
    limit: Annotated[int, typer.Option()] = 20,
    sort: Annotated[str, typer.Option(help="stars, updated or best-match")] = "stars",
):
    """Search repositories with GitHub search syntax (JSON)."""
    emit(gh.search_repos(query, limit, None if sort == "best-match" else sort))


@github_app.command("code")
def github_code(query: str, limit: Annotated[int, typer.Option()] = 20):
    """Search code, e.g. '"langgraph" filename:pyproject.toml' (JSON; needs auth)."""
    emit(gh.search_code(query, limit))


@github_app.command("issues")
def github_issues(
    repo: str,
    course: CourseOpt = None,
    query: Annotated[str, typer.Option(help="Extra search terms")] = "",
    limit: Annotated[int, typer.Option()] = 20,
    discussions: Annotated[bool, typer.Option(help="Discussions instead of issues")] = False,
):
    """Save the most-reacted issues (or discussions) as Markdown in the cache; print the path."""
    found = Course.find(course)
    slug = research.repo_slug(repo)
    if discussions:
        items, kind = gh.top_discussions(slug, limit), "discussions"
    else:
        items, kind = gh.top_issues(slug, query, limit), "issues"
    name = f"{kind}-{slug.replace('/', '__')}" + (
        f"-{hashlib.sha1(query.encode()).hexdigest()[:6]}" if query else ""
    )
    path = fetchmod.cache_dir(found) / f"{name}.md"
    atomic_write(path, gh.issues_markdown(slug, items, kind))
    emit({"path": str(path.relative_to(found.root)), "count": len(items)})


# --- sources ----------------------------------------------------------------------------


@sources_app.command("add")
def sources_add(
    course: CourseOpt = None,
    json_text: Annotated[str | None, typer.Option("--json", help="Row(s) as JSON")] = None,
    file: Annotated[Path | None, typer.Option(help="JSON lines file")] = None,
):
    """Add or merge sources (validated, URLs normalized, duplicates merged)."""
    text = file.read_text() if file else (json_text or sys.stdin.read())
    report = srcmod.add(Course.find(course), srcmod.rows_from_text(text))
    emit({"added": report.added, "merged": report.merged})


@sources_app.command("list")
def sources_list(
    course: CourseOpt = None,
    status: Annotated[list[str] | None, typer.Option(help="Repeatable")] = None,
    type_: Annotated[str | None, typer.Option("--type")] = None,
    role: Annotated[str | None, typer.Option()] = None,
    brief: Annotated[bool, typer.Option(help="Only id, type, score, url")] = False,
):
    """Print sources as JSON lines, optionally filtered."""
    for s in srcmod.query(Course.find(course), status, type_, role):
        if brief:
            typer.echo(
                json.dumps(
                    {"id": s.id, "type": s.type, "score": s.score, "url": s.url}, ensure_ascii=False
                )
            )
        else:
            typer.echo(s.model_dump_json(exclude_none=True))


@sources_app.command("render")
def sources_render(course: CourseOpt = None):
    """Write the review sheet .codelabgen/sources.md."""
    found = Course.find(course)
    path = srcmod.render(found)
    counts: dict[str, int] = {}
    for s in srcmod.load(found):
        counts[s.type] = counts.get(s.type, 0) + 1
    emit({"path": str(path.relative_to(found.root)), "by_type": counts})


@sources_app.command("apply")
def sources_apply(course: CourseOpt = None):
    """Read the user's ticks and additions from sources.md into the registry."""
    emit(srcmod.apply(Course.find(course)))


# --- config -----------------------------------------------------------------------------

CONFIG_KEYS = {"version", "language", "topic", "runtime.kind", "runtime.per"}


@config_app.command("show")
def config_show(course: CourseOpt = None):
    """Print the course config (JSON)."""
    emit(Course.find(course).load_config().model_dump(mode="json"))


@config_app.command("set")
def config_set(key: str, value: str, course: CourseOpt = None):
    """Set version, language, topic, runtime.kind or runtime.per."""
    if key not in CONFIG_KEYS:
        fail(f"only {', '.join(sorted(CONFIG_KEYS))} can be set here")
    found = Course.find(course)
    config = found.load_config()
    target, _, name = key.rpartition(".")
    setattr(config.runtime if target == "runtime" else config, name, value)
    found.save_config(config.model_validate(config.model_dump()))
    StateStore(found).log("config", key=key, value=value)
    typer.echo(f"{key} = {value}")


@external_app.command("add")
def external_add(
    provider: str,
    course: CourseOpt = None,
    model: Annotated[list[str] | None, typer.Option(help="Model or plan, repeatable")] = None,
    env: Annotated[list[str] | None, typer.Option(help="Variable it needs, repeatable")] = None,
):
    """Record the user's choice of an external service (replaces the same provider)."""
    from codelabgen.models import External

    found = Course.find(course)
    config = found.load_config()
    config.external = [e for e in config.external if e.provider != provider]
    config.external.append(External(provider=provider, models=model or [], env_vars=env or []))
    found.save_config(config)
    StateStore(found).log("external", provider=provider, models=",".join(model or []))
    typer.echo(f"external: {provider}")


@external_app.command("clear")
def external_clear(course: CourseOpt = None):
    """Forget all recorded external services."""
    found = Course.find(course)
    config = found.load_config()
    config.external = []
    found.save_config(config)
    typer.echo("external: cleared")


# --- topics -----------------------------------------------------------------------------


@topics_app.command("add")
def topics_add(
    source: Annotated[str, typer.Option(help="Source id the topics come from")],
    course: CourseOpt = None,
    json_text: Annotated[str | None, typer.Option("--json", help="Topic rows as JSON")] = None,
    file: Annotated[Path | None, typer.Option(help="JSON lines file")] = None,
):
    """Set the topics of one source (replaces earlier ones for that source)."""
    text = file.read_text() if file else (json_text or sys.stdin.read())
    count = topicsmod.add(Course.find(course), source, srcmod.rows_from_text(text))
    typer.echo(f"{source}: {count} topics")


@topics_app.command("merge")
def topics_merge(course: CourseOpt = None):
    """Merge all topics into .codelabgen/topics/summary.md (exact-name merge)."""
    found = Course.find(course)
    items, path = topicsmod.merge(found)
    emit({"topics": len(items), "path": str(path.relative_to(found.root))})


# --- digests ----------------------------------------------------------------------------


@sources_app.command("digests")
def sources_digests(course: CourseOpt = None):
    """Kept sources whose digest is missing or incomplete (JSON lines)."""
    found = Course.find(course)
    pending = srcmod.pending_digests(found)
    for s in pending:
        typer.echo(
            json.dumps(
                {"id": s.id, "type": s.type, "problems": srcmod.digest_problems(found, s)},
                ensure_ascii=False,
            )
        )
    if not pending:
        typer.echo("all digests present")


@sources_app.command("batches")
def sources_batches(
    course: CourseOpt = None,
    size: Annotated[int, typer.Option(help="Sources per extractor")] = 5,
    all_sources: Annotated[
        bool, typer.Option("--all", help="Include sources with digests")
    ] = False,
):
    """Group the sources still needing digests for parallel topic extractors (JSON)."""
    emit(srcmod.batches(Course.find(course), size, only_pending=not all_sources))


@sources_app.command("index")
def sources_index(
    course: CourseOpt = None,
    role: Annotated[str | None, typer.Option(help="Print the digests of one role")] = None,
):
    """Rebuild .codelabgen/sources/index.md; with --role, print that role's digest paths."""
    found = Course.find(course)
    path = srcmod.build_index(found)
    if role:
        for s in srcmod.query(found, ["kept", "user"], role=role):
            digest = srcmod.digest_path(found, s.id)
            if digest.is_file():
                typer.echo(digest.relative_to(found.root))
        return
    typer.echo(path.relative_to(found.root))


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
    except (
        StateError,
        InitError,
        CourseNotFound,
        CurriculumError,
        ScaffoldError,
        fetchmod.FetchError,
        gh.GitHubError,
        research.ResearchError,
        srcmod.SourcesError,
        topicsmod.TopicsError,
    ) as exc:
        typer.echo(f"error: {exc}", err=True)
        sys.exit(2)
    except ValidationError as exc:
        typer.echo(f"error: invalid data: {exc}", err=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
