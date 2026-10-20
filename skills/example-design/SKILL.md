---
name: example-design
description: How to design the code example a codelabgen lesson is built around, and how to write its lesson spec (`.codelabgen/lessons/<id>/spec.yaml`) — example complexity, the storyline across lessons, offline tests, experiments, regions. Used by the example-designer agent.
user-invocable: false
---

# Designing a lesson's example

Every lesson teaches one idea through one runnable example. The example is the lesson's backbone: the read-along explains its code next to it, and the notes explain the concept by pointing at it. Your output is the **lesson spec**. The code-author implements it, so it must be concrete enough to build without guessing.

## The core rule: the example is exactly as complex as the idea needs

- The **domain** must be obvious at a glance: a calculator, support tickets, a to-do list, a library catalog, an order. A learner should never spend effort understanding the business problem.
- The **technology** is where the complexity goes. Every part of the example should exercise the lesson's concept or be strictly needed to run it.
- **Cut everything else:** no argument parsing, logging setup, config frameworks, class hierarchies, retries or error handling unless the lesson is about them.
- **Size guide:** a first lesson is often 20–60 lines of lesson code. A later lesson may need 100–300. If a file passes about 150 lines, ask whether it really teaches one idea.
- **Prefer determinism.** Rules instead of an LLM call, fixed inputs instead of user input, unless the lesson is about the non-deterministic part.

Bad: a "smart assistant" whose prompt engineering and API wrangling hide the graph wiring the lesson is about. Good: a three-node graph that routes a ticket by keywords, so that the routing mechanism is the only new thing.

## The storyline across lessons

The curriculum says for each lesson whether its example is `new` or `extend`s an earlier lesson's example.

- **extend:** the lesson starts from a copy of the earlier lesson's code. `codelabgen scaffold lesson <id>` makes the copy and renames the package. Design a **small, focused delta** that adds the new concept. List each change in `delta`. Don't refactor or rename things the new concept doesn't need; the learner should be able to diff the two lessons and see only the new idea.
- **new:** start fresh, but reuse the course's familiar domains and names where it helps.
- **Look ahead.** If later lessons extend this example, leave natural extension points, but never build for them now.

## Confirm the API before you design

Your spec names concrete APIs, so check that they exist in the **pinned version**:

1. Read `.codelabgen/research/deprecations.md` and the `code-truth` source digests, if present.
2. Read the installed library source. The code-authoring skill's runtime reference (`${CLAUDE_PLUGIN_ROOT}/skills/code-authoring/references/<runtime>.md`, runtime from `.codelabgen/config.yaml`) says how to install the dependency and where its sources are. Grep them for the classes and functions you plan to use and check the signatures.
3. Use the official docs (WebFetch) for intended usage. When the docs and the installed source disagree, the installed source wins.

Never put an API into the spec that you have not seen in the pinned version.

## Tests: offline and deterministic

The spec lists the tests the code-author must write. Tests run in `codelabgen verify` **before** the live run, and must:

- need no network, no API keys and no LLM: use fakes, stubs or in-memory backends (for example an in-memory checkpointer instead of Postgres)
- check behaviour the lesson is about (the route a ticket takes, the state after a step), not trivia
- be few: usually 2–6 small tests

## The live run (`run_cmd`)

`run_cmd` runs in the lesson directory: for Python through `uv run`, usually `python -m <package>`; for Node usually `npx tsx src/main.ts`; for Go usually `go run .`; for Rust usually `cargo run --quiet`. It must:

- finish on its own in well under `run_timeout_s` (default 300 s; aim for seconds)
- print output that shows the concept working; the notes quote it as the real output
- use the real services the lesson declares (`services`, for example `postgres`), with connection settings from environment variables

## Experiments

List 3–5 "what to try" experiments. Each one is a small change with an observable effect that deepens understanding: "remove the edge from X to Y and run again: compilation fails with …", "send a ticket with both keywords: …". Write each as **change → what you will observe → why**. Prefer experiments that show a common mistake.

## Recordings

A terminal recording helps when the output **unfolds over time** or the terminal is the interface: streaming tokens, progress, an interactive CLI, a long-running process with log lines. A short, static output doesn't need one: the read-along quotes it as text.

For each recording, give a `name` (kebab-case, used for the file names), the `cmd` as for `run_cmd` (for example `python -m l1_2_routing --stream` or `go run . --stream`), `max_seconds` (keep it under 30), and, for interactive programs, an `input_script` that is piped to the program's stdin. Recordings run after the tests pass, with the lesson's environment.

## Regions

Name the code regions the notes will show as snippets: snake_case, one per meaningful unit (the state class, the routing function, the graph wiring). The code-author wraps each in `# region <name>` / `# endregion` markers.

## The spec file

Write `.codelabgen/lessons/<id>/spec.yaml`. `codelabgen schema show lesson-spec` prints the full schema. File paths are relative to the lesson directory.

```yaml
id: "1.2"
title: Условные рёбра и маршрутизация        # course language
scenario: >-                                  # English, for the agents
  Support tickets arrive as text. A classify node tags each ticket by keywords,
  a conditional edge routes it to the billing, tech or general queue node,
  and each queue node appends a reply. The run prints the route of three
  sample tickets.
files:                    # relative to the lesson dir; layout per runtime (see code-authoring)
  - src/l1_2_routing/state.py
  - src/l1_2_routing/graph.py
  - src/l1_2_routing/__main__.py
  - tests/test_routing.py
delta_from: null          # or the lesson id this one extends
delta: []                 # for extend: one line per change
run_cmd: python -m l1_2_routing
run_timeout_s: 60
services: []              # e.g. [postgres]
regions: [state, classify, route, build_graph]
tests:
  - a billing ticket ends in the billing queue
  - a ticket without keywords goes to general
experiments:
  - "Return an unknown queue name from route(): …"
env: []                   # extra variables this lesson needs, if any
recordings: []           # e.g. [{name: stream-reply, cmd: "python -m l1_2_routing", max_seconds: 20}]
```

`scenario`, `delta`, `tests` and `experiments` are in English: they are instructions for the agents. `title` is in the course language. Code identifiers are English.
