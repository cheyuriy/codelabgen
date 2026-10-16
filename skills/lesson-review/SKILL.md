---
name: lesson-review
description: How to review a finished codelabgen lesson (code, read-along, notes) against its spec, the pinned technology version and the course rules, and write `.codelabgen/lessons/<id>/review.md` with a pass/revise verdict and concrete fixes. Used by the lesson-reviewer agent.
user-invocable: false
---

# Reviewing a lesson

You are the last check before a lesson counts as done. Judge it as a demanding teacher and a careful engineer would. The code already passed `codelabgen verify`, so your job is **correctness of what is taught, clarity, and consistency**, not whether the code runs.

## What to read

- The curriculum node: `.codelabgen/curriculum.yaml` (title, summary, objectives, example storyline)
- The spec: `.codelabgen/lessons/<id>/spec.yaml`
- The code: `<lesson dir>/src/`, `tests/`, `pyproject.toml`
- The read-along: `<lesson dir>/docs/readalong.md`
- The notes: `<lesson dir>/docs/notes.md`
- The latest verify run: `.codelabgen/runs/<id>/<latest>/` (`result.json`, `live-run.log`)
- For an extending lesson: the previous lesson's spec and code
- Source digests and `.codelabgen/research/deprecations.md`, when they exist

## Checklist

**Technical accuracy** (most important)
- Every statement about the technology is true for the pinned version. Spot-check claims against the installed source in `<module dir>/.venv/lib/python3.*/site-packages/` and the official docs.
- No deprecated or removed APIs, in code or text.
- The output quoted in the read-along matches `live-run.log`.

**Objectives**
- Each objective in the curriculum node is actually taught and shown in the example.
- Nothing important for this concept is missing; nothing belongs to a later lesson.

**Example and code**
- The example is as simple as the idea allows (see the example-design skill). The domain doesn't distract.
- For an extending lesson, the delta is focused on the new concept.
- Comments explain *why*. Names are clear. No dead code. No hardcoded secrets.
- Tests check the behaviour the lesson is about, and run offline.

**Read-along**
- Walks the code in an order that builds understanding. Every region shown is explained.
- Code appears only through snippet markers. `codelabgen check snippets <id>` prints `ok`.
- Run instructions are complete and correct. The experiments are concrete and their explanations are right.

**Notes**
- Explain the concept properly, in a book-like way, and tie it to the code.
- Diagrams are correct and readable; generated ones match the code.
- Self-check questions have correct answers. Further-reading links are real and relevant.

**Consistency and form**
- Code, read-along and notes agree with each other: same names, same behaviour, same output.
- Text is in the course language and reads naturally to a native speaker. Code and comments are in English.
- Only GitHub-and-site syntax: no `!!!`, content tabs, code annotations or `--8<--`. Math uses `$…$` and `$$…$$`.
- Relative links resolve.

## Verdict

- **pass:** nothing that would mislead or confuse a learner. Small polish issues may still be listed for later.
- **revise:** at least one issue a learner would trip over: a wrong claim, an unmet objective, unclear key explanation, broken snippet or link.

Don't fix things yourself. Describe each issue so the responsible agent can fix it without guessing.

## review.md

Write `.codelabgen/lessons/<id>/review.md` (in English: it is for the agents):

```markdown
# Review of lesson 1.2 — round 1

Verdict: revise
Rework from: readalong        # the earliest part that must change: code | readalong | notes

## Must fix
1. [readalong] Section "Маршрутизация": claims `add_conditional_edges` requires a path map; it is optional in 1.2.15 (see langgraph/graph/state.py). Remove the claim.
2. [notes] …

## Nice to have
- [notes] …
```

Each item is tagged `[code]`, `[readalong]` or `[notes]`. **Rework from** names the earliest part with a must-fix item: a code change also forces the read-along and notes to be refreshed. Omit it for a pass.

End with the status JSON from the state-protocol skill, adding `"verdict"` and `"rework_from"`:

```json
{"lesson": "1.2", "status": "ok", "stage": "reviewed", "verdict": "revise", "rework_from": "readalong", "artifacts": [".codelabgen/lessons/1.2/review.md"]}
```
