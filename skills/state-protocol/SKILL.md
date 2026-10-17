---
name: state-protocol
description: How every codelabgen agent reads and changes course state through the `codelabgen` CLI — lesson stages, phases, failures, blocking, the event log, artifact locations and the status message agents return. Load before any work inside a codelabgen course directory.
user-invocable: false
---

# codelabgen state protocol

A codelabgen course is a directory with a hidden `.codelabgen/` folder. Its progress lives in `.codelabgen/state.json`, and every change to it goes through the `codelabgen` CLI. The CLI holds a lock, validates each change and writes an event to `.codelabgen/events.jsonl`, which is what makes an interrupted run resumable.

## Rules

1. **Never edit `state.json` or `events.jsonl` with Edit, Write or shell redirection.** Use the commands below.
2. **Pass the course explicitly** with `--course <dir>` (or set `CODELABGEN_COURSE`), unless the working directory is inside the course.
3. **A non-zero exit is a refusal, not a glitch.** Exit code 2 prints `error: …` with the reason, for example a skipped stage or a used-up budget. Report it; don't retry the same command or work around it.
4. **Only the orchestrator changes state.** Worker agents (example-designer, code-author, …) never run `state set`, `fail`, `block`, `phase` or `register`. They do their work, may run read-only commands and `state log`, and report through the status JSON at the end. The orchestrator checks the result and moves the stage.

## Running the CLI

codelabgen sessions run with the plugin's virtual environment activated, so `codelabgen` is on `PATH`. If it is not found, run it through uv instead:

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} codelabgen …
```

**Lesson commands need their own environment.** The lesson code has its own uv workspace per module. When you run `uv` for lesson code yourself, drop the plugin's environment first, or uv uses the wrong venv: `env -u VIRTUAL_ENV uv run …`. `codelabgen verify` does this for you.

## Lesson stages

Each lesson records the **last completed** stage:

```
pending → spec → code → verified → readalong → notes → reviewed → done
```

| Stage done | Work that moves it to the next stage | The orchestrator then runs |
|---|---|---|
| `pending` | example-designer writes `lessons/<id>/spec.yaml` | `codelabgen state set <id> spec` |
| `spec` | code-author writes the code and tests | `codelabgen state set <id> code` |
| `code` | `codelabgen verify <id> --update-state` passes (code-fixer repairs failures) | nothing: verify sets `verified` or counts a failure |
| `verified` | readalong-writer | `codelabgen state set <id> readalong` |
| `readalong` | notes-writer | `codelabgen state set <id> notes` |
| `notes` | lesson-reviewer, verdict pass | `codelabgen state set <id> reviewed` |
| `reviewed` | final checks | `codelabgen state set <id> done` |

`codelabgen state stages` prints the same table as JSON.

- **Forward** moves go exactly one stage at a time.
- **Rework** moves back to any earlier stage: `codelabgen state set <id> readalong --note "reviewer: example 2 unclear"`. Moving back from `notes` or `reviewed` uses up one review round, and the CLI refuses once the budget is gone.
- **Failed verify:** `codelabgen state fail <id> --note "<one-line cause>"`. When the fix budget runs out, the lesson becomes `blocked` automatically.
- **Block** for a decision only the user can make: `codelabgen state block <id> --reason "…"`. The orchestrator unblocks with `codelabgen state unblock <id>`.
- **Stale:** `codelabgen state stale <id> --reason "…"` marks a done lesson whose upstream changed. It must be redone from an earlier stage.

## Phases (orchestrator only)

```
init → recon → sources → gate_sources → topics → curriculum → gate_plan → scaffold → lessons → assembly → done
```

`codelabgen state phase <next>` advances exactly one phase. Leaving a gate (`gate_sources`, `gate_plan`) needs `--approved`, and only after the user approved in the conversation. Entering `assembly` requires every lesson to be `done`.

## Reading state

- `codelabgen state show`: human summary. `--json` gives the full state.
- `codelabgen state next`: JSON with what is left in the current phase (`actions`), the lesson work items in the `lessons` phase, and `interrupted` tasks. Lessons in one module run in order; separate modules run in parallel up to the budget.
- `codelabgen state task list --open`: tasks still running or failed. Tasks (`state task start/done/fail/reset`) are the orchestrator's record of worker runs; workers don't touch them.
- `codelabgen report`: the generation summary in `.codelabgen/report.md`.
- `codelabgen schema show <name>`: JSON Schema of a data file (`config`, `source`, `topic`, `curriculum`, `lesson-spec`, `run-result`, `glossary-entry`, …).

## Logging

Record notable facts that are not state changes, so the final report can use them:

```bash
codelabgen state log <kind> --lesson <id> --data key=value --data key=value
```

## Where artifacts go

Paths are relative to the course root.

| Artifact | Path |
|---|---|
| Research overview, deprecated APIs | `.codelabgen/research/overview.md`, `.codelabgen/research/deprecations.md` |
| Source candidates, source digests | `.codelabgen/sources.jsonl`, `.codelabgen/sources/<id>.md` |
| Topics | `.codelabgen/topics/<source-id>.jsonl` |
| Curriculum, plan | `.codelabgen/curriculum.yaml`, `.codelabgen/plan.md` |
| Lesson spec, review | `.codelabgen/lessons/<id>/spec.yaml`, `.codelabgen/lessons/<id>/review.md` |
| Lesson code and docs | `<module>/<id>-<slug>/` (code, `docs/notes.md`, `docs/readalong.md`) |

## What a worker returns

Finish with a short JSON block and nothing after it, so the orchestrator can parse it:

```json
{"lesson": "1.2", "status": "ok", "stage": "code", "artifacts": ["1-basics/1.2-routing/src/l1_2_routing/graph.py"], "notes": "one line, optional"}
```

`status` is `ok`, `failed` (the work could not be finished; say why in `notes`) or `needs-user` (a decision only the user can make). `stage` is the stage your work completes; the orchestrator decides whether to record it.
