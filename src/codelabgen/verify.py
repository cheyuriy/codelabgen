"""`codelabgen verify <id>`: prove that a lesson installs, passes its checks and runs.

Steps, stopping at the first failure:
  env            required variables are set (course .env + lesson .env)
  sync           `uv sync --all-packages` in the module workspace
  lint, format   ruff check / ruff format --check in the lesson dir
  offline-tests  pytest in the lesson dir
  services       docker compose services the live run needs are up and healthy
  live-run       the spec's run_cmd, with its timeout
  record         terminal recordings listed in the spec (skipped without asciinema/agg)
  diagrams       D2 / Graphviz sources rendered to SVG
  snippets       code regions copied into the lesson's Markdown

Each step's output goes to `.codelabgen/runs/<id>/<timestamp>/<step>.log`, and
the outcome to `result.json` next to it.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from codelabgen import curriculum as cur
from codelabgen import diagrams, snippets
from codelabgen import env as envmod
from codelabgen import record as recordings
from codelabgen.course import Course, atomic_write, dump_json
from codelabgen.models import RunResult, StepResult, now
from codelabgen.scaffold import lesson_services

TAIL_LINES = 60


@dataclass
class Step:
    name: str
    argv: list[str] | None  # None = done in Python
    cwd: Path
    timeout: int


def run_dir_for(course: Course, lesson_id: str) -> Path:
    stamp = now().strftime("%Y%m%dT%H%M%SZ")
    path = course.meta / "runs" / lesson_id / stamp
    suffix = 1
    while path.exists():
        suffix += 1
        path = course.meta / "runs" / lesson_id / f"{stamp}-{suffix}"
    path.mkdir(parents=True)
    return path


def verify(course: Course, lesson_id: str, live: bool = True) -> RunResult:
    curriculum = cur.load(course)
    lesson = cur.find_lesson(curriculum, lesson_id)
    spec = envmod.load_spec(course, lesson_id)
    lesson_dir = course.root / lesson.rel_dir
    module_dir = course.root / lesson.module_rel_dir
    run_dir = run_dir_for(course, lesson_id)
    process_env = envmod.process_env(course, lesson)
    started = now()
    results: list[StepResult] = []

    def record(name: str, code: int, seconds: float, log: str) -> bool:
        (run_dir / f"{name}.log").write_text(log)
        results.append(
            StepResult(name=name, exit_code=code, duration_s=round(seconds, 2), log=f"{name}.log")
        )
        return code == 0

    def finish(passed: bool) -> RunResult:
        failed = None if passed else results[-1].name
        result = RunResult(
            lesson=lesson_id,
            started=started,
            run_dir=str(run_dir.relative_to(course.root)),
            steps=results,
            passed=passed,
            failed_step=failed,
        )
        atomic_write(run_dir / "result.json", dump_json(result))
        return result

    # env
    report = envmod.check(course, curriculum, lesson)
    lines = [f"required: {', '.join(v.name for v in report.required) or 'none'}"]
    if report.missing:
        lines.append(f"missing or empty: {', '.join(report.missing)}")
        lines.append("fill them in the course .env (or the lesson .env) and run verify again")
    if not record("env", 1 if report.missing else 0, 0, "\n".join(lines) + "\n"):
        return finish(False)

    if spec is None:
        record("live-run", 1, 0, f"no spec: .codelabgen/lessons/{lesson_id}/spec.yaml is missing\n")
        return finish(False)

    uv_run = ["uv", "run", "--package", lesson.project]
    steps = [
        Step("sync", ["uv", "sync", "--all-packages"], module_dir, 900),
        Step("lint", [*uv_run, "--frozen", "ruff", "check", "."], lesson_dir, 120),
        Step("format", [*uv_run, "--frozen", "ruff", "format", "--check", "."], lesson_dir, 120),
        Step("offline-tests", [*uv_run, "--frozen", "pytest", "-q", "tests"], lesson_dir, 600),
    ]
    if live:
        # Services are only for the live run: offline tests never need them.
        needed = lesson_services(curriculum, course)[lesson_id]
        if needed:
            steps.append(
                Step(
                    "services",
                    compose_argv(course, "up", "-d", "--wait", *needed),
                    course.root,
                    300,
                )
            )
        live_argv = [*uv_run, "--frozen", *shlex.split(spec.run_cmd)]
        steps.append(Step("live-run", live_argv, lesson_dir, spec.run_timeout_s))

    for step in steps:
        code, seconds, log = run_step(step, process_env)
        if step.name == "services":
            if code != 0:
                log += explain_port_conflict(log)
            else:
                problems = check_published(course, lesson_services(curriculum, course)[lesson_id])
                if problems:
                    code = 1
                    log += "\n--- port check ---\n" + "\n".join(problems) + "\n"
        if not record(step.name, code, seconds, log):
            return finish(False)

    if live:
        recorded = recordings.record(course, lesson_id)
        log = recorded.skipped and f"skipped: {recorded.skipped}\n" or ""
        log += "".join(f"recorded {p.relative_to(course.root)}\n" for p in recorded.recorded)
        log += "".join(f"problem: {p}\n" for p in recorded.problems)
        if not record("record", 1 if recorded.problems else 0, 0, log or "nothing recorded\n"):
            return finish(False)

    rendered = diagrams.render(lesson_dir)
    log = "".join(f"rendered {p.relative_to(course.root)}\n" for p in rendered.rendered)
    log += "".join(f"problem: {p}\n" for p in rendered.problems)
    if not record("diagrams", 1 if rendered.problems else 0, 0, log or "nothing to render\n"):
        return finish(False)

    changed, problems = snippets.sync(lesson_dir)
    log = "".join(f"updated {p.relative_to(course.root)}\n" for p in changed)
    log += "".join(f"problem: {p}\n" for p in problems)
    return finish(record("snippets", 1 if problems else 0, 0, log or "nothing to sync\n"))


def compose_argv(course: Course, *args: str) -> list[str]:
    return ["docker", "compose", "-f", str(course.root / "docker-compose.yml"), *args]


def check_published(course: Course, names: list[str]) -> list[str]:
    """Each service must really be published on its expected host port.

    A container can be healthy (its healthcheck runs inside it) without its port
    mapping, and then the lesson would silently reach whatever else listens there.
    """
    from codelabgen import services

    offset = course.load_config().runtime.port_offset or 0
    problems = []
    for service in services.resolve(names, course.meta):
        for host, container in services.published_ports(services.with_offset(service, offset)):
            proc = subprocess.run(
                compose_argv(course, "port", service.name, str(container)),
                cwd=course.root,
                capture_output=True,
                text=True,
            )
            published = proc.stdout.strip().rsplit(":", 1)[-1]
            if proc.returncode != 0 or published != str(host):
                problems.append(
                    f"{service.name}: container port {container} is not published on host port "
                    f"{host} (got {published or 'nothing'}). Recreate it: "
                    f"docker compose up -d --force-recreate {service.name}"
                )
    return problems


def explain_port_conflict(log: str) -> str:
    """Name the container holding a port that a service could not bind."""
    ports = sorted(
        set(re.findall(r"(?:Bind for [\d.:\[\]]*?:|port )(\d{2,5})\b.*?(?:allocated|in use)", log))
    )
    notes = []
    for port in ports:
        proc = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"publish={port}",
                "--format",
                '{{.Names}}\t{{.Label "com.docker.compose.project"}}',
            ],
            capture_output=True,
            text=True,
        )
        for line in proc.stdout.splitlines():
            name, _, project = line.partition("\t")
            stop = f"docker compose -p {project} stop" if project else f"docker stop {name}"
            notes.append(
                f"port {port} is used by container {name}"
                + (f" (compose project {project}, probably another course)" if project else "")
                + f". Stop it with: {stop}"
            )
    if not notes:
        return ""
    return "\n--- diagnosis ---\n" + "\n".join(notes) + "\n"


def run_step(step: Step, env: dict[str, str]) -> tuple[int, float, str]:
    header = f"$ {shlex.join(step.argv)}\n# cwd: {step.cwd}\n\n"
    start = time.monotonic()
    try:
        proc = subprocess.run(
            step.argv,
            cwd=step.cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=step.timeout,
        )
        output = proc.stdout + (("\n--- stderr ---\n" + proc.stderr) if proc.stderr else "")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        partial = (
            (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        )
        output = partial + f"\n--- timed out after {step.timeout}s ---\n"
        code = 124
    except FileNotFoundError as exc:
        output, code = f"command not found: {exc.filename}\n", 127
    return code, time.monotonic() - start, header + output


def summary(course: Course, result: RunResult) -> dict:
    """A compact view for agents: the failing step and the tail of its log."""
    data = {
        "lesson": result.lesson,
        "passed": result.passed,
        "run_dir": result.run_dir,
        "steps": {s.name: s.exit_code for s in result.steps},
    }
    if result.failed_step:
        log = (course.root / result.run_dir / f"{result.failed_step}.log").read_text()
        data["failed_step"] = result.failed_step
        data["log_tail"] = "\n".join(log.splitlines()[-TAIL_LINES:])
    return data
