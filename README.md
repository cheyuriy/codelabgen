# codelabgen

A Claude Code plugin that generates hands-on courses for a technology, language, framework or library. Every lesson is built around a runnable, tested code example and has three parts: the code, a read-along walkthrough of the code, and book-style notes.

## Layout

| Path | What it holds |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `commands/` | Slash commands (`/codelabgen:status`, …) |
| `skills/` | Procedural knowledge loaded by the orchestrator and the agents |
| `agents/` | Subagent definitions (leaf workers) |
| `hooks/` | Plugin hooks: state-file guard, subagent log |
| `src/codelabgen/`, `tests/` | The `codelabgen` CLI with every deterministic step; the repo root is its uv project |
| `src/codelabgen/templates/` | Templates for generated course files |
| `schemas/` | JSON Schemas of the data files, generated from `src/codelabgen/models.py` |

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

## Making a course

In Claude Code started with the plugin:

```
/codelabgen:new LangGraph --target ~/courses/langgraph --lang en
```

`/codelabgen:new` builds the course in one session: research, the source review, topics and the curriculum, the plan review, every lesson, assembly and the evaluation. The reviews and other questions (LLM provider, keys) are asked in the chat. Useful options: `--version` pins the technology version, `--source <url>` adds sources you want included, `--source-type` and `--sources-per-type` narrow the research, and `--wishes "…"` sets scope or size ("at most 3 lessons").

Other commands:

| Command | What it does |
|---|---|
| `/codelabgen:resume <dir>` | Continue a course from wherever it stopped, including work interrupted in an earlier session |
| `/codelabgen:status <dir>` | Phase, lesson stages and blocked lessons |
| `/codelabgen:sources`, `/codelabgen:plan` | Review sources or the plan of a course stopped at that review, then continue to the end |
| `/codelabgen:lesson <id\|all>` | Produce (or redo, with `--redo <stage>`) single lessons |
| `/codelabgen:build` | Assemble the course: glossary, READMEs, `run.sh`, checks, the MkDocs site, a git commit |
| `/codelabgen:extend <dir> "<request>"` | Deepen a topic or add new ones to a finished course |

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

## Development

With the environment activated:

```bash
pytest
ruff check . && ruff format --check .
codelabgen schema export   # after changing models.py
```
