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

## Runtimes

| `runtime.kind` | Lessons | Needs |
|---|---|---|
| `python-uv` | uv workspace per module; ruff, pytest | `uv` |
| `node` | npm workspace per module; TypeScript (tsx, tsc), Biome, vitest | `node`, `npm` (Node 24 LTS or later) |
| `go` | `go.work` per module, one Go module per lesson; go vet, gofmt, go test | `go` |
| `rust` | Cargo workspace per module, one package per lesson; clippy, rustfmt, cargo test | `cargo` with `clippy` and `rustfmt` (rustup's default profile), a C linker (`cc`) |

## Evaluating generated courses

`codelabgen eval --course <dir> [--reverify] [--site]` scores a course (`.codelabgen/eval.md`, `eval.json`):

| Dimension | Weight | What it measures |
|---|---|---|
| completion | 20% | lessons done; blocked lessons |
| verification | 25% | latest (or, with `--reverify`, fresh) verify runs pass |
| consistency | 15% | `check all` problems; strict site build with `--site` |
| content | 25% | per lesson: snippets, real output, experiments, diagrams, self-check, further reading, tests, comment density |
| process | 15% | review rounds and fix attempts |

The automatic score catches broken and incomplete courses; quality needs a reader. `eval` writes `.codelabgen/eval-human.md`, a checklist for two sampled lessons (the first, and the most reworked one). Fill it in and run `eval` again.

Suggested evaluation set, one per runtime:

```
/codelabgen:new LangGraph --target ~/Documents/courses/eval-langgraph --lang ru
/codelabgen:new Zod --target ~/Documents/courses/eval-zod --lang en
/codelabgen:new "chi (Go HTTP router)" --target ~/Documents/courses/eval-chi --lang en
```

`/codelabgen:new` stops at the source review. Continue each course to the end:

1. `/codelabgen:sources --course <dir>`: approve (or edit) `.codelabgen/sources.md`. Topics and the curriculum are drafted, and it stops at the plan review.
2. `/codelabgen:plan --course <dir>`: approve the plan and answer the runtime questions (LLM provider, keys). The course is scaffolded and all lessons are produced.
3. `/codelabgen:build --course <dir>`: assemble the course and the site.

`/codelabgen:resume <dir>` continues from wherever a course stopped. When a course is done: `codelabgen eval --course <dir> --reverify --site`, fill in `eval-human.md`, and share `eval.md`, `report.md` and the human notes.

## Development

With the environment activated:

```bash
pytest
ruff check . && ruff format --check .
codelabgen schema export   # after changing models.py
```

## Status

- M0 (foundation): `codelabgen init`, `state`, `schema`, `doctor`; the `state-protocol` skill; `/codelabgen:status`.
- M7 (hardening): `node`, `go` and `rust` runtimes next to `python-uv` (scaffold, verify, run.sh, recordings, checks, extensions), per-runtime code-authoring and runtime-strategy references, `codelabgen eval` (rubric + human review sheet), plugin hooks (state-file guard, subagent log).
- M6 (extension): `extend start/status/stage/diff/apply/finish` (lessons matched by slug path; rewrite, stale propagation, opt-in renumbering that moves directories, packages, specs, runs and links), `sources keep-proposed`, `curriculum number/validate --file`, `services up/down/status`, per-course service ports with a published-port check in verify; gap-analyst agent, course-extension skill, extend modes for the architect and runtime planner; `/codelabgen:extend`.
- M5 (orchestration and resume): `state next` for every phase (from state and files on disk), `state task start/done/fail/reset/list` with interruption detection, `report`, `parallel_agents` budget; the orchestrator skill rewritten around one main loop; `/codelabgen:resume`.
- M4 (curriculum): `topics add/merge`, `sources digests/batches/index`, `curriculum number/render`, `config set runtime.*`, `config external add/clear`, custom services in `.codelabgen/services.yaml`; topic-extractor, curriculum-architect and runtime-planner agents; topic-extraction, source-digest, curriculum-design and runtime-strategy skills; `/codelabgen:plan`. Every phase is now covered.
- M3 (research): `fetch` (HTML/Markdown/PDF cache), `llms-txt`, `transcript`, `pkg-info`, `repo clone` (pinned-version tag), `github meta/repos/code/issues`, `sources add/list/render/apply`, `config`; tech-scout and source-hunter agents; source-evaluation and ten source-type skills; `/codelabgen:new`, `/codelabgen:sources`.
- M2 (assembly and visuals): `toc` (READMEs, nav, `run.sh`), `site build/serve`, `glossary`, `diagrams render`, `record`, `check all`, `commit`; the `site-assembly` skill; `/codelabgen:build`.
- M1 (lesson pipeline): `curriculum`, `scaffold`, `verify`, `snippets`, `check snippets`, `env`; six lesson agents and their skills; the orchestrator skill (lesson production); `/codelabgen:lesson`. Test course: `tests/fixtures/make-m1-course.sh <dir>`.
