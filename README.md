# codelabgen

A Claude Code plugin that generates hands-on courses for a technology, language, framework or library. Every lesson is built around a runnable, tested code example and has three parts: the code, a read-along walkthrough of the code, and book-style notes.

The design is in `seed_docs/PLAN.md` (kept out of git).

## Layout

| Path | What it holds |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `commands/` | Slash commands (`/codelabgen:status`, …) |
| `skills/` | Procedural knowledge loaded by the orchestrator and the agents |
| `agents/` | Subagent definitions (leaf workers) |
| `src/codelabgen/`, `tests/` | The `codelabgen` CLI with every deterministic step; the repo root is its uv project |
| `schemas/` | JSON Schemas of the data files, generated from `src/codelabgen/models.py` |
| `templates/` | Templates for generated course files |

## Setup

The repo root is a uv project with a single virtual environment in `.venv`. `uv sync` installs the `codelabgen` CLI into it in editable mode, so changes to `src/` take effect immediately. Always work with that environment activated: Claude Code started from an activated shell passes it on to every command it runs, so agents find `codelabgen` on `PATH`.

```bash
uv sync
source .venv/bin/activate
codelabgen doctor        # which external tools are present, and what a missing one disables
claude --plugin-dir .    # load the plugin from this checkout
```

## Development

With the environment activated:

```bash
pytest
ruff check . && ruff format --check .
codelabgen schema export   # after changing models.py
```

## Status

- M0 (foundation): `codelabgen init`, `state`, `schema`, `doctor`; the `state-protocol` skill; `/codelabgen:status`.
- M1 (lesson pipeline): `curriculum`, `scaffold`, `verify`, `snippets`, `check snippets`, `env`; six lesson agents and their skills; the orchestrator skill (lesson production); `/codelabgen:lesson`. Test course: `tests/fixtures/make-m1-course.sh <dir>`.
