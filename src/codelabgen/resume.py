"""`codelabgen state next`: what is left to do, in every phase.

The answer comes from the state (phase, lessons, tasks) and from the files on
disk (overview, sources, digests, curriculum), so a resumed session picks up
exactly where an interrupted one stopped. Actions are:

  run-agent   start a worker; `task` is the key to `state task start/done`
  command     a codelabgen command the orchestrator runs itself
  ask-user    the orchestrator needs the user (a review gate, a missing secret)
  advance     move to the next phase (`approved` marks a review gate)

A task still `running` is listed under `interrupted`: its worker stopped midway,
so the next worker for it must check and complete the partial work.
"""

from __future__ import annotations

import hashlib
from typing import Any

from codelabgen import curriculum as cur
from codelabgen import env as envmod
from codelabgen import sources as srcmod
from codelabgen.course import Course
from codelabgen.models import Phase, State
from codelabgen.state import StateStore

# (source type label, skill) — one hunter per row, in this order.
HUNTERS: list[tuple[str, str]] = [
    ("official-docs", "source-official-docs"),
    ("official-blog", "source-official-blog"),  # also release-notes and deprecations.md
    ("package-internals", "source-package-internals"),
    ("article", "source-articles"),
    ("github-repo", "source-github-repos"),
    ("qa", "source-qa"),
    ("paper-spec", "source-papers-specs"),
    ("talk-workshop", "source-talks-workshops"),
    ("university", "source-university"),
    ("book-course", "source-books-courses"),
]


def batch_key(ids: list[str]) -> str:
    return "topics:" + hashlib.sha1(",".join(sorted(ids)).encode()).hexdigest()[:8]


def agent(name: str, task: str, state: State, **args: Any) -> dict:
    previous = state.tasks.get(task)
    action = {"do": "run-agent", "agent": name, "task": task}
    if previous and previous.status == "running":
        action["interrupted"] = True
    if previous and previous.status == "failed":
        action["retry"] = previous.attempts
    return action | ({"args": args} if args else {})


def command(run: str, why: str | None = None) -> dict:
    return {"do": "command", "run": run} | ({"why": why} if why else {})


def ask(about: str, **details: Any) -> dict:
    return {"do": "ask-user", "about": about} | details


def advance(to: Phase, approved: bool = False) -> dict:
    flag = " --approved" if approved else ""
    return {"do": "advance", "to": to, "run": f"codelabgen state phase {to}{flag}"}


def next_actions(course: Course) -> dict:
    store = StateStore(course)
    state = store.load()
    config = course.load_config()
    meta = course.meta
    actions: list[dict] = []
    result: dict[str, Any] = {"phase": state.phase}

    extension = state.extension
    if extension and extension.stage not in ("lessons",):
        result["extension"] = {
            "id": extension.id,
            "stage": extension.stage,
            "request": extension.request,
        }
        result["actions"] = extension_actions(course, state, extension)
        result["interrupted"] = interrupted(state)
        return result
    if extension:
        result["extension"] = {
            "id": extension.id,
            "stage": extension.stage,
            "request": extension.request,
        }

    match state.phase:
        case Phase.INIT:
            actions.append(advance(Phase.RECON))

        case Phase.RECON:
            if not (meta / "research" / "overview.md").is_file():
                actions.append(agent("tech-scout", "recon:tech-scout", state))
            elif not config.version:
                actions.append(
                    ask(
                        "confirm the version proposed in research/overview.md",
                        then="codelabgen config set version <v>",
                    )
                )
            else:
                actions.append(advance(Phase.SOURCES))

        case Phase.SOURCES:
            registered = {s.url for s in srcmod.load(course)}
            missing_user = [
                u for u in config.user_sources if srcmod.normalize_url(u) not in registered
            ]
            if missing_user:
                actions.append(
                    command(
                        "codelabgen sources add (status user) for each URL",
                        why=f"user sources not recorded: {', '.join(missing_user)}",
                    )
                )
            for type_, skill in HUNTERS:
                task = f"sources:{type_}"
                if state.tasks.get(task) is None or state.tasks[task].status != "done":
                    actions.append(agent("source-hunter", task, state, type=type_, skill=skill))
            hunters_left = any(a["do"] == "run-agent" for a in actions)
            if not hunters_left:
                if not (meta / "research" / "deprecations.md").is_file():
                    actions.append(
                        agent(
                            "source-hunter",
                            "sources:deprecations",
                            state,
                            type="release-notes",
                            skill="source-official-blog",
                            only="write research/deprecations.md",
                        )
                    )
                else:
                    actions += [command("codelabgen sources render"), advance(Phase.GATE_SOURCES)]

        case Phase.GATE_SOURCES:
            actions += [
                ask(
                    "review the sources",
                    sheet=".codelabgen/sources.md",
                    then="codelabgen sources apply",
                ),
                advance(Phase.TOPICS, approved=True),
            ]

        case Phase.TOPICS:
            size = 5
            for ids in srcmod.batches(course, size):
                actions.append(agent("topic-extractor", batch_key(ids), state, sources=ids))
            if not actions:
                actions += [
                    command("codelabgen topics merge"),
                    command("codelabgen sources index"),
                    advance(Phase.CURRICULUM),
                ]

        case Phase.CURRICULUM:
            problems = curriculum_problems(course)
            if problems is not None:
                actions.append(
                    agent("curriculum-architect", "curriculum:architect", state, problems=problems)
                )
            elif not (meta / "research" / "runtime.md").is_file() or not config.runtime.kind:
                actions.append(agent("runtime-planner", "curriculum:runtime", state))
            else:
                actions += [
                    command("codelabgen sources index"),
                    command("codelabgen curriculum render"),
                    advance(Phase.GATE_PLAN),
                ]

        case Phase.GATE_PLAN:
            actions += [
                ask(
                    "review the plan and answer the runtime questions",
                    plan=".codelabgen/plan.md",
                    questions=".codelabgen/research/runtime.md",
                ),
                advance(Phase.SCAFFOLD, approved=True),
            ]

        case Phase.SCAFFOLD:
            if not state.lessons:
                actions += [command("codelabgen scaffold course"), command("codelabgen toc")]
            else:
                missing = env_missing(course)
                if missing:
                    actions.append(
                        ask("fill in the course .env", missing=missing, then="codelabgen env check")
                    )
                else:
                    actions.append(advance(Phase.LESSONS))

        case Phase.LESSONS:
            work = store.next_work()
            result |= {"lessons": work["lessons"], "blocked": work["blocked"]}
            if not work["lessons"] and not work["blocked"]:
                actions.append(ask("offer to assemble the course (/codelabgen:build)"))
                actions.append(advance(Phase.ASSEMBLY))
            elif not work["lessons"]:
                actions.append(ask("only blocked lessons are left", blocked=work["blocked"]))
            else:
                actions.append(command("work on the listed lessons (see lessons)"))

        case Phase.ASSEMBLY:
            actions += [
                command("codelabgen glossary build"),
                command("codelabgen toc"),
                command("codelabgen check all"),
                command("codelabgen site build"),
                command('codelabgen commit -m "<message>"'),
                advance(Phase.DONE),
            ]

        case Phase.DONE:
            if extension:
                actions.append(
                    command(
                        "codelabgen extend finish", why=f"extension {extension.id} is assembled"
                    )
                )

    result["interrupted"] = interrupted(state)
    result["actions"] = actions
    return result


def interrupted(state: State) -> list[dict]:
    return [
        {"task": key, "phase": task.phase, "lesson": task.lesson, "attempts": task.attempts}
        for key, task in state.tasks.items()
        if task.status == "running"
    ]


def extension_actions(course: Course, state: State, extension) -> list[dict]:
    """Actions for the extension stages before lesson production."""
    import yaml

    from codelabgen import extension as ext

    folder = ext.ext_dir(course, extension.id)
    prefix = f"ext{extension.id}"
    actions: list[dict] = []

    def pending(task: str) -> bool:
        return state.tasks.get(task) is None or state.tasks[task].status != "done"

    match extension.stage:
        case "gaps":
            if not (folder / "gaps.md").is_file() or not (folder / "hunt.yaml").is_file():
                actions.append(
                    agent(
                        "gap-analyst",
                        f"{prefix}:gaps",
                        state,
                        request=extension.request,
                        folder=str(folder),
                    )
                )
            else:
                actions.append(command("codelabgen extend stage research"))
        case "research":
            hunts = yaml.safe_load((folder / "hunt.yaml").read_text()) or []
            for hunt in hunts:
                task = f"{prefix}:hunt:{hunt['type']}"
                if pending(task):
                    actions.append(
                        agent(
                            "source-hunter",
                            task,
                            state,
                            type=hunt["type"],
                            skill=hunt["skill"],
                            focus=hunt.get("focus"),
                        )
                    )
            if not actions:
                actions += [
                    command("codelabgen sources keep-proposed --min-score 0.6"),
                    command("codelabgen extend stage digests"),
                ]
        case "digests":
            for ids in srcmod.batches(course, 5):
                actions.append(agent("topic-extractor", batch_key(ids), state, sources=ids))
            if not actions:
                actions += [
                    command("codelabgen topics merge"),
                    command("codelabgen sources index"),
                    command("codelabgen extend stage delta"),
                ]
        case "delta":
            proposed = ext.proposed_path(course, extension.id)
            problems = (
                ["the proposed curriculum does not exist yet"]
                if not proposed.is_file()
                else proposal_problems(course, proposed)
            )
            if problems:
                actions.append(
                    agent(
                        "curriculum-architect",
                        f"{prefix}:architect",
                        state,
                        mode="extend",
                        request=extension.request,
                        proposal=str(proposed),
                        gaps=str(folder / "gaps.md"),
                        problems=problems,
                    )
                )
            elif pending(f"{prefix}:runtime"):
                actions.append(
                    agent(
                        "runtime-planner",
                        f"{prefix}:runtime",
                        state,
                        mode="extend",
                        proposal=str(proposed),
                    )
                )
            else:
                actions += [
                    command("codelabgen extend diff"),
                    command("codelabgen extend stage gate"),
                ]
        case "gate":
            actions += [
                ask(
                    "review the extension",
                    delta=str(folder / "delta.md"),
                    new_sources="sources kept during this extension",
                ),
                command(
                    "codelabgen extend apply [--allow-renumber]",
                    why="after the user approves; renumbering needs explicit consent",
                ),
            ]
    return actions


def proposal_problems(course: Course, path) -> list[str] | None:
    try:
        cur.load(course, path)
    except cur.CurriculumError as exc:
        return exc.problems
    except Exception as exc:  # schema or YAML errors
        return [str(exc).splitlines()[0]]
    return None


def curriculum_problems(course: Course) -> list[str] | None:
    """None when curriculum.yaml exists and is valid, else what is wrong with it."""
    if not (course.meta / "curriculum.yaml").is_file():
        return ["curriculum.yaml does not exist yet"]
    try:
        cur.load(course)
    except cur.CurriculumError as exc:
        return exc.problems
    except Exception as exc:  # schema errors from pydantic, YAML syntax errors
        return [str(exc).splitlines()[0]]
    return None


def env_missing(course: Course) -> dict[str, list[str]]:
    curriculum = cur.load(course)
    missing = {}
    for lesson in cur.lessons(curriculum):
        report = envmod.check(course, curriculum, lesson)
        if report.missing:
            missing[lesson.id] = report.missing
    return missing
