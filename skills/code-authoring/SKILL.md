---
name: code-authoring
description: How to write and fix the code of a codelabgen lesson from its spec — project layout, pinned dependencies, teaching-grade comments, region markers for snippets, offline tests, environment variables, and getting `codelabgen verify` to pass. Used by the code-author and code-fixer agents.
user-invocable: false
---

# Writing lesson code

The code is what learners run, read and experiment with. It must work in the pinned version, read like a well-commented teaching example, and pass `codelabgen verify`.

## Layout (Python)

The lesson directory was created by `codelabgen scaffold`. Keep this layout:

```
<lesson dir>/
├── pyproject.toml          # lesson project: name, pinned dependencies
├── src/<package>/
│   ├── __init__.py         # one-line docstring; keep it
│   ├── __main__.py         # the live run: `python -m <package>`
│   └── *.py                # the lesson code, split as the spec's `files` say
└── tests/test_*.py         # offline tests
```

- Create exactly the files in the spec's `files`. If you need another file, say so in the status `notes`.
- Import the lesson's own modules by the package name: `from l1_2_routing.graph import build_graph`.
- Don't touch `docs/`, `README.md` or `.codelabgen/`.

## Dependencies

- Add them to `dependencies` in the lesson's `pyproject.toml`, **pinned exactly** to the course's pinned version: `"langgraph==1.2.15"`. Pin extra packages (for example `langgraph-checkpoint-postgres`, `psycopg[binary]`) to versions that work with it.
- Then sync the module's workspace: `env -u VIRTUAL_ENV uv sync --all-packages`, run in the module directory (the parent of the lesson). Lessons in one module share a lockfile, so keep versions consistent with the other lessons in the module.
- `pytest` and `ruff` come from the module's dev group; don't add them to the lesson.

## Use only APIs you have seen

Before writing a call, confirm it exists in the installed version. The package source is in `<module dir>/.venv/lib/python3.*/site-packages/`; grep it for the class or function and read the signature. Check `.codelabgen/research/deprecations.md` when it exists, and never use anything listed there. When the docs and the installed source disagree, the installed source wins.

## Teaching-grade code

- **Comments and docstrings in English**, more than in production code. Explain *why* and *what the library does here*, not what the syntax does. A learner should be able to follow the file without the read-along.
- Each function and class gets a docstring. Each non-obvious line involving the technology gets a comment.
- **Simple over clever.** Plain functions, explicit names, no premature abstraction, no metaprogramming. Prefer the library's most common, documented idiom.
- Type hints on functions and state definitions.
- Configuration through environment variables, read with `os.environ["NAME"]` (or `.get` with a sensible default for non-secret settings). Never hardcode secrets or connection strings. `codelabgen verify` loads the course and lesson `.env` files.

## Region markers

Wrap every region the spec lists:

```python
# region route
def route(state: TicketState) -> str:
    """Pick the queue for a ticket from its category."""
    return QUEUES.get(state["category"], "general")
# endregion
```

- Names exactly as in the spec's `regions`. Regions may nest. Markers never appear in the docs.
- `ruff format` puts two blank lines before an `# endregion` that follows a top-level function or class. That is expected; leave it.

## Tests

- Write the tests the spec lists, in `tests/test_*.py`, with plain `assert`s.
- **Offline only:** no network, no API keys, no LLM, no Docker. Use fakes and in-memory backends (an in-memory checkpointer instead of Postgres, a fake chat model instead of a real one).
- Fast and deterministic.

## The live run

`src/<package>/__main__.py` implements the spec's `run_cmd`. It uses the real services (for example Postgres through `POSTGRES_URL`), prints clear, readable output showing the concept at work, and exits by itself. Its output is quoted in the read-along, so make it worth reading: short labeled lines, no debug noise.

## Finish with a green verify

1. In the lesson directory: `env -u VIRTUAL_ENV uv run ruff format .`, then `env -u VIRTUAL_ENV uv run ruff check --fix .`
2. Run `codelabgen verify <id> --course <course dir>`. It prints JSON. If it fails, read `failed_step` and `log_tail` (the full log is in the course's `run_dir`), fix, and run it again.
3. Stop after 5 failed runs and report `failed` with the cause in `notes`.

Don't pass `--update-state`; the orchestrator records the official result.

## Fixing failures (code-fixer)

You get the failing verify summary. Work from the evidence:

- `env`: a variable is missing. You can't fix it in code: report `needs-user` and name the variable.
- `services`: Docker or the service failed to start. Read the log's diagnosis: a port taken by another course's container, or a service not published on its port, needs the user (report `needs-user` with the suggested command), as does Docker itself being unavailable.
- `sync`: a dependency doesn't resolve. Fix the pins in `pyproject.toml`.
- `lint` / `format`: run `ruff format` and `ruff check --fix`, then fix what remains by hand.
- `offline-tests` / `live-run`: read the traceback, check the API against the installed source, and fix the code. Never weaken or delete a test to make it pass unless the test itself contradicts the spec, and say so in `notes`.

Make the smallest change that fixes the cause. Keep regions, comments and the spec's behaviour intact.
