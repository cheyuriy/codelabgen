---
name: source-package-internals
description: How to use a technology's own repository at the pinned version as a codelabgen source — examples, tests, docstrings, notebooks, cookbooks and templates — plus LLM-oriented docs (llms.txt, Context7). The strongest code-truth material. Source type `package-internals`.
user-invocable: false
---

# The library itself (`package-internals`)

Nothing shows how an API really behaves in the pinned version better than the library's own code. Tests are executable specifications, examples are maintained by the authors, and docstrings explain intent. This is the course's best `code-truth`.

## Get the code at the pinned version

1. Find the repo from `research/overview.md` or `codelabgen pkg-info`.
2. `codelabgen repo clone <owner/name> --package <package name>`. It finds the tag of the pinned version (including monorepo tags like `langgraph==1.2.15`) and prints the interesting folders.
3. Check `version_matched` in its output. If it is false, the clone is the default branch: say so in each `reason`, and lower the score a little.

## What to look at

| Where | Why |
|---|---|
| `examples/`, `cookbook/`, `templates/`, notebooks | Complete, maintained usage examples |
| `tests/` of the main package | How each API behaves, including edge cases and errors. Find a feature's tests by grepping for its name |
| Public modules' docstrings | Intended usage and parameter meanings |
| `docs/` in the repo | Docs sources, sometimes with more detail than the site |
| Official template or starter repos (often separate repos in the same org) | Project layout as the maintainers recommend it |

Also check for LLM-oriented docs: `codelabgen llms-txt <docs root>`. If the Context7 MCP tools are available in your session, look up the library there too.

## What to record

Record GitHub URLs pointing into the repo **at the pinned tag** (`https://github.com/<repo>/tree/<tag>/<path>`), one per useful folder or file group:
- the examples or cookbook root (`code-truth`, often `structure`)
- the tests of the core package (`code-truth`, and `pitfalls` when they cover error cases)
- notable official templates (`code-truth`)
- `llms.txt`, if it exists and the official-docs hunter hasn't recorded it (`structure`, `code-truth`)

In `reason`, say what is there and how to use it: "Tests for StateGraph compile errors: unknown nodes, missing entry point, duplicate names."
