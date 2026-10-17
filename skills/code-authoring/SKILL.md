---
name: code-authoring
description: How to write and fix the code of a codelabgen lesson from its spec — layout, pinned dependencies, teaching-grade comments, region markers for snippets, offline tests, environment variables, and getting `codelabgen verify` to pass — for Python (uv), Node (TypeScript) and Go courses. Used by the code-author and code-fixer agents.
user-invocable: false
---

# Writing lesson code

The code is what learners run, read and experiment with. It must work in the pinned version, read like a well-commented teaching example, and pass `codelabgen verify`.

## First: your runtime's reference

The course runtime is `runtime.kind` in `.codelabgen/config.yaml`. Read its reference before writing anything. It covers the layout, dependencies, where installed library sources live, comment style, the formatter and linter, and how tests and the live run work:

| `runtime.kind` | Reference |
|---|---|
| `python-uv` | `${CLAUDE_PLUGIN_ROOT}/skills/code-authoring/references/python.md` |
| `node` | `${CLAUDE_PLUGIN_ROOT}/skills/code-authoring/references/node.md` |
| `go` | `${CLAUDE_PLUGIN_ROOT}/skills/code-authoring/references/go.md` |

`codelabgen curriculum lessons` gives each lesson's directory, `package` and `project` names.

## Files

- The lesson directory was created by `codelabgen scaffold`. Keep its layout.
- Create exactly the files in the spec's `files`. If you need another file, say so in the status `notes`.
- The scaffold's placeholder (`__init__.py` docstring, `src/main.ts` or `main.go` with a comment) is yours to replace or keep.
- Don't touch `docs/`, `README.md` or `.codelabgen/`.

## Use only APIs you have seen

Before writing a call, confirm it exists in the installed version. The reference says where the installed sources are; grep them for the function or type and read the signature. Check `.codelabgen/research/deprecations.md` when it exists, and never use anything listed there. When the docs and the installed source disagree, the installed source wins.

## Teaching-grade code

- **Comments in English**, more than in production code. Explain *why* and *what the library does here*, not what the syntax does. A learner should be able to follow the file without the read-along.
- Every exported function and type gets a doc comment in the language's style. Every non-obvious line involving the technology gets a comment.
- **Simple over clever.** Plain functions, explicit names, no premature abstraction, no metaprogramming. Prefer the library's most common, documented idiom.
- Types everywhere the language has them.
- **Configuration through environment variables.** Read them with the language's normal API, with a sensible default only for non-secret settings. Never hardcode secrets or connection strings. `codelabgen verify` loads the course and lesson `.env` files.

## Region markers

Wrap every region the spec lists, in the language's line-comment syntax:

```
# region route        (Python)        // region route        (TypeScript, Go)
…                                      …
# endregion                            // endregion
```

- Names exactly as in the spec's `regions`. Regions may nest. Markers never appear in the docs.
- If the formatter moves blank lines around a marker, that's expected; leave it.

## Tests

- Write the tests the spec lists, where the reference says tests live.
- **Offline only:** no network, no API keys, no LLM, no Docker. Use fakes and in-memory backends: an in-memory store instead of Postgres, a fake chat model instead of a real one.
- Fast and deterministic.

## The live run

The spec's `run_cmd` runs the lesson for real: with real services (for example Postgres through `POSTGRES_URL`) and real keys. It prints clear, readable output showing the concept at work, and exits by itself. Its output is quoted in the read-along, so make it worth reading: short labeled lines, no debug noise.

## Finish with a green verify

1. Format and lint with the commands from the reference.
2. Run `codelabgen verify <id> --course <course dir>`. It prints JSON. If it fails, read `failed_step` and `log_tail` (the full log is in the course's `run_dir`), fix, and run it again.
3. Stop after 5 failed runs and report `failed` with the cause in `notes`.

Don't pass `--update-state`; the orchestrator records the official result.

## Fixing failures (code-fixer)

You get the failing verify summary. Work from the evidence:

- `env`: a variable is missing. You can't fix it in code: report `needs-user` and name the variable.
- `services`: Docker or the service failed to start. Read the log's diagnosis. A port taken by another course's container, a service not published on its port, or Docker itself being unavailable all need the user: report `needs-user` with the suggested command.
- `sync`: a dependency doesn't resolve. Fix the pins in the lesson's manifest (see the reference).
- `lint` / `format`: run the formatter and the linter's fixer, then fix what remains by hand.
- `offline-tests` / `live-run`: read the error, check the API against the installed source, and fix the code. Never weaken or delete a test to make it pass unless the test itself contradicts the spec, and say so in `notes`.

Make the smallest change that fixes the cause. Keep regions, comments and the spec's behaviour intact.
