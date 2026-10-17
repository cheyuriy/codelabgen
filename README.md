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

Optional tools, each enabling one feature (`codelabgen doctor` shows what is missing):

| Tool | Feature | Install (Ubuntu) |
|---|---|---|
| Docker | services such as Postgres in lessons | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/ubuntu/) |
| `asciinema` 3.x, `agg` | terminal recordings | binaries from the GitHub releases of `asciinema/asciinema` and `asciinema/agg` (apt's asciinema 2.x is too old) |
| `d2` | D2 diagrams | `curl -fsSL https://d2lang.com/install.sh \| sh -s --` |
| Graphviz (`dot`) | Graphviz diagrams | `sudo apt install graphviz` |
| `gh` | GitHub source discovery | `sudo apt install gh`, then `gh auth login` |
| `yt-dlp` | talk transcripts | `uv tool install yt-dlp` |

## Development

With the environment activated:

```bash
pytest
ruff check . && ruff format --check .
codelabgen schema export   # after changing models.py
```

## Status

- M0 (foundation): `codelabgen init`, `state`, `schema`, `doctor`; the `state-protocol` skill; `/codelabgen:status`.
- M4 (curriculum): `topics add/merge`, `sources digests/batches/index`, `curriculum number/render`, `config set runtime.*`, `config external add/clear`, custom services in `.codelabgen/services.yaml`; topic-extractor, curriculum-architect and runtime-planner agents; topic-extraction, source-digest, curriculum-design and runtime-strategy skills; `/codelabgen:plan`. Every phase is now covered.
- M3 (research): `fetch` (HTML/Markdown/PDF cache), `llms-txt`, `transcript`, `pkg-info`, `repo clone` (pinned-version tag), `github meta/repos/code/issues`, `sources add/list/render/apply`, `config`; tech-scout and source-hunter agents; source-evaluation and ten source-type skills; `/codelabgen:new`, `/codelabgen:sources`.
- M2 (assembly and visuals): `toc` (READMEs, nav, `run.sh`), `site build/serve`, `glossary`, `diagrams render`, `record`, `check all`, `commit`; the `site-assembly` skill; `/codelabgen:build`.
- M1 (lesson pipeline): `curriculum`, `scaffold`, `verify`, `snippets`, `check snippets`, `env`; six lesson agents and their skills; the orchestrator skill (lesson production); `/codelabgen:lesson`. Test course: `tests/fixtures/make-m1-course.sh <dir>`.
