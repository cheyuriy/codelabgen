---
name: readalong-writing
description: How to write a codelabgen lesson's read-along (`docs/readalong.md`) — a plain explanation of the lesson code, meant to be read side by side with the code in the editor, referring to files, functions, classes and lines. Used by the readalong-writer agent.
user-invocable: false
---

# Writing the read-along

The learner opens the lesson code and the read-along side by side, for example in VS Code. The read-along explains the code: what each part is for, why it is written this way, and what the library does behind each call. That's all. No copies of the code, no theory (that's in the notes), no exercises.

Keep it simple and short. A paragraph or a few bullets per function is usually enough.

Write in the **course language** (`language` in `.codelabgen/config.yaml`). Identifiers, file names and commands stay as they are.

## Structure

```markdown
# <id> <lesson title> — разбор кода          ← "code walkthrough" in the course language

One or two sentences: what the program does. Run it with `./run.sh <id>` from the course root.
The concept itself: [конспект](notes.md).

## Что изменилось с урока X                   ← only when the example extends an earlier lesson
A short list of the changes, each with a link to the place in the code.

## [state.py](../src/l1_2_routing/state.py)   ← one section per file, in reading order
What the file is for, in a sentence.

- [`TicketState`](../src/l1_2_routing/state.py#L8) — …
- [`route`](../src/l1_2_routing/state.py#L12): the `Annotated[list[str], operator.add]` annotation in line 12 makes LangGraph …

## [graph.py](../src/l1_2_routing/graph.py)
…
```

Section titles are examples in Russian; use the course language.

## Order

Order the files so the reader understands each one before the next needs it. Usually: the data (state, models), then the pieces that act on it (nodes, handlers, functions), then how they are wired together, then the entry point that runs everything. Within a file, follow the code from top to bottom, so the reader can scroll along.

## Referring to code

- **By name first:** functions, classes, methods, variables, in backticks: `build_graph`, `TicketState.route`.
- **Link each name to its place,** relative to the read-along, with a line anchor: `[`build_graph`](../src/l1_2_routing/graph.py#L74)`, or a range: `…graph.py#L74-L94`. In VS Code these links open the file at that line, on GitHub they highlight it, and the reader always knows where to look.
- **Line numbers for single lines** that matter: "line 87 adds the conditional edge". Take the numbers from the final code, and check them.
- Paths go from `docs/readalong.md` to the code: `../src/…` for Python, Node and Rust, `../<file>.go` for Go.
- Don't copy code into the read-along. A short inline fragment in backticks is fine when you talk about it: "the call `builder.add_conditional_edges("classify", route_ticket)`".

## What to explain

- **What the code comments don't already say.** The code has its own comments, so don't repeat them. Add what a learner would ask next to the code: why this approach, what the library does here, what happens at run time, what would break if you changed it.
- **The technology, not the syntax.** "`add_node` registers the function under a name; the graph calls it with the current state and merges what it returns" is the point. "Here we call add_node" is not.
- **The non-obvious lines,** one by one when needed: a default that matters, an order that matters, a value that is merged rather than replaced.
- **For the concept itself,** link to the notes (`подробнее — в [конспекте](notes.md#…)`) instead of explaining theory here.

## Syntax

Plain Markdown: headings, short paragraphs, lists, inline code, relative links. Nothing else is needed. In particular, no snippet markers, no code blocks with lesson code, no `<details>`, no diagrams.

## Before you finish

1. Every link points to an existing file, and every `#L…` anchor to an existing line: `codelabgen check links --course <dir>` reports nothing for this lesson.
2. Open each linked line and make sure it really shows what the text says it shows.
