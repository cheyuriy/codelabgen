---
name: course-extension
description: How to extend a finished codelabgen course — analysing what a request needs against the existing curriculum and source digests, planning targeted research (hunt.yaml), placing new or deepened lessons without renumbering, and what happens to lessons that build on rewritten ones. Used by the gap analyst and by the curriculum architect in extend mode.
user-invocable: false
---

# Extending a course

A finished course can be extended in two ways:
- **Deepen** an existing topic: "more on checkpointers", "explain reducers properly"
- **Add** a new topic: "add a module on deployment", "add a lesson on streaming"

Extensions live in `.codelabgen/extensions/<n>/`. The request is in `request.md`.

## 1. Gap analysis (gap analyst)

Work out what the request needs and what the course already has:

1. Read `request.md`, `.codelabgen/curriculum.yaml`, and the lessons the request touches: their `README.md`, `docs/notes.md`, and spec.
2. Read `.codelabgen/sources/index.md` and the digests of the relevant sources, **especially their "Gaps / dig deeper" sections**: they often say exactly where more material is.
3. Decide what is already covered (and where), what is covered only shallowly, and what is missing entirely.

Write `gaps.md`:

```markdown
# Extension 2: gap analysis

## Request
"Add a lesson on streaming"

## Already in the course
- 1.2 shows `stream_mode="updates"` in passing (readalong, "Запуск"), without explanation

## What the extension needs
- Streaming modes: values, updates, messages, custom, debug; when to use which
- Token streaming from LLM nodes
- …

## Material we already have
- official-docs--…--a1b2c3 covers stream modes (digest, "Topics covered"); its "dig deeper" points to the streaming how-to (not fetched)

## Missing material
- Token streaming with LLM nodes: no digest covers it

## Suggested placement
A new lesson 2.5 at the end of module 2, extending the 2.4 example. No renumbering needed.
```

And `hunt.yaml`: the targeted searches to run. It may be empty (`[]`) when the existing digests are enough.

```yaml
- type: official-docs
  skill: source-official-docs
  focus: "Streaming how-to: stream modes and token streaming (linked from the Graph API digest's dig-deeper section)"
- type: qa
  skill: source-qa
  focus: "Issues about streaming LLM tokens through graph nodes"
```

`type` and `skill` come from the hunters' table (`source-official-docs`, `source-articles`, …). `focus` tells the hunter exactly what to look for. Keep it to the few searches that matter.

## 2. The proposed curriculum (architect, extend mode)

The architect writes a **complete** proposed curriculum to `.codelabgen/extensions/<n>/curriculum.yaml`: a copy of the current `curriculum.yaml` with the change applied. Then:

```bash
codelabgen curriculum number --file .codelabgen/extensions/<n>/curriculum.yaml
codelabgen curriculum validate --file .codelabgen/extensions/<n>/curriculum.yaml
```

### Placement: avoid renumbering

Changing an existing lesson's id moves its directory, renames its package and breaks the user's branches. So place new material, in this order of preference:
1. **A sub-lesson** under the lesson it deepens (`2.3.1`), if the tree has room (three levels at most).
2. **At the end of the module** it belongs to.
3. **A new module at the end** of the course.

Insert in the middle (renumbering later lessons) only when the order really matters for understanding. Say so clearly in the status notes: the user must approve renumbering explicitly.

### Deepening an existing lesson

Edit that lesson's `summary` and `objectives` in the proposal: the lesson will be rewritten from its spec onwards. Lessons whose example builds on it (`example.from`, directly or indirectly) become `stale` and are re-checked.

### Rules

- Never remove lessons. Extensions only add and rewrite.
- Keep slugs of existing lessons unchanged: the slug path is how a lesson is recognised. Changing a slug looks like removing a lesson and adding a new one.
- Wording-only edits (titles) are fine; they don't trigger a rewrite.
- New lessons follow the curriculum-design skill: objectives, prerequisites, storyline, and `sources`, including the new digests.

## 3. After the user approves

`codelabgen extend apply` (with `--allow-renumber` only when the user agreed) does the rest:
- registers new lessons as `pending`
- sends rewritten lessons back to `pending`
- marks lessons that build on them `stale`
- moves renumbered lessons: directories, packages, specs, runs, links

Lesson production then runs as usual.

**Stale lessons** are re-checked, not rewritten blindly. Run `codelabgen verify <id>`. If it passes, the lesson reviewer checks whether the lesson still agrees with the rewritten one it builds on. Then either accept it (`state set <id> reviewed`, then `done`) or rework it like any review.
