---
name: readalong-writing
description: How to write a codelabgen lesson's read-along (`docs/readalong.md`) — a guided walk through the lesson code with snippets synced from code regions, the real output of the run, and "what to try" experiments, rendering well on GitHub and the MkDocs site. Used by the readalong-writer agent.
user-invocable: false
---

# Writing the read-along

The read-along is for a learner with the lesson code open. It walks through the code in the order that makes the idea click, explains what each part does and why, shows the real output, and ends with experiments. The theory goes in the notes (`docs/notes.md`). The read-along stays close to the code and links to the notes for the concept.

Write it in the **course language** (`language` in `.codelabgen/config.yaml`). Code identifiers, file names and commands stay as they are.

## Structure

```markdown
# <id> <lesson title> — разбор кода          ← "code walkthrough" in the course language

One or two sentences: what the example does and which idea it shows.
Link to the notes: [Конспект](notes.md).

## Как запустить                              ← how to run
From the course root: `./run.sh <id>` (it loads .env, starts services, syncs and runs),
and `./run.sh test <id>` for the tests. Then the manual way, for readers who want to
see the steps: `docker compose up -d --wait <service>` if needed, one-time
install in the module (or lesson) directory, then the run command in the lesson
directory. Say which directory each command runs in.

## Что изменилось с урока X                   ← only when the example extends an earlier lesson
The delta from the spec, as a short list with links to the regions below.

## <one section per step of the walkthrough>
A snippet, then the explanation.

## Что получится                              ← the real output
## Что попробовать                            ← experiments
```

Section titles are examples in Russian; use the course language.

## Order of the walkthrough

Follow the reader's understanding, not the file order. Usually: the data (state, models) → the pieces that act on it (nodes, functions) → how they are wired together → the entry point that runs it. One section per region, with headings that say what the reader learns ("Маршрутизация: функция route"), not just the identifier.

## Snippets: never paste code by hand

Show code only through snippet markers. `codelabgen snippets sync` fills them from the code's regions:

```markdown
<!-- snippet: src/l1_2_routing/graph.py#route -->
<!-- /snippet -->
```

- Paths are relative to the lesson directory. `#name` is a region from the spec's `regions`; without `#name` the whole file is shown (fine for short files).
- Write the markers with nothing between them, then run `codelabgen snippets sync <id> --course <dir>`, which fills in the code.
- Refer to code by identifiers and quoted fragments ("the call `graph.add_conditional_edges(...)`"), **never by line numbers**, which change.

## Explaining the code

- After each snippet, explain what the reader needs: what this part is for, what the library does with it, the key lines, and anything surprising. Go down to individual lines where they carry the idea.
- Don't repeat what the code says; explain what it means. "Here we add a node" is useless. "The node's return value is merged into the state, so returning only `category` leaves the other fields untouched" is the point.
- Link concepts to the notes rather than re-explaining theory: `подробнее — в [конспекте](notes.md#reducers)`.
- Mermaid diagrams are welcome when they show the code's structure, for example the graph the code builds (see the diagramming skill).

## Real output

Quote the live run's real output from the latest passing verify run: `.codelabgen/runs/<id>/<latest>/live-run.log` (the part after the command header). Copy it exactly into a `text` code block, then explain what to notice in it. Never invent or "tidy" output. If the output depends on an LLM or on time, say that a run may differ.

## Recordings

If the spec lists `recordings`, the verify run saved them as `<lesson dir>/docs/generated/<name>.gif` (with a `.cast` next to it). Show each one where it helps, usually next to the real output:

```markdown
![Запуск: маршрутизация трёх обращений](generated/route-tickets.gif)
```

The path is relative to the read-along, so write it as `generated/<name>.gif`. Only link GIFs that exist. If verify logged "skipped" for `record`, show the text output alone.

## Experiments

Turn the spec's `experiments` into a "what to try" section. For each one: what to change (a concrete edit), what you will observe, and why. Put the explanation in a collapsible block, so the reader can guess first:

```markdown
1. В `route` верните `"unknown"` вместо `"general"` и запустите снова.

   <details><summary>Что произойдёт и почему</summary>

   …

   </details>
```

Each experiment starts from the lesson's original code. When an experiment changes the code, end its explanation with a reminder to undo the change (for example `git checkout -- src/` or "верните код как было") before the next one.

**Verify what you predict.** Run each experiment in a scratch copy of the lesson directory (outside the course) and describe what really happens, not what the spec expected. If the outcome differs from the spec's `experiments` entry, correct that entry in `.codelabgen/lessons/<id>/spec.yaml` as well, so the spec stays the source of truth for later lessons.

## Syntax that works on GitHub and the site

Only these: plain Markdown, fenced code, Mermaid, `$…$` and `$$…$$` math, GitHub alerts (`> [!NOTE]`, `> [!TIP]`, `> [!WARNING]`), `<details>`, and relative links. **Not** `!!!` admonitions, content tabs, code annotations or `--8<--` includes.

## Before you finish

1. `codelabgen snippets sync <id> --course <dir>`
2. `codelabgen check snippets <id> --course <dir>` must print `ok`.
3. `codelabgen check links --course <dir>`, `check render` and `check math` report nothing for this lesson's files.
