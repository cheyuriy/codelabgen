---
name: diagramming
description: How to draw diagrams and write math in codelabgen lessons — choosing Mermaid, D2 or Graphviz, generating diagrams from the code itself, size and labeling rules, and LaTeX conventions that render on both GitHub and the MkDocs site.
user-invocable: false
---

# Diagrams and math in lessons

A diagram earns its place when the reader needs to see **structure or flow**: how parts connect, the order things happen in, how state changes. Don't draw what a sentence says just as well.

## Choosing the tool

| Need | Tool | Why |
|---|---|---|
| Flows, graphs of nodes, sequences, state machines | **Mermaid** (` ```mermaid ` block) | GitHub renders it natively; no build step |
| A diagram of something the library can draw itself | **Generated from the code** | It always matches the code |
| Architecture, layered systems, many containers | **D2** (`docs/diagrams/<name>.d2` + rendered `.svg`) | Better layout for big pictures |
| Dense graphs | **Graphviz** (`docs/diagrams/<name>.dot` + `.svg`) | Handles many edges |

Default to Mermaid. Use D2 or Graphviz only when `codelabgen doctor` shows the tool as `ok`.

## D2 and Graphviz

- Put the source in `<lesson dir>/docs/diagrams/<name>.d2` (or `.dot`) and run `codelabgen diagrams render <id> --course <dir>`. It writes `<name>.svg` next to the source. Graphviz SVGs have a transparent background; D2 SVGs switch between a light and a dark palette with the reader's color scheme. `codelabgen verify` re-renders changed sources too.
- Reference the SVG from the docs: `![Архитектура сервиса](diagrams/<name>.svg)`. Never reference the source file.
- No colors or fonts in the source: the renderer's themes handle light and dark mode. Labels in the course language, short.
- Keep it readable at page width: about 20 shapes at most.

## Generate from the code when you can

Libraries that build graphs can often draw them. LangGraph's compiled graph prints Mermaid:

```bash
cd <lesson dir>
env -u VIRTUAL_ENV uv run python -c "from l1_2_routing.graph import build_graph; print(build_graph().get_graph().draw_mermaid())"
```

Paste the result into a ` ```mermaid ` block and add a sentence saying it was generated from the code. You may simplify styling, but never change the structure.

## Mermaid rules

- **At most about 15 nodes.** Split larger pictures, or show one level of detail.
- **Labels in the course language,** short (1–4 words). Identifiers stay as they are: `route()`, `TicketState`.
- **Pick the right type:** `flowchart LR/TD` for flows and graphs, `sequenceDiagram` for interactions over time, `stateDiagram-v2` for state machines.
- **No hard-coded colors or themes.** Let GitHub and the site apply light and dark themes.
- **Put labels with spaces, parentheses or non-Latin text in quotes:** `A["Классификация (classify)"]`.
- **Introduce each diagram** with one sentence saying what to look at.

## Math

- Inline: `$…$` with no spaces just inside the delimiters (`$O(n)$`, not `$ O(n) $`).
- Block: `$$…$$` on lines of their own, with a blank line before and after.
- Nothing else: no `\(…\)`, no ` ```math ` blocks.
- Escape a literal dollar sign in prose as `\$`.
- Formulas with `_` or `*` in several places go in block form, so Markdown on GitHub doesn't mangle them.
