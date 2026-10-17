"""`codelabgen eval`: score a generated course against the codelabgen rubric.

Automatic dimensions (0–100 each, weighted):

  completion    20%  lessons done; blocked lessons count against it
  verification  25%  each lesson's latest verify run passed (or a fresh run, --reverify)
  consistency   15%  `check all` problems; the strict site build (--site)
  content       25%  per-lesson structure: code links in the read-along, real output, experiments,
                     diagrams, self-check, further reading, tests, comment density
  process       15%  review rounds and fix attempts per lesson

The human part: `eval` writes `.codelabgen/eval-human.md`, a checklist for two
sampled lessons. Scores filled in there (1–5) are read back on the next run and
reported next to the automatic score. They are not mixed into it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from codelabgen import checks, runtimes
from codelabgen import curriculum as cur
from codelabgen.course import Course, atomic_write
from codelabgen.markdown import LINK, code_blocks, prose_lines
from codelabgen.models import Stage
from codelabgen.state import StateStore

WEIGHTS = {"completion": 20, "verification": 25, "consistency": 15, "content": 25, "process": 15}
TEST_PATTERNS = {
    "python-uv": re.compile(r"^\s*def test_\w+", re.MULTILINE),
    "node": re.compile(r"^\s*(?:test|it)\s*\(", re.MULTILINE),
    "go": re.compile(r"^func Test\w+\s*\(", re.MULTILINE),
}
COMMENT = {"python-uv": ("#",), "node": ("//", "/*", "*"), "go": ("//",)}
HUMAN_QUESTIONS = [
    "Technical accuracy: everything said is true for the pinned version",
    "Example: as simple as the idea allows, domain doesn't distract",
    "Read-along: I could follow the code without other help",
    "Notes: explain the concept well, like a good book chapter",
    "Language: reads naturally in the course language",
    "Experiments: worth doing, and the explanations are right",
]


@dataclass
class LessonScore:
    lesson: str
    criteria: dict[str, bool] = field(default_factory=dict)
    metrics: dict[str, float | int] = field(default_factory=dict)

    @property
    def score(self) -> float:
        return 100 * sum(self.criteria.values()) / len(self.criteria) if self.criteria else 0.0


def lesson_content(course: Course, lesson) -> LessonScore:
    runtime = runtimes.for_course(course)
    folder = course.root / lesson.rel_dir
    readalong_path, notes_path = folder / "docs" / "readalong.md", folder / "docs" / "notes.md"
    readalong = readalong_path.read_text() if readalong_path.is_file() else ""
    notes = notes_path.read_text() if notes_path.is_file() else ""
    result = LessonScore(lesson.id)

    code_refs = len(re.findall(r"\]\([^)]*#L\d+", readalong))
    output_blocks = sum(1 for _ in code_blocks(notes, "text"))
    experiments = notes.count("<details")
    headings = sum(1 for _, line in prose_lines(notes) if line.startswith("## "))
    diagrams = (
        sum(1 for _ in code_blocks(notes, "mermaid"))
        + sum(1 for _ in code_blocks(readalong, "mermaid"))
        + len(re.findall(r"!\[[^\]]*\]\([^)]+\.svg\)", notes + readalong))
    )
    external = [
        t for _, line in prose_lines(notes) for t in LINK.findall(line) if t.startswith("http")
    ]
    code = runtimes.real_code_files(runtime, folder, lesson)
    tests = runtime.test_files(folder, lesson)
    pattern = TEST_PATTERNS.get(runtime.kind, TEST_PATTERNS["python-uv"])
    test_count = sum(len(pattern.findall(p.read_text(errors="replace"))) for p in tests)
    code_lines = comment_lines = 0
    prefixes = COMMENT.get(runtime.kind, ("#",))
    for path in code:
        in_docstring = False
        for raw in path.read_text(errors="replace").splitlines():
            line = raw.strip()
            if not line:
                continue
            code_lines += 1
            if line.count('"""') == 1:
                in_docstring = not in_docstring
                comment_lines += 1
            elif in_docstring or line.startswith(prefixes) or line.startswith('"""'):
                comment_lines += 1
    density = comment_lines / code_lines if code_lines else 0.0

    result.metrics = {
        "readalong_lines": len(readalong.splitlines()),
        "notes_lines": len(notes.splitlines()),
        "code_refs": code_refs,
        "experiments": experiments,
        "diagrams": diagrams,
        "external_links": len(external),
        "code_lines": code_lines,
        "tests": test_count,
        "comment_density": round(density, 2),
    }
    result.criteria = {
        "readalong exists": bool(readalong),
        "notes exist": bool(notes),
        "readalong links 3+ places in the code": code_refs >= 3,
        "notes quote real output": output_blocks >= 1,
        "3+ experiments and self-check answers": experiments >= 4,
        "notes have 4+ sections": headings >= 4,
        "a diagram": diagrams >= 1,
        "self-check questions": "<details" in notes,
        "2+ further-reading links": len(external) >= 2,
        "2+ tests": test_count >= 2,
        "comment density ≥ 15%": density >= 0.15,
    }
    return result


def latest_run(course: Course, lesson_id: str) -> dict | None:
    folder = course.meta / "runs" / lesson_id
    if not folder.is_dir():
        return None
    for run in sorted(folder.iterdir(), reverse=True):
        result = run / "result.json"
        if result.is_file():
            return json.loads(result.read_text())
    return None


def evaluate(course: Course, reverify: bool = False, site: bool = False) -> dict:
    curriculum = cur.load(course)
    lessons = cur.lessons(curriculum)
    state = StateStore(course).load()
    total = len(lessons) or 1
    dims: dict[str, float] = {}
    details: dict = {}

    done = sum(
        1
        for lesson in lessons
        if state.lessons.get(lesson.id) and state.lessons[lesson.id].stage is Stage.DONE
    )
    blocked = [lid for lid, lesson in state.lessons.items() if lesson.stage is Stage.BLOCKED]
    dims["completion"] = max(0.0, 100 * done / total - 10 * len(blocked))
    details["completion"] = {"done": done, "total": len(lessons), "blocked": blocked}

    verified = {}
    if reverify:
        from codelabgen.verify import verify

        for lesson in lessons:
            verified[lesson.id] = verify(course, lesson.id).passed
    else:
        for lesson in lessons:
            run = latest_run(course, lesson.id)
            verified[lesson.id] = bool(run and run["passed"])
    dims["verification"] = 100 * sum(verified.values()) / total
    details["verification"] = {"fresh": reverify, "passed": verified}

    problems = {name: len(check(course)) for name, check in checks.CHECKS.items()}
    consistency = max(0.0, 100 - 5 * sum(problems.values()))
    site_ok = None
    if site:
        from codelabgen import site as sitemod
        from codelabgen import toc

        toc.generate(course)
        site_ok = sitemod.run(course, "build", []).returncode == 0
        consistency = consistency if site_ok else consistency * 0.5
    dims["consistency"] = consistency
    details["consistency"] = {"problems": problems, "site_build": site_ok}

    contents = [lesson_content(course, lesson) for lesson in lessons]
    dims["content"] = sum(c.score for c in contents) / total
    details["content"] = {
        c.lesson: {
            "score": round(c.score),
            "missing": [k for k, v in c.criteria.items() if not v],
            "metrics": c.metrics,
        }
        for c in contents
    }

    rounds = [
        state.lessons[lesson.id].review_rounds for lesson in lessons if lesson.id in state.lessons
    ]
    fixes = [
        state.lessons[lesson.id].fix_attempts for lesson in lessons if lesson.id in state.lessons
    ]
    runs = [
        len(list((course.meta / "runs" / lesson.id).glob("*")))
        if (course.meta / "runs" / lesson.id).is_dir()
        else 0
        for lesson in lessons
    ]
    per_lesson = [
        100 - 20 * min(r, 2) - 10 * min(f, 3) for r, f in zip(rounds, fixes, strict=False)
    ]
    dims["process"] = sum(per_lesson) / total if per_lesson else 0.0
    details["process"] = {
        "review_rounds": dict(zip([lesson.id for lesson in lessons], rounds, strict=False)),
        "fix_attempts_total": sum(fixes),
        "verify_runs_total": sum(runs),
    }

    overall = sum(dims[k] * w for k, w in WEIGHTS.items()) / sum(WEIGHTS.values())
    human = read_human(course)
    result = {
        "course": str(course.root),
        "topic": course.load_config().topic,
        "runtime": runtimes.for_course(course).kind,
        "overall": round(overall, 1),
        "dimensions": {k: round(v, 1) for k, v in dims.items()},
        "weights": WEIGHTS,
        "details": details,
        "human": human,
    }
    atomic_write(course.meta / "eval.json", json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    write_human_template(course, lessons, contents, state)
    atomic_write(course.meta / "eval.md", render_markdown(result))
    return result


def sample_lessons(lessons, contents, state) -> list:
    """Two lessons for the human read: the first one and the most reworked other one."""
    if not lessons:
        return []
    first = lessons[0]
    others = lessons[1:]
    if not others:
        return [first]
    worst = max(
        others,
        key=lambda lesson: (
            state.lessons[lesson.id].review_rounds if lesson.id in state.lessons else 0,
            -next(c.score for c in contents if c.lesson == lesson.id),
        ),
    )
    return [first, worst]


def human_path(course: Course) -> Path:
    return course.meta / "eval-human.md"


def write_human_template(course, lessons, contents, state) -> None:
    path = human_path(course)
    if path.exists():
        return
    lines = [
        "# Human review",
        "",
        "Read these lessons as a learner would, and score each question from 1 (poor) to "
        "5 (excellent) by replacing the `_`. Run `codelabgen eval` again to include them.",
        "",
    ]
    for lesson in sample_lessons(lessons, contents, state):
        lines += [
            f"## {lesson.id} {lesson.node.title}",
            "",
            f"`{lesson.rel_dir.as_posix()}/docs/readalong.md`, `docs/notes.md`",
            "",
        ]
        lines += [f"- [_] {question}" for question in HUMAN_QUESTIONS]
        lines += ["", "Notes:", "", ""]
    atomic_write(path, "\n".join(lines))


def read_human(course: Course) -> dict | None:
    path = human_path(course)
    if not path.is_file():
        return None
    scores: dict[str, dict[str, int]] = {}
    current = None
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            current = line[3:].split(" ", 1)[0]
            scores[current] = {}
        match = re.match(r"- \[([1-5])\] (.+)", line.strip())
        if match and current:
            scores[current][match.group(2)] = int(match.group(1))
    filled = {k: v for k, v in scores.items() if v}
    if not filled:
        return None
    values = [s for lesson in filled.values() for s in lesson.values()]
    return {"lessons": filled, "average": round(sum(values) / len(values), 2)}


def render_markdown(result: dict) -> str:
    lines = [
        f"# Evaluation: {result['topic']} ({result['runtime']})",
        "",
        f"**Overall: {result['overall']} / 100**",
        "",
        "| Dimension | Score | Weight |",
        "|---|---|---|",
    ]
    for name, score in result["dimensions"].items():
        lines.append(f"| {name} | {score} | {result['weights'][name]}% |")
    details = result["details"]
    lines += [
        "",
        "## Completion",
        "",
        f"{details['completion']['done']} of {details['completion']['total']} lessons done"
        + (
            f"; blocked: {', '.join(details['completion']['blocked'])}"
            if details["completion"]["blocked"]
            else ""
        ),
        "",
    ]
    failed = [k for k, v in details["verification"]["passed"].items() if not v]
    lines += [
        "## Verification",
        "",
        ("All lessons pass" if not failed else f"Not passing: {', '.join(failed)}")
        + (" (fresh run)" if details["verification"]["fresh"] else " (latest runs)"),
        "",
    ]
    problems = {k: v for k, v in details["consistency"]["problems"].items() if v}
    lines += [
        "## Consistency",
        "",
        ("No problems" if not problems else ", ".join(f"{k}: {v}" for k, v in problems.items()))
        + (
            ""
            if details["consistency"]["site_build"] is None
            else f"; site build {'ok' if details['consistency']['site_build'] else 'FAILED'}"
        ),
        "",
    ]
    lines += ["## Content", "", "| Lesson | Score | Missing |", "|---|---|---|"]
    for lesson_id, item in details["content"].items():
        lines.append(f"| {lesson_id} | {item['score']} | {'; '.join(item['missing']) or '—'} |")
    process = details["process"]
    lines += [
        "",
        "## Process",
        "",
        f"Review rounds: {sum(process['review_rounds'].values())} · fix attempts: "
        f"{process['fix_attempts_total']} · verify runs: {process['verify_runs_total']}",
        "",
    ]
    human = result["human"]
    lines += [
        "## Human review",
        "",
        (
            f"Average {human['average']} / 5 over {len(human['lessons'])} lessons"
            if human
            else "Not filled in yet: `.codelabgen/eval-human.md`"
        ),
        "",
    ]
    return "\n".join(lines)
