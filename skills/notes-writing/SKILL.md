---
name: notes-writing
description: How to write a codelabgen lesson's notes (`docs/notes.md`) — a book-style chapter on the lesson's concept that refers to the lesson code, with diagrams, callouts, self-check questions and cited sources, rendering well on GitHub and the MkDocs site. Used by the notes-writer agent.
user-invocable: false
---

# Writing the notes

The notes are the lesson's chapter in a book: they explain the concept properly, as a good technical book would, and tie it to the example the learner has just run. The read-along explains *the code*; the notes explain *the idea*, pointing into the code to make it concrete.

Write in the **course language** (`language` in `.codelabgen/config.yaml`). There is no length limit: the chapter is as long as the idea needs, and not a sentence longer. No filler, no marketing tone, no "in this lesson we will…" padding.

## Structure

Adapt to the topic. A typical chapter:

1. **The problem.** What situation calls for this concept? What goes wrong without it? Start from something the learner already knows.
2. **The concept.** Define it precisely. Introduce terms one at a time, each defined on first use. Give the mental model that makes the rest follow.
3. **How it works.** The mechanism, with a diagram where structure or flow matters.
4. **In our example.** Map the concept onto the lesson code: which region does what, with snippets (same markers as the read-along) for the key parts, and links to the read-along for the walkthrough.
5. **Details and edge cases.** Behaviour that surprises people, limits, interactions with what earlier lessons covered.
6. **Common mistakes.** As callouts, ideally from real pitfalls (the `pitfalls` source digests, issue trackers, the spec's experiments).
7. **Summary.** 3–6 bullets the learner should remember.
8. **Self-check.** 3–5 questions with answers hidden in `<details>`.
9. **Further reading.** Sources actually used, with links.

## Accuracy

- Every claim about the technology must hold for the **pinned version**. Check against the official docs (WebFetch) and the installed package source in `<module dir>/.venv/lib/python3.*/site-packages/`. Use the `concepts` and `pitfalls` source digests in `.codelabgen/sources/` when they exist.
- Read `.codelabgen/research/deprecations.md` if it exists, and never present a deprecated API as current.
- When unsure, say less or verify, rather than guess.
- Write in your own words. Never copy text from sources. Short quotes are fine when attributed.

## Tying notes to the code

- Use snippet markers to show the key parts. `codelabgen snippets sync` fills them, exactly as in the read-along:
  ```markdown
  <!-- snippet: src/l1_2_routing/graph.py#build_graph -->
  <!-- /snippet -->
  ```
- Link to the walkthrough with `[разбор кода](readalong.md#…)` and to files with relative links such as `[graph.py](../src/l1_2_routing/graph.py)`.
- Refer to code by identifiers, never by line numbers.

## Glossary terms

The course has a shared glossary (`GLOSSARY.md`). On the site, every use of a term shows its definition on hover.

- For each term this lesson **introduces**, add it, in the course language:
  ```bash
  codelabgen glossary add "Граф состояний" --definition "Граф, в котором узлы по очереди обновляют общее состояние." --alias "граф состояний" --lesson <id> --course <dir>
  ```
  Use the form the term takes in text as the term. Add inflected forms the text uses as `--alias` (Russian: "графа", "графе"…), because tooltips match exact words only.
- **Link the first use** of each term in the notes to its entry. Get the link target from `codelabgen glossary link "<term>" --from <lesson dir>/docs/notes.md --course <dir>`.
- Check `codelabgen glossary list` first. Don't redefine terms that earlier lessons introduced, but you may link to them.
- Definitions: one or two sentences, self-contained, without Markdown links.
- **Never use an everyday word as a term or alias.** Tooltips attach to every exact occurrence on the site, in every lesson. A term like "Поток" (thread) with aliases "поток", "потока" would tooltip unrelated uses of the word ("поток данных"). Use the specific form instead: `thread`, `thread_id`, "поток (thread)". Distinctive technical words such as `checkpointer`, `reducer`, `StateSnapshot` and their inflections are fine.

## Diagrams, math, callouts

- Follow the diagramming skill. Use Mermaid by default; generate the diagram from the code when the library can draw it.
- Math: only `$…$` (inline) and `$$…$$` (block, on its own lines).
- Callouts in GitHub alert syntax:
  ```markdown
  > [!WARNING]
  > Узел должен возвращать только изменённые поля …
  ```
  Use `NOTE` for asides, `TIP` for practical advice, `WARNING` for common mistakes, `IMPORTANT` for must-know facts.
- Only syntax that renders on GitHub and the site: no `!!!` admonitions, content tabs, code annotations or `--8<--`.

## Further reading

List only sources you actually read for this chapter, with title and URL, official docs first. Never invent a URL; check each one with WebFetch.

## Before you finish

1. `codelabgen snippets sync <id> --course <dir>`, then `codelabgen check snippets <id> --course <dir>` must print `ok`.
2. Every relative link points to an existing file. Every external link was fetched.
3. Every diagram follows the diagramming skill's rules.
4. `codelabgen check links --course <dir>`, `check render` and `check math` report nothing for this lesson's files.
